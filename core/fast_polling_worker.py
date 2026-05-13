"""선택 PID 만 grep 으로 빠르게 폴링하는 워커.

`adb -s <serial> shell "dumpsys meminfo | grep 'pid <N>'"` 형식의 응답이
보통 4 줄(Total PSS by process / OOM adjustment 섹션 각 2줄)이며,
사용자 요구에 따라 **3번째 줄(Total PSS by OOM adjustment 헤더 라인)** 의
메모리 값을 사용한다.
"""
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QThread, pyqtSignal

from core.data_models import ADJGroup, MemInfoSnapshot, ProcessEntry

# "   25,820K: com.nhn.android.search (pid 23280)" 같은 라인을 파싱
_LINE_RE = re.compile(r"^\s*(\d[\d,]*)K:\s+(.+?)\s+\(pid\s+(\d+)\)")

_FAST_ADJ_CATEGORY = "FastUpdate"
_FAST_ADJ_ORDER    = 99


def _extract(m: re.Match) -> tuple[str, int, int]:
    mem_kb = int(m.group(1).replace(",", ""))
    pkg    = m.group(2).strip()
    pid    = int(m.group(3))
    return (pkg, pid, mem_kb)


def parse_grep_response(raw: str) -> tuple[str, int, int] | None:
    """grep 응답에서 (package, pid, memory_kb) 추출.

    선호 순서:
      1) 3번째 라인 (사용자 명시 — OOM ADJ 헤더 라인)
      2) 매칭 가능한 마지막 라인
      3) 매칭 가능한 어떤 라인
    매칭되는 라인이 하나도 없으면 None.
    """
    if not raw:
        return None
    lines = [l for l in raw.splitlines() if l.strip()]

    # 1순위: 3번째 라인
    if len(lines) >= 3:
        m = _LINE_RE.match(lines[2])
        if m:
            return _extract(m)

    # 2순위: 매칭되는 마지막 라인
    for line in reversed(lines):
        m = _LINE_RE.match(line)
        if m:
            return _extract(m)
    return None


# 하위 호환 alias
parse_grep_third_line = parse_grep_response


class FastPollingWorker(QThread):
    snapshot_ready = pyqtSignal(object)   # MemInfoSnapshot
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        adb_manager,
        serial: str,
        packages_with_pids: list[tuple[str, int]],
        interval_sec: int,
    ):
        super().__init__()
        self._adb          = adb_manager
        self._serial       = serial
        self._procs        = list(packages_with_pids)   # [(pkg, pid), ...]
        self._interval_sec = max(1, int(interval_sec))
        self._stop_flag    = threading.Event()

    # ── QThread 인터페이스 ───────────────────────────────────────────────────

    def run(self):
        self._stop_flag.clear()
        n = max(1, len(self._procs))
        with ThreadPoolExecutor(max_workers=n) as ex:
            while not self._stop_flag.is_set():
                t0 = time.monotonic()

                # 사이클 내 모든 PID 에 대해 병렬 grep 수행 후 결과 수집
                results = self._run_one_cycle(ex)

                if self._stop_flag.is_set():
                    break

                snap = self._build_snapshot(results)
                self.snapshot_ready.emit(snap)

                elapsed   = time.monotonic() - t0
                remaining = max(0.0, self._interval_sec - elapsed)
                self._sleep_with_stop_check(remaining)

    def _run_one_cycle(self, executor: ThreadPoolExecutor) -> list[tuple[str, int, int]]:
        """선택된 PID 들에 대해 병렬 grep 후 결과 수집. 한 사이클이 끝나야 다음 사이클 진입."""
        futures = {
            executor.submit(self._fetch_one, pkg, pid): (pkg, pid)
            for pkg, pid in self._procs
        }
        results: list[tuple[str, int, int]] = []
        try:
            for fut in as_completed(futures, timeout=self._interval_sec + 30):
                if self._stop_flag.is_set():
                    break
                try:
                    r = fut.result()
                    if r is not None:
                        results.append(r)
                except Exception as e:
                    self.error_occurred.emit(str(e))
        except Exception as e:
            self.error_occurred.emit(str(e))
        return results

    def _fetch_one(self, pkg: str, pid: int) -> tuple[str, int, int] | None:
        """패키지명으로 grep 후 (pkg, pid) 정확히 매칭되는 라인만 사용.

        한 번의 `grep "<pkg>"` 응답에 같은 패키지명을 가진 다른 PID,
        또는 substring 매칭되는 다른 프로세스(`:privileged_process0` 등)가
        섞여 있을 수 있으므로 엄격하게 필터링한다.

        매칭 라인 중 3번째(사용자 명시 — OOM ADJ 헤더) 우선, 폴백은 마지막.
        """
        raw = self._adb.run_meminfo_for_package(self._serial, pkg)

        # 예) "    25,820K: com.nhn.android.search (pid 23280)"
        #     "    25,820K: com.nhn.android.search (pid 23280 / activities)"
        # 제외) "...:privileged_process0 (pid ...)"  / 다른 PID
        exact_re = re.compile(
            r"^\s*(\d[\d,]*)K:\s+"
            + re.escape(pkg)
            + r"\s+\(pid\s+" + str(pid) + r"(?:\s*/[^)]*)?\)\s*$"
        )
        matched_mem: list[int] = []
        for line in raw.splitlines():
            m = exact_re.match(line)
            if m:
                matched_mem.append(int(m.group(1).replace(",", "")))

        if not matched_mem:
            snippet = (
                raw[:160].replace("\n", " | ").strip()
                if raw else "<empty response>"
            )
            self.error_occurred.emit(
                f"{pkg} (PID {pid}) 매칭 실패: {snippet}"
            )
            return None

        mem_kb = matched_mem[2] if len(matched_mem) >= 3 else matched_mem[-1]
        return (pkg, pid, mem_kb)

    def _build_snapshot(self, results: list[tuple[str, int, int]]) -> MemInfoSnapshot:
        snap = MemInfoSnapshot(device_id=self._serial, timestamp=time.time())
        if not results:
            return snap
        group = ADJGroup(
            adj_category=_FAST_ADJ_CATEGORY,
            adj_order=_FAST_ADJ_ORDER,
            total_memory_kb=sum(r[2] for r in results),
        )
        for pkg, pid, mem_kb in results:
            group.processes.append(ProcessEntry(
                adj_category=_FAST_ADJ_CATEGORY,
                adj_order=_FAST_ADJ_ORDER,
                memory_kb=mem_kb,
                package_name=pkg,
                pid=pid,
                timestamp=snap.timestamp,
            ))
        snap.adj_groups.append(group)
        return snap

    def _sleep_with_stop_check(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not self._stop_flag.is_set():
            time.sleep(0.05)

    def stop(self) -> None:
        self._stop_flag.set()
        self.wait(3000)

    def set_interval(self, sec: int) -> None:
        self._interval_sec = max(1, int(sec))
