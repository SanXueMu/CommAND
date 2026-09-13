"""测试辅助：带超时的数据库可达性探测。

背景：集成测试在**模块导入期**用 `pytest.mark.skipif(not _db_reachable(), ...)` 决定是否跳过；
若直接连库而网络不通（VPN 断开等），TCP 连接会长时间挂起，导致整个 pytest 卡在 collecting。
故这里先做带超时的 TCP 探测，再尝试真实连接。
"""
from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

DEFAULT_DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://command_dev:root@192.168.8.41:5432/command_dev"
)


def db_reachable(url: str | None = None, timeout: float = 2.0) -> bool:
    url = url or DEFAULT_DB_URL
    parsed = urlparse(url)
    host, port = parsed.hostname, parsed.port or 5432
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError:
        return False
    try:
        from store.db import Db

        return Db(url).ping()
    except Exception:
        return False
