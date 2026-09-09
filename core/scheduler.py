"""L5 调度循环：认领执行 / 心跳 / 恢复 / 协作取消注册表。"""

import threading
import time
from pathlib import Path
from typing import Any

from config import Config
from core.errors import TaskCancelled, ToolDomainError, ToolUserError
from core.protocol import ToolManifest
from core.runner import RunContext, Runner
from store.db import Db
from store.event_repo import EventRepo
from store.task_repo import TaskRepo
from store.tool_repo import ToolRepo


class Scheduler:
    """worker 主循环：claim → Runner 执行 → 状态落盘；emit 顺带心跳。"""

    def __init__(
        self,
        db: Db,
        runner: Runner,
        task_repo: TaskRepo,
        tool_repo: ToolRepo,
        event_repo: EventRepo,
        config: Config,
    ) -> None:
        self._db = db
        self._runner = runner
        self._task_repo = task_repo
        self._tool_repo = tool_repo
        self._event_repo = event_repo
        self._config = config
        self._stop = threading.Event()
        self._running: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self._task_repo.recover_stale(self._config.heartbeat_timeout_s)
        for i in range(self._config.worker_concurrency):
            thread = threading.Thread(target=self._worker_loop, args=(f"w{i}",), daemon=True)
            thread.start()
            self._threads.append(thread)
        heartbeat = threading.Thread(target=self._heartbeat_loop, daemon=True)
        heartbeat.start()
        self._threads.append(heartbeat)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=10)

    def request_cancel(self, handle: str) -> bool:
        """协作取消：置位该任务的 cancel_event，由工具在检查点响应。"""
        with self._lock:
            event = self._running.get(handle)
        if event is None:
            return False
        event.set()
        return True

    def run_once(self, worker_id: str) -> bool:
        """认领并执行一条任务；返回是否执行（测试可同步驱动）。"""
        task = self._task_repo.claim(worker_id)
        if task is None:
            return False
        handle = task["handle"]
        cancel_event = threading.Event()
        with self._lock:
            self._running[handle] = cancel_event
        try:
            self._execute(task, cancel_event)
        finally:
            with self._lock:
                self._running.pop(handle, None)
        return True

    def _execute(self, task: dict[str, Any], cancel_event: threading.Event) -> None:
        handle = task["handle"]

        def emit(type: str, data: dict[str, Any]) -> None:
            self._event_repo.append(handle, type, data)
            self._task_repo.heartbeat(handle)

        try:
            tool = self._tool_repo.get(task["tool_id"])
            if tool is None or not tool.get("path"):
                self._task_repo.finish(handle, "failed", error={
                    "kind": "system",
                    "message": "工具未登记落位路径（migration 002 前注册的旧记录），请重新 register"})
                return
            manifest = ToolManifest.model_validate(tool["manifest"])
            tool_dir = Path(tool["path"])
            ctx = RunContext(handle=handle, attempt=task["attempt"],
                             cancel_event=cancel_event, emit=emit)
            result = self._runner.run(manifest, tool_dir, task["input"], ctx)
            self._task_repo.finish(handle, "succeeded", output=result)
        except TaskCancelled:
            self._task_repo.finish(handle, "cancelled")
        except ToolDomainError as exc:
            if task["attempt"] < task["max_attempts"]:
                self._task_repo.requeue(handle)
            else:
                self._task_repo.finish(handle, "failed_review", error={
                    "kind": "domain", "message": str(exc)})
        except ToolUserError as exc:
            self._task_repo.finish(handle, "failed", error={
                "kind": "user", "message": str(exc)})
        except Exception as exc:
            self._task_repo.finish(handle, "failed", error={
                "kind": "system", "message": f"{type(exc).__name__}: {exc}"})

    def _worker_loop(self, worker_id: str) -> None:
        while not self._stop.is_set():
            if not self.run_once(worker_id):
                time.sleep(0.5)

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                handles = list(self._running.keys())
            for handle in handles:
                self._task_repo.heartbeat(handle)
            self._task_repo.recover_stale(self._config.heartbeat_timeout_s)
            self._stop.wait(self._config.heartbeat_interval_s / 3)
