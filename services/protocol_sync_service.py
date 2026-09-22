"""协议同步服务（蓝图「飞升」§同步状态机）：

    capture → 固化会员原始映像（不可变，内容去重）
    sync    → PENDING → VALIDATING → MIGRATING → SUCCEEDED / FAILED / INCOMPATIBLE

铁律（总体方案 2026-09-22）：
- 幂等可重放：同 (provider, snapshot, to_release) 已 SUCCEEDED 的 run 直接命中，不重复投影；
- 事务内完成：锁定→校验→迁移→翻转投影→落状态 一次提交，崩溃即整体回滚；
- advisory lock：hashtext(provider) 防同会员并发同步；
- 失败保留上一次成功投影（无 Down Migration，回退 = 切回历史成功投影）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from store.db import Db
from store.protocol_repo import ProtocolRepo, _canonical_json
from store.site_repo import SiteRepo

DEFAULT_PROVIDER_ID = "default"

# CommAND 侧当前实现的协议口径（与 CommWEB src/protocol/version.ts 对账维护）。
CURRENT_CORE = 1
CURRENT_SNAPSHOT_SCHEMA = 1
CURRENT_EXTENSIONS: dict[str, int] = {
    "site.manifest": 3,
    "slots.decl": 3,
    "form.cascade": 1,
    "toolface.ui": 1,
    "studio.ocr": 1,
    "studio.translate": 1,
}
CURRENT_RELEASE_ID = 1

# 迁移链：(from_release, to_release) → payload 变换。
# 顺序应用、必须幂等（同输入同输出）；新增协议发布时登记对应边，禁止改写旧边。
MIGRATIONS: dict[tuple[int, int], Callable[[dict[str, Any]], dict[str, Any]]] = {}


def _checksum(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:16]


class ProtocolSyncService:
    def __init__(self, db: Db, repo: ProtocolRepo, site_repo: SiteRepo) -> None:
        self._db = db
        self._repo = repo
        self._site_repo = site_repo

    def ensure_current_release(self) -> None:
        """启动幂等登记当前协议发布（发布历史只追加，不改旧行）。"""
        self._repo.ensure_release(
            CURRENT_RELEASE_ID, CURRENT_CORE, CURRENT_EXTENSIONS,
            CURRENT_SNAPSHOT_SCHEMA, notes="初始发布：Core/Extension/Snapshot 三层口径立baseline",
        )

    # ── 采集：会员原始映像 ────────────────────────────────────

    def capture(self, provider_id: str = DEFAULT_PROVIDER_ID) -> dict[str, Any]:
        """刷新会员映像：访问会员实时声明 → 固化为不可变 Source Snapshot。

        目前仅支持中心自托管会员（default = CommAND 自身 site_views）；
        远程会员采集（在线时拉其 /meta/site）为后续扩展点。
        """
        if provider_id != DEFAULT_PROVIDER_ID:
            raise ValueError(f"暂不支持远程会员采集: {provider_id}")
        payload = {"name": "CommAND", "views": self._site_repo.list()}
        checksum = _checksum(payload)
        latest = self._repo.latest_snapshot(provider_id)
        if latest and latest["checksum"] == checksum:
            return {"snapshot": latest, "deduped": True}  # 内容未变不落新行
        release = self._repo.latest_release()
        if not release:
            raise RuntimeError("协议发布表为空（ensure_current_release 未执行）")
        snapshot_id = self._repo.insert_snapshot(
            provider_id, release["id"], CURRENT_SNAPSHOT_SCHEMA, payload, checksum,
        )
        return {
            "snapshot": {"id": snapshot_id, "release_id": release["id"],
                         "schema_version": CURRENT_SNAPSHOT_SCHEMA,
                         "payload": payload, "checksum": checksum, "captured_at": None},
            "deduped": False,
        }

    # ── 同步：状态机主体 ──────────────────────────────────────

    def sync(self, provider_id: str = DEFAULT_PROVIDER_ID, to_release_id: int | None = None) -> dict[str, Any]:
        target = self._repo.release(to_release_id or CURRENT_RELEASE_ID)
        if not target:
            raise ValueError(f"目标协议发布不存在: {to_release_id}")
        snapshot = self._repo.latest_snapshot(provider_id)
        if not snapshot:
            raise ValueError("无会员映像（先执行采集 /control/protocol/providers/{pid}/capture）")

        # 幂等重放：同映像 + 同目标已成功 → 直接命中（不重复投影）
        hit = self._repo.succeeded_run(provider_id, snapshot["id"], target["id"])
        if hit:
            return {"run": hit, "replayed": True}

        run_id = self._repo.insert_sync_run(
            provider_id, snapshot["id"], snapshot["release_id"], target["id"],
        )
        return {"run": self._sync_locked(provider_id, run_id, snapshot, target)}

    def _sync_locked(
        self, provider_id: str, run_id: int, snapshot: dict[str, Any], target: dict[str, Any],
    ) -> dict[str, Any]:
        """锁定段：单连接单事务（advisory xact lock → 校验 → 迁移 → 翻转投影 → 终态）。"""
        from_release: int = snapshot["release_id"]
        to_release: int = target["id"]

        def finish(status: str, error: str | None = None, checksum: str | None = None) -> dict[str, Any]:
            self._repo.update_sync_run(run_id, status, error=error, checksum=checksum)
            return self._repo.list_sync_runs(provider_id, 1)[0]

        try:
            with self._db.pool.connection() as conn:
                # 并发锁：同会员同步串行化（事务级，块结束自动释放）
                conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"protocol_sync:{provider_id}",))
                # 锁内二次确认幂等（防两请求同时过了锁外检查）
                hit = conn.execute(
                    "SELECT id FROM provider_sync_run WHERE provider_id=%s AND snapshot_id=%s"
                    " AND to_release_id=%s AND status='SUCCEEDED' LIMIT 1",
                    (provider_id, snapshot["id"], to_release),
                ).fetchone()
                if hit:
                    conn.rollback()
                    return {"id": hit[0], "status": "SUCCEEDED", "replayed": True}

                # VALIDATING：快照格式必须不高于目标发布（只升不降，降级不支持）
                if snapshot["schema_version"] > target["snapshot_schema"]:
                    conn.rollback()
                    return finish("INCOMPATIBLE", error=(
                        f"映像 schema v{snapshot['schema_version']} 高于目标发布"
                        f" v{target['snapshot_schema']}（不支持降级）"))
                if from_release > to_release:
                    conn.rollback()
                    return finish("INCOMPATIBLE", error=f"不支持降级发布 r{from_release}→r{to_release}")

                # MIGRATING：沿迁移链逐边应用
                payload = dict(snapshot["payload"])
                step = from_release
                while step < to_release:
                    edge = MIGRATIONS.get((step, step + 1))
                    if edge is None:
                        conn.rollback()
                        return finish("INCOMPATIBLE", error=f"缺迁移边 r{step}→r{step + 1}")
                    payload = edge(payload)
                    step += 1

                checksum = _checksum(payload)
                conn.execute(
                    "UPDATE provider_projection SET is_current = FALSE WHERE provider_id=%s AND is_current",
                    (provider_id,),
                )
                conn.execute(
                    "INSERT INTO provider_projection (provider_id, snapshot_id, release_id, payload, checksum, is_current)"
                    " VALUES (%s, %s, %s, %s, %s, TRUE)",
                    (provider_id, snapshot["id"], to_release, json.dumps(payload, ensure_ascii=False), checksum),
                )
                conn.execute(
                    "UPDATE provider_sync_run SET status='SUCCEEDED', checksum=%s, finished_at=now(), error=NULL WHERE id=%s",
                    (checksum, run_id),
                )
            return self._repo.list_sync_runs(provider_id, 1)[0]
        except Exception as exc:  # noqa: BLE001 —— 任何异常落 FAILED，保留上一次成功投影
            return finish("FAILED", error=str(exc))

    # ── 状态视图 ──────────────────────────────────────────────

    def state(self, provider_id: str = DEFAULT_PROVIDER_ID) -> dict[str, Any]:
        return {
            "provider_id": provider_id,
            "release": self._repo.latest_release(),
            "snapshot": self._repo.latest_snapshot(provider_id),
            "projection": self._repo.current_projection(provider_id),
            "runs": self._repo.list_sync_runs(provider_id, 10),
        }
