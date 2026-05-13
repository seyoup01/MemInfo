import time
import threading

from PyQt6.QtCore import QThread, pyqtSignal

from core.meminfo_parser import parse as default_parser
from core.data_models import MemInfoSnapshot


def compute_delta(
    current: MemInfoSnapshot,
    prev: MemInfoSnapshot | None,
) -> MemInfoSnapshot:
    """이전 스냅샷과 비교하여 각 ProcessEntry의 prev_memory_kb / is_new / is_gone 설정."""
    if prev is None:
        return current

    # 이전 스냅샷 프로세스를 {package_name: memory_kb} 로 색인
    prev_map: dict[str, int] = {
        p.package_name: p.memory_kb
        for g in prev.adj_groups
        for p in g.processes
    }
    # 현재 스냅샷 패키지명 집합
    cur_names: set[str] = {
        p.package_name
        for g in current.adj_groups
        for p in g.processes
    }

    for group in current.adj_groups:
        for proc in group.processes:
            if proc.package_name in prev_map:
                proc.prev_memory_kb = prev_map[proc.package_name]
                proc.is_new = False
            else:
                proc.prev_memory_kb = 0
                proc.is_new = True

    # 종료된 프로세스: 이전에 있었으나 현재 없는 것 → is_gone=True 로 표시하여 별도 그룹에 추가
    gone_entries = []
    for g in prev.adj_groups:
        for p in g.processes:
            if p.package_name not in cur_names:
                p.is_gone = True
                p.timestamp = current.timestamp
                gone_entries.append(p)

    if gone_entries:
        # 기존 ADJ 그룹에 삽입 (같은 카테고리에 추가)
        cat_map = {g.adj_category: g for g in current.adj_groups}
        for p in gone_entries:
            if p.adj_category in cat_map:
                cat_map[p.adj_category].processes.append(p)
            else:
                from core.data_models import ADJGroup
                new_grp = ADJGroup(p.adj_category, p.adj_order)
                new_grp.processes.append(p)
                current.adj_groups.append(new_grp)

    return current


class PollingWorker(QThread):
    snapshot_ready = pyqtSignal(object)   # MemInfoSnapshot 전달
    error_occurred = pyqtSignal(str)      # 오류 메시지 전달

    def __init__(self, adb_manager, parser, device_id: str, interval_sec: int):
        super().__init__()
        self._adb        = adb_manager
        self._parser     = parser
        self._device_id  = device_id
        self._interval_sec = interval_sec
        self._stop_flag  = threading.Event()
        self._prev_snap: MemInfoSnapshot | None = None

    # ── QThread 인터페이스 ────────────────────────────────────────────────────

    def run(self):
        self._stop_flag.clear()
        while not self._stop_flag.is_set():
            try:
                raw = self._adb.run_meminfo(self._device_id)
                if raw:
                    snap = self._parser(raw, self._device_id)
                    snap = compute_delta(snap, self._prev_snap)
                    self._prev_snap = snap
                    self.snapshot_ready.emit(snap)
                else:
                    self.error_occurred.emit("meminfo 데이터를 받지 못했습니다.")
            except Exception as e:
                self.error_occurred.emit(str(e))

            # 폴링 간격 동안 0.05초 단위로 stop 플래그 체크
            deadline = time.monotonic() + self._interval_sec
            while time.monotonic() < deadline and not self._stop_flag.is_set():
                time.sleep(0.05)

    def stop(self) -> None:
        self._stop_flag.set()
        self.wait(2000)   # 최대 2초 대기

    def set_interval(self, sec: int) -> None:
        """실행 중에도 주기 변경 가능 (다음 사이클부터 적용)."""
        self._interval_sec = sec
