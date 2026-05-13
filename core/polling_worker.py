import re
import time
import threading

from PyQt6.QtCore import QThread, pyqtSignal

from core.meminfo_parser import parse as default_parser
from core.data_models import MemInfoSnapshot

# dumpsys meminfo 의 끝부분 "Tuning: 512 (large 512), oom ..." 라인
# 이 라인이 보여야 출력이 완결된 것으로 간주.
_OUTPUT_COMPLETE = re.compile(r"^\s*Tuning:\s+\d", re.MULTILINE)

# 연속 N 회 불완전/실패 응답이 누적되면 짧은 백오프
_MAX_CONSECUTIVE_INCOMPLETE = 5
_BACKOFF_ON_INCOMPLETE_SEC  = 2.0


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
        self._consecutive_incomplete = 0

    # ── QThread 인터페이스 ────────────────────────────────────────────────────

    def run(self):
        self._stop_flag.clear()
        self._consecutive_incomplete = 0
        while not self._stop_flag.is_set():
            wait_full_interval = True
            try:
                raw = self._adb.run_meminfo(self._device_id)
                if raw and _OUTPUT_COMPLETE.search(raw):
                    snap = self._parser(raw, self._device_id)
                    snap = compute_delta(snap, self._prev_snap)
                    self._prev_snap = snap
                    self._consecutive_incomplete = 0
                    self.snapshot_ready.emit(snap)
                else:
                    # 불완전·빈 응답 → 폴링 주기 SKIP 하고 즉시 재시도
                    self._consecutive_incomplete += 1
                    self.error_occurred.emit(
                        "meminfo 응답이 불완전합니다 — 재시도 중"
                        if raw else
                        "meminfo 데이터를 받지 못했습니다 — 재시도 중"
                    )
                    wait_full_interval = False
            except Exception as e:
                self._consecutive_incomplete += 1
                self.error_occurred.emit(str(e))
                wait_full_interval = False

            if self._stop_flag.is_set():
                break

            if wait_full_interval:
                # 정상 응답 → 설정된 폴링 주기만큼 대기
                self._sleep_with_stop_check(self._interval_sec)
            elif self._consecutive_incomplete >= _MAX_CONSECUTIVE_INCOMPLETE:
                # 연속 실패 누적 → 폭주 방지 백오프
                self._sleep_with_stop_check(_BACKOFF_ON_INCOMPLETE_SEC)
            # else: 즉시 재시도 (대기 없음)

    def _sleep_with_stop_check(self, seconds: float) -> None:
        """stop 플래그를 0.05s 단위로 폴링하며 대기."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not self._stop_flag.is_set():
            time.sleep(0.05)

    def stop(self) -> None:
        self._stop_flag.set()
        # 메인 폴링이 dumpsys subprocess 에 블록되어 있으면 wait() 가 무한정 대기.
        # adb 가 cancel_all() 을 지원하면 진행 중 subprocess 를 즉시 종료하여 깨움.
        if hasattr(self._adb, "cancel_all"):
            try:
                self._adb.cancel_all()
            except Exception:
                pass
        self.wait(3000)

    def set_interval(self, sec: int) -> None:
        """실행 중에도 주기 변경 가능 (다음 사이클부터 적용)."""
        self._interval_sec = sec
