import os
import sqlite3
import time
from .data_models import MemInfoSnapshot

_DB_DIR = os.path.join(os.path.expanduser("~"), ".meminfo_monitor")
_DB_PATH = os.path.join(_DB_DIR, "history.db")

_DDL = """
CREATE TABLE IF NOT EXISTS snapshots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT    NOT NULL,
    timestamp REAL    NOT NULL,
    adj       TEXT    NOT NULL,
    adj_order INTEGER NOT NULL,
    package   TEXT    NOT NULL,
    pid       INTEGER NOT NULL,
    memory_kb INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_timestamp ON snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_package   ON snapshots(package);
"""


class HistoryManager:
    def __init__(self, max_records: int = 1000, db_path: str = _DB_PATH):
        self.max_records = max_records
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_DDL)

    # ── 공개 API ─────────────────────────────────────────────────────────────

    def save_snapshot(self, snapshot: MemInfoSnapshot) -> None:
        """스냅샷의 모든 프로세스를 DB에 저장. max_records 초과 시 자동 삭제."""
        rows = [
            (
                snapshot.device_id,
                snapshot.timestamp,
                proc.adj_category,
                proc.adj_order,
                proc.package_name,
                proc.pid,
                proc.memory_kb,
            )
            for group in snapshot.adj_groups
            for proc in group.processes
        ]
        if not rows:
            return

        conn = self._connect()
        try:
            conn.executemany(
                "INSERT INTO snapshots "
                "(device_id, timestamp, adj, adj_order, package, pid, memory_kb) "
                "VALUES (?,?,?,?,?,?,?)",
                rows,
            )
            # max_records 초과 시 가장 오래된 레코드 삭제
            total = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            if total > self.max_records:
                excess = total - self.max_records
                conn.execute(
                    "DELETE FROM snapshots WHERE id IN "
                    "(SELECT id FROM snapshots ORDER BY timestamp ASC, id ASC LIMIT ?)",
                    (excess,),
                )
            conn.commit()
        finally:
            conn.close()

    def get_snapshots_for_process(
        self, package_name: str, limit: int = 200
    ) -> list[tuple[float, int]]:
        """[(timestamp, memory_kb), ...] 최신순 반환 (차트용)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT timestamp, memory_kb FROM snapshots "
                "WHERE package = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (package_name, limit),
            ).fetchall()
        finally:
            conn.close()
        return [(r["timestamp"], r["memory_kb"]) for r in rows]

    def get_all_for_export(self) -> list[dict]:
        """CSV/JSON 내보내기용 전체 데이터."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT device_id, timestamp, adj, adj_order, package, pid, memory_kb "
                "FROM snapshots ORDER BY timestamp ASC"
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def clear(self) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM snapshots")
            conn.commit()
        finally:
            conn.close()

    def record_count(self) -> int:
        conn = self._connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        finally:
            conn.close()
