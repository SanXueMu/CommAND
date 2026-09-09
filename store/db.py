"""L6 PostgreSQL 接入：连接池、健康检查与前进式版本化迁移。"""

from pathlib import Path

from psycopg_pool import ConnectionPool

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

SCHEMA_VERSION_DDL = (
    "CREATE TABLE IF NOT EXISTS schema_version ("
    "id INT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
)


class Db:
    """psycopg3 连接池封装：全系统唯一建连点。"""

    def __init__(self, database_url: str) -> None:
        self._pool = ConnectionPool(database_url, min_size=1, max_size=8, open=False)
        self._opened = False

    def open(self) -> None:
        if self._opened:
            return
        self._pool.open()
        self._opened = True

    def ping(self) -> bool:
        try:
            self.open()
            with self._pool.connection() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def apply_migrations(self) -> list[int]:
        self.open()
        applied: list[int] = []
        with self._pool.connection() as conn:
            conn.execute(SCHEMA_VERSION_DDL)
            done = {row[0] for row in conn.execute("SELECT id FROM schema_version").fetchall()}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                version = int(path.stem.split("_")[0])
                if version in done:
                    continue
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO schema_version (id) VALUES (%s)", (version,))
                applied.append(version)
        return applied

    @property
    def pool(self) -> ConnectionPool:
        return self._pool
