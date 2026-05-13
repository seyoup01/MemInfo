"""STEP 11 검증: 차트 빠르게 Update — PID grep 병렬 폴링."""
import os
import sys
import time

import pytest
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_meminfo.txt")


@pytest.fixture
def sample_snapshot():
    from core.meminfo_parser import parse
    with open(FIXTURE, encoding="utf-8") as f:
        return parse(f.read(), "test_device")


# ── AdbManager / MockAdbManager — PID 한정 명령 ───────────────────────────────

def test_adb_manager_run_meminfo_for_pid_exists():
    from core.adb_manager import AdbManager, MockAdbManager
    assert hasattr(AdbManager, "run_meminfo_for_pid")
    assert hasattr(MockAdbManager, "run_meminfo_for_pid")


def test_mock_run_meminfo_for_pid_returns_lines():
    """Mock 은 픽스처에서 해당 pid 라인을 추출/반복하여 최소 3줄 반환."""
    from core.adb_manager import MockAdbManager
    mgr = MockAdbManager()
    raw = mgr.run_meminfo_for_pid("dev", 1234)   # com.android.systemui pid 1234
    lines = [l for l in raw.splitlines() if l.strip()]
    assert len(lines) >= 3, f"3줄 이상 기대, 실제 {len(lines)}: {raw!r}"


# ── 3번째 라인 파싱 ───────────────────────────────────────────────────────────

def test_parse_grep_third_line_extracts_memory():
    """4줄 입력의 3번째 라인에서 (pkg, pid, memory_kb) 추출."""
    from core.fast_polling_worker import parse_grep_third_line
    raw = (
        "     35,864K: com.nhn.android.search (pid 23280)\n"
        "         35,864K: com.nhn.android.search (pid 23280)\n"
        "     25,820K: com.nhn.android.search (pid 23280)\n"
        "         25,820K: com.nhn.android.search (pid 23280)\n"
    )
    result = parse_grep_third_line(raw)
    assert result == ("com.nhn.android.search", 23280, 25820)


def test_parse_grep_returns_none_when_no_line_matches():
    """매칭되는 라인이 하나도 없을 때만 None 반환."""
    from core.fast_polling_worker import parse_grep_response
    assert parse_grep_response("") is None
    assert parse_grep_response("garbage\nstuff\n") is None


def test_parse_grep_response_falls_back_to_any_line():
    """3번째 라인이 없어도 매칭 가능한 라인이 있으면 추출."""
    from core.fast_polling_worker import parse_grep_response
    # 1줄짜리 응답
    one_line = "     25,820K: com.x (pid 123)\n"
    assert parse_grep_response(one_line) == ("com.x", 123, 25820)
    # 2줄 — 둘 다 매칭, 마지막 채택
    two = ("     11,111K: com.a (pid 5)\n"
           "     22,222K: com.a (pid 5)\n")
    pkg, pid, mem = parse_grep_response(two)
    assert mem == 22222


def test_parse_grep_response_picks_third_when_available():
    """4줄 응답이면 3번째 라인 우선 (사용자 명시 OOM ADJ 헤더)."""
    from core.fast_polling_worker import parse_grep_response
    raw = (
        "     35,864K: com.s (pid 23280)\n"
        "         35,864K: com.s (pid 23280)\n"
        "     25,820K: com.s (pid 23280)\n"
        "         25,820K: com.s (pid 23280)\n"
    )
    assert parse_grep_response(raw) == ("com.s", 23280, 25820)


def test_parse_grep_third_line_alias_still_exists():
    """하위 호환: parse_grep_third_line 이름도 사용 가능해야."""
    from core.fast_polling_worker import parse_grep_third_line, parse_grep_response
    assert parse_grep_third_line is parse_grep_response


# ── FastPollingWorker ─────────────────────────────────────────────────────────

