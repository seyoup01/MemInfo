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
    """run_meminfo_for_package 호출을 카운트하는 Mock.

    `pid_mem` dict 의 키가 PID, 값이 memory_kb. 패키지명은 호출 시점에 동적 매칭.
    """
    def __init__(self, pid_mem: dict[int, int], pkg_for_pid: dict[int, str] | None = None):
        self._pid_mem    = pid_mem
        self._pkg_for_pid = pkg_for_pid or {}
        self.calls = 0

    def run_meminfo_for_package(self, serial, package):
        self.calls += 1
        out = []
        # 요청된 package 에 해당하는 PID 의 라인만 4줄(3번째가 OOM) 형태로 합성
        for pid, mem in self._pid_mem.items():
            if mem == 0:
                continue
            pkg_for_this_pid = self._pkg_for_pid.get(pid, package)
            if pkg_for_this_pid != package:
                continue
            for _ in range(4):
                out.append(f"     {mem:,}K: {package} (pid {pid})")
        return "\n".join(out) + "\n" if out else ""


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
    adb = _FastAdbMock(
        {1001: 12345, 1002: 67890, 1003: 11111},
        pkg_for_pid={1001: "a", 1002: "b", 1003: "c"},
    )
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
    adb = _FastAdbMock(
        {1001: 12345, 1002: 0},
        pkg_for_pid={1001: "a", 1002: "b"},
    )
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
    def run_meminfo_for_package(self, serial, package):
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
    def run_meminfo_for_package(self, serial, package):
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


# ── 패키지명 grep (Step 2) ────────────────────────────────────────────────────

def test_adb_run_meminfo_for_package_tries_double_quote_first(monkeypatch):
    from core.adb_manager import AdbManager
    calls = []
    monkeypatch.setattr(AdbManager, "__init__", lambda self: None)
    monkeypatch.setattr(AdbManager, "_run",
                        lambda self, *args, timeout=None: (calls.append(args) or ""))
    mgr = AdbManager()
    mgr.run_meminfo_for_package("dev", "com.example.app")
    assert len(calls) >= 1
    first_cmd = calls[0][3]
    assert '"com.example.app"' in first_cmd, f"첫 시도 큰따옴표 아님: {first_cmd}"


def test_adb_run_meminfo_for_package_falls_back_to_single_quote(monkeypatch):
    from core.adb_manager import AdbManager
    calls = []
    monkeypatch.setattr(AdbManager, "__init__", lambda self: None)
    monkeypatch.setattr(AdbManager, "_run",
                        lambda self, *args, timeout=None: (calls.append(args) or ""))
    mgr = AdbManager()
    mgr.run_meminfo_for_package("dev", "com.example.app")
    assert len(calls) == 2, f"폴백 시도 안 함: {calls}"
    second_cmd = calls[1][3]
    assert "'com.example.app'" in second_cmd


def test_mock_run_meminfo_for_package_filters_lines():
    from core.adb_manager import MockAdbManager
    mgr = MockAdbManager()
    raw = mgr.run_meminfo_for_package("dev", "com.android.systemui")
    lines = [l for l in raw.splitlines() if l.strip()]
    # 픽스처에서 com.android.systemui 포함 라인만 반환
    assert all("com.android.systemui" in l for l in lines)
    assert len(lines) >= 1


# ── 정확 매칭 필터 — substring/다른 PID 차단 ────────────────────────────────

# 사용자 실측 예시 (com.nhn.android.search 패키지명 grep 결과 12줄)
_REAL_RESPONSE_12LINES = """\
    429,548K: com.nhn.android.search (pid 23195 / activities)
    142,160K: com.nhn.android.search:privileged_process0 (pid 23503)
     35,224K: com.nhn.android.search (pid 23280)
         35,224K: com.nhn.android.search (pid 23280)
        429,548K: com.nhn.android.search (pid 23195 / activities)
        142,160K: com.nhn.android.search:privileged_process0 (pid 23503)
    603,854K: com.nhn.android.search (pid 23195 / activities)
    115,882K: com.nhn.android.search:privileged_process0 (pid 23503)
     25,821K: com.nhn.android.search (pid 23280)
         25,821K: com.nhn.android.search (pid 23280)
        603,854K: com.nhn.android.search (pid 23195 / activities)
        115,882K: com.nhn.android.search:privileged_process0 (pid 23503)
"""


class _FixedAdb:
    """run_meminfo_for_package 가 고정된 응답을 반환하는 Mock."""
    def __init__(self, response: str):
        self._response = response
        self.calls = 0
    def run_meminfo_for_package(self, serial, package):
        self.calls += 1
        return self._response


def test_fast_polling_filters_substring_package_matches():
    """패키지명이 'com.nhn.android.search' 인데 응답에 같은 접두어를 가진
    다른 프로세스(:privileged_process0)가 섞여 있어도 제외해야 한다."""
    from core.fast_polling_worker import FastPollingWorker
    adb = _FixedAdb(_REAL_RESPONSE_12LINES)
    # pid 23280 만 선택
    worker = FastPollingWorker(
        adb, "dev", [("com.nhn.android.search", 23280)], interval_sec=1
    )
    snaps = []
    worker.snapshot_ready.connect(lambda s: snaps.append(s))
    worker.start()
    _wait_for(lambda: len(snaps) >= 1, timeout=2.0)
    worker.stop()

    procs = [p for g in snaps[0].adj_groups for p in g.processes]
    assert len(procs) == 1, f"정확히 1개 기대, 실제 {len(procs)}: {procs}"
    p = procs[0]
    assert p.package_name == "com.nhn.android.search"
    assert p.pid == 23280
    # 3번째 매칭 라인 값 (사용자 예시) = 25,821K
    assert p.memory_kb == 25821, f"매칭 라인 추출 오류: {p.memory_kb}"


