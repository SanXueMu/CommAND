"""L1 配置：frozen dataclass 配置族 + load_config（.env 与环境变量覆盖默认值）。"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    database_url: str
    worker_concurrency: int
    heartbeat_interval_s: int
    heartbeat_timeout_s: int
    tools_dir: Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def load_config(env_file: str = ".env") -> Config:
    _load_dotenv(Path(env_file))
    return Config(
        host=os.environ.get("COMMAND_HOST", "127.0.0.1"),
        port=int(os.environ.get("COMMAND_PORT", "8800")),
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql://command:command@127.0.0.1:5433/command",
        ),
        worker_concurrency=int(os.environ.get("WORKER_CONCURRENCY", "4")),
        heartbeat_interval_s=int(os.environ.get("HEARTBEAT_INTERVAL_S", "15")),
        heartbeat_timeout_s=int(os.environ.get("HEARTBEAT_TIMEOUT_S", "90")),
        tools_dir=Path(os.environ.get("TOOLS_DIR", "tools")),
    )