class _FastAdbMock:
    """run_meminfo_for_pid 호출을 카운트하는 Mock. PID 별 고정값 반환."""
    def __init__(self, pid_mem: dict[int, int]):
        self._pid_mem = pid_mem
        self.calls = 0

    def run_meminfo_for_pid(self, serial, pid):
        self.calls += 1
        mem = self._pid_mem.get(pid, 0)
        # 4줄 형태로 합성 (3번째가 OOM)
        if mem == 0:
            return ""
        line = f"     {mem:,}K: pkg{pid} (pid {pid})"
        return f"{line}\n    {line}\n{line}\n    {line}\n"


def _wait_for(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        _app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_fast_polling_emits_snapshot_with_all_selected_pids():
    from core.fast_polling_worker import FastPollingWorker
    adb = _FastAdbMock({1001: 12345, 1002: 67890, 1003: 11111})
    pairs = [("a", 1001), ("b", 1002), ("c", 1003)]

    worker = FastPollingWorker(adb, "dev", pairs, interval_sec=1)
    snaps = []
    worker.snapshot_ready.connect(lambda s: snaps.append(s))
    worker.start()

    assert _wait_for(lambda: len(snaps) >= 1, timeout=2.0), \
        f"snapshot 미발생: 호출 {adb.calls}회"
    worker.stop()

    snap = snaps[0]
    pkgs = {p.package_name: p.memory_kb for g in snap.adj_groups for p in g.processes}
    assert pkgs == {"a": 12345, "b": 67890, "c": 11111}, pkgs


def test_fast_polling_stops_cleanly():
    from core.fast_polling_worker import FastPollingWorker
    adb = _FastAdbMock({1: 100})
    worker = FastPollingWorker(adb, "dev", [("a", 1)], interval_sec=1)
    worker.start()
    _wait_for(lambda: adb.calls >= 1, timeout=2.0)
    worker.stop()
    assert not worker.isRunning()


def test_fast_polling_respects_interval():
    """interval=2 일 때 0.3초 동안 너무 자주 호출되지 않아야 한다."""
    from core.fast_polling_worker import FastPollingWorker
    adb = _FastAdbMock({1: 100})
    worker = FastPollingWorker(adb, "dev", [("a", 1)], interval_sec=2)
    worker.start()
    # 첫 사이클 발생할 시간만 기다림
    _wait_for(lambda: adb.calls >= 1, timeout=2.0)
    first_calls = adb.calls
    time.sleep(0.3)   # interval 보다 짧음 → 추가 호출 없어야
    _app.processEvents()
    worker.stop()
    assert adb.calls - first_calls <= 1, \
        f"interval 미준수: {adb.calls - first_calls}회 추가 호출"


def test_fast_polling_skips_unparseable_pid():
    """grep 결과가 None 인 PID 는 결과에서 제외, 나머지는 정상 emit."""
    from core.fast_polling_worker import FastPollingWorker
    adb = _FastAdbMock({1001: 12345, 1002: 0})   # 1002 는 빈 응답
    pairs = [("a", 1001), ("b", 1002)]
    worker = FastPollingWorker(adb, "dev", pairs, interval_sec=1)
    snaps = []
    worker.snapshot_ready.connect(lambda s: snaps.append(s))
    worker.start()
    _wait_for(lambda: len(snaps) >= 1, timeout=2.0)
    worker.stop()
    pkgs = {p.package_name for g in snaps[0].adj_groups for p in g.processes}
    assert pkgs == {"a"}, pkgs


# ── SelectionView 버튼 ───────────────────────────────────────────────────────

def test_selection_view_has_fast_chart_button():
    from ui.selection_view import SelectionView
    sv = SelectionView()
    assert hasattr(sv, "_btn_fast")
    assert "빠르게" in sv._btn_fast.text()


def test_selection_view_fast_chart_emits_pairs(sample_snapshot):
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv.update_data(sample_snapshot)

    received = []
    sv.fast_chart_requested.connect(lambda lst: received.append(list(lst)))

    # 일부 선택
    first_proc = sample_snapshot.adj_groups[0].processes[0]
    sv._selected_packages.add(first_proc.package_name)
    sv._emit_fast_chart()

    assert received, "fast_chart_requested 미발생"
    assert received[-1] == [(first_proc.package_name, first_proc.pid)]


def test_selection_view_fast_chart_no_emit_when_empty(sample_snapshot):
    """선택이 0개면 emit 하지 않아야 한다."""
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv.update_data(sample_snapshot)

    received = []
    sv.fast_chart_requested.connect(lambda lst: received.append(lst))
    sv._emit_fast_chart()
    assert received == []


# ── FastUpdateWindow ─────────────────────────────────────────────────────────

def test_fast_update_window_default_interval_is_1s():
    from core.adb_manager import MockAdbManager
    from ui.fast_update_window import FastUpdateWindow
    win = FastUpdateWindow(MockAdbManager(), "dev", [("a", 1)])
    try:
        assert win._interval_combo.currentText() == "1s"
    finally:
        win.close()


def test_fast_update_window_close_signal():
    from core.adb_manager import MockAdbManager
    from ui.fast_update_window import FastUpdateWindow
    win = FastUpdateWindow(MockAdbManager(), "dev", [("a", 1)])
    fired = []
    win.closed.connect(lambda: fired.append(True))
    win.close()
    assert fired == [True]


def test_fast_update_window_chart_packages_match():
    from core.adb_manager import MockAdbManager
    from ui.fast_update_window import FastUpdateWindow
    win = FastUpdateWindow(MockAdbManager(), "dev", [("a", 1), ("b", 2)])
    try:
        assert win._chart._packages == ["a", "b"]
    finally:
        win.close()


# ── MainWindow 통합 ──────────────────────────────────────────────────────────

def test_main_window_has_fast_window_initially_none():
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w._fast_win is None


def test_main_window_opens_fast_update_on_request(sample_snapshot):
    from ui.main_window import MainWindow
    from ui.fast_update_window import FastUpdateWindow

    w = MainWindow()
    w.selection_view.update_data(sample_snapshot)

    # 첫 프로세스 (pkg, pid) 한 쌍 emit
    proc = sample_snapshot.adj_groups[0].processes[0]
    w.selection_view.fast_chart_requested.emit([(proc.package_name, proc.pid)])
    _app.processEvents()

    assert isinstance(w._fast_win, FastUpdateWindow), "FastUpdateWindow 미생성"
    w._fast_win.close()
    _app.processEvents()
    assert w._fast_win is None


def test_main_window_resumes_polling_after_fast_close(sample_snapshot, monkeypatch):
    """fast 윈도우 닫힌 후, 이전에 폴링 중이었으면 _start_worker 호출."""
    from ui.main_window import MainWindow
    w = MainWindow()

    # _fast_was_running 가 True 일 때 _start_worker 가 호출되는지 검증
    called = []
    monkeypatch.setattr(w, "_start_worker", lambda: called.append(True))
    w._fast_was_running = True
    w._on_fast_window_closed()
    assert called == [True]
    assert w._fast_was_running is False


def test_main_window_no_resume_if_was_not_running():
    from ui.main_window import MainWindow
    w = MainWindow()
    w._fast_was_running = False
    # _start_worker 호출 카운트를 위해 monkeypatch 없이 worker 상태만 검증
    w._on_fast_window_closed()
    assert w._worker is None


# ── 진단: 파싱 실패 시 error_occurred 발생 ──────────────────────────────────

class _UnparseableAdb:
    def run_meminfo_for_pid(self, serial, pid):
        return "this output\ncannot match the expected line format\n"


def test_fast_polling_emits_error_with_raw_excerpt_on_failure():
    from core.fast_polling_worker import FastPollingWorker
    worker = FastPollingWorker(_UnparseableAdb(), "dev", [("a", 1)], interval_sec=1)
    errors = []
    worker.error_occurred.connect(lambda m: errors.append(m))
    worker.start()
    _wait_for(lambda: len(errors) >= 1, timeout=2.0)
    worker.stop()
    assert any("PID 1" in e and ("cannot match" in e or "this output" in e)
               for e in errors), f"진단 메시지 미발생: {errors}"


class _EmptyAdb:
    def run_meminfo_for_pid(self, serial, pid):
        return ""


def test_fast_polling_emits_empty_response_diagnostic():
    from core.fast_polling_worker import FastPollingWorker
    worker = FastPollingWorker(_EmptyAdb(), "dev", [("a", 7)], interval_sec=1)
    errors = []
    worker.error_occurred.connect(lambda m: errors.append(m))
    worker.start()
    _wait_for(lambda: len(errors) >= 1, timeout=2.0)
    worker.stop()
    assert any("PID 7" in e and "empty" in e.lower() for e in errors), \
        f"empty 진단 미발생: {errors}"


# ── AdbManager quote 폴백 ───────────────────────────────────────────────────

def test_adb_run_meminfo_for_pid_tries_double_quote_first(monkeypatch):
    """첫 시도가 큰따옴표 패턴이어야 한다 (Windows + adb 호환성)."""
    from core.adb_manager import AdbManager

    # AdbManager 인스턴스 생성을 회피하기 위해 클래스에 직접 patch
    calls = []
    def fake_run(self, *args, timeout=None):
        calls.append(args)
        return ""   # 모두 빈 응답 → 두 패턴 모두 시도

    monkeypatch.setattr(AdbManager, "_run", fake_run)
    monkeypatch.setattr(AdbManager, "__init__", lambda self: None)

    mgr = AdbManager()
    mgr._adb = "adb"   # 임의값
    mgr.run_meminfo_for_pid("dev", 23280)

    assert len(calls) >= 1
    first_cmd = calls[0][3]   # "-s", "dev", "shell", <cmd>
    assert '"pid 23280"' in first_cmd, f"첫 시도 큰따옴표 아님: {first_cmd}"


def test_adb_run_meminfo_for_pid_falls_back_to_single_quote(monkeypatch):
    """큰따옴표 응답이 빈 경우 작은따옴표로 폴백."""
    from core.adb_manager import AdbManager

    calls = []
    def fake_run(self, *args, timeout=None):
        calls.append(args)
        return ""

    monkeypatch.setattr(AdbManager, "_run", fake_run)
    monkeypatch.setattr(AdbManager, "__init__", lambda self: None)

    mgr = AdbManager()
    mgr._adb = "adb"
    mgr.run_meminfo_for_pid("dev", 23280)

    assert len(calls) == 2, f"폴백 시도 안 함: {calls}"
    second_cmd = calls[1][3]
    assert "'pid 23280'" in second_cmd, f"폴백이 작은따옴표 아님: {second_cmd}"


# ── FastUpdateWindow status bar 진단 ──────────────────────────────────────

def test_fast_update_window_status_bar_updates_on_snapshot(sample_snapshot):
    """스냅샷 수신 후 status bar 에 '응답 N/M' 형식 포함."""
    from core.adb_manager import MockAdbManager
    from ui.fast_update_window import FastUpdateWindow

    win = FastUpdateWindow(MockAdbManager(), "dev",
                           [("com.android.systemui", 1234)])
    try:
        # 워커 시작 후 첫 스냅샷이 도착할 때까지 짧게 대기
        _wait_for(lambda: "응답" in win._status.currentMessage(), timeout=3.0)
        msg = win._status.currentMessage()
        assert "응답" in msg, f"상태바: {msg!r}"
        assert "/1" in msg or "1/1" in msg, f"카운트 없음: {msg!r}"
    finally:
        win.close()