def test_fast_polling_filters_different_pid_same_pkg():
    """같은 패키지명 다른 PID (23195 / activities) 는 제외되어야 한다."""
    from core.fast_polling_worker import FastPollingWorker
    adb = _FixedAdb(_REAL_RESPONSE_12LINES)
    # pid 23195 선택 — 다른 결과를 기대
    worker = FastPollingWorker(
        adb, "dev", [("com.nhn.android.search", 23195)], interval_sec=1
    )
    snaps = []
    worker.snapshot_ready.connect(lambda s: snaps.append(s))
    worker.start()
    _wait_for(lambda: len(snaps) >= 1, timeout=2.0)
    worker.stop()

    procs = [p for g in snaps[0].adj_groups for p in g.processes]
    assert len(procs) == 1
    # 23195 매칭 라인 4개: 429,548 / 429,548 / 603,854 / 603,854
    # 3번째 = 603,854
    assert procs[0].memory_kb == 603854, f"23195 추출 오류: {procs[0].memory_kb}"


def test_fast_polling_falls_back_to_last_when_under_3_matches():
    """매칭 라인 2개일 때 마지막 라인 사용."""
    from core.fast_polling_worker import FastPollingWorker
    response = (
        "    50,000K: com.x (pid 100)\n"
        "        60,000K: com.x (pid 100)\n"
    )
    adb = _FixedAdb(response)
    worker = FastPollingWorker(adb, "dev", [("com.x", 100)], interval_sec=1)
    snaps = []
    worker.snapshot_ready.connect(lambda s: snaps.append(s))
    worker.start()
    _wait_for(lambda: len(snaps) >= 1, timeout=2.0)
    worker.stop()
    procs = [p for g in snaps[0].adj_groups for p in g.processes]
    assert procs[0].memory_kb == 60000   # 마지막 라인


def test_fast_polling_emits_error_when_no_match():
    from core.fast_polling_worker import FastPollingWorker
    adb = _FixedAdb("    99,999K: other.pkg (pid 999)\n")
    worker = FastPollingWorker(adb, "dev", [("com.x", 100)], interval_sec=1)
    errors = []
    worker.error_occurred.connect(lambda m: errors.append(m))
    worker.start()
    _wait_for(lambda: len(errors) >= 1, timeout=2.0)
    worker.stop()
    assert any("com.x" in e and "100" in e for e in errors), f"errors: {errors}"


# ── AdbManager subprocess 추적 / cancel_all ──────────────────────────────────

def test_adb_cancel_all_kills_pending_subprocesses():
    """_procs 에 들어있는 Popen-like 객체들의 kill() 이 호출되어야."""
    from core.adb_manager import AdbManager

    killed = []
    class FakeProc:
        def kill(self):
            killed.append(self)

    mgr = AdbManager.__new__(AdbManager)   # __init__ 우회
    import threading as _t
    mgr._procs_lock = _t.Lock()
    mgr._procs = {FakeProc(), FakeProc(), FakeProc()}
    mgr.cancel_all()
    assert len(killed) == 3


def test_polling_worker_stop_calls_cancel_all():
    """PollingWorker.stop() 이 adb.cancel_all() 을 호출하는지."""
    from core.polling_worker import PollingWorker

    cancel_calls = []
    class _CancelMock:
        def run_meminfo(self, *a, **k):
            time.sleep(0.05)
            return ""
        def cancel_all(self):
            cancel_calls.append(True)

    worker = PollingWorker(_CancelMock(), lambda *_: None, "dev", interval_sec=1)
    worker.start()
    time.sleep(0.1)
    worker.stop()
    assert cancel_calls, "cancel_all 미호출"


# ── 메인 윈도우 상태바 (Step 1 검증) ─────────────────────────────────────────

def test_main_window_shows_status_message_when_fast_open(sample_snapshot):
    from ui.main_window import MainWindow
    w = MainWindow()
    w.selection_view.update_data(sample_snapshot)
    proc = sample_snapshot.adj_groups[0].processes[0]
    w.selection_view.fast_chart_requested.emit([(proc.package_name, proc.pid)])
    _app.processEvents()
    msg = w.status_bar.currentMessage()
    assert "메인 dumpsys 폴링 중단됨" in msg, f"상태바: {msg!r}"
    w._fast_win.close()
    _app.processEvents()


def test_main_window_clears_status_after_fast_close(sample_snapshot):
    from ui.main_window import MainWindow
    w = MainWindow()
    w.selection_view.update_data(sample_snapshot)
    proc = sample_snapshot.adj_groups[0].processes[0]
    w.selection_view.fast_chart_requested.emit([(proc.package_name, proc.pid)])
    _app.processEvents()
    assert w._fast_win is not None
    w._fast_win.close()
    _app.processEvents()
    msg = w.status_bar.currentMessage()
    assert "중단됨" not in msg, f"상태바 미클리어: {msg!r}"
