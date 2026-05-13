"""STEP 10 검증: 내보내기, 자동 재연결, 최종 통합"""
import csv
import json
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


@pytest.fixture
def history_with_data(tmp_path, sample_snapshot):
    from core.history_manager import HistoryManager
    hm = HistoryManager(db_path=str(tmp_path / "hist.db"))
    hm.save_snapshot(sample_snapshot)
    hm.save_snapshot(sample_snapshot)
    return hm


# ── Exporter imports ──────────────────────────────────────────────────────────

def test_exporter_imports():
    from utils.exporter import Exporter
    assert Exporter is not None


# ── export_csv ────────────────────────────────────────────────────────────────

def test_export_csv_creates_file(tmp_path, history_with_data):
    from utils.exporter import Exporter
    path = str(tmp_path / "out.csv")
    records = history_with_data.get_all_for_export()
    Exporter.export_csv(records, path)
    assert os.path.exists(path), "CSV 파일이 생성되지 않음"


def test_export_csv_has_correct_headers(tmp_path, history_with_data):
    from utils.exporter import Exporter
    path = str(tmp_path / "out.csv")
    records = history_with_data.get_all_for_export()
    Exporter.export_csv(records, path)

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames

    for col in ["timestamp", "device_id", "adj", "package", "pid", "memory_kb"]:
        assert col in headers, f"컬럼 '{col}' 누락"


def test_export_csv_row_count(tmp_path, history_with_data, sample_snapshot):
    """CSV 행 수 = 히스토리 레코드 수."""
    from utils.exporter import Exporter
    path = str(tmp_path / "out.csv")
    records = history_with_data.get_all_for_export()
    Exporter.export_csv(records, path)

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == len(records)


# ── export_json ───────────────────────────────────────────────────────────────

def test_export_json_creates_file(tmp_path, history_with_data):
    from utils.exporter import Exporter
    path = str(tmp_path / "out.json")
    Exporter.export_json(history_with_data.get_all_for_export(), path)
    assert os.path.exists(path)


def test_export_json_parseable(tmp_path, history_with_data):
    from utils.exporter import Exporter
    path = str(tmp_path / "out.json")
    records = history_with_data.get_all_for_export()
    Exporter.export_json(records, path)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list)
    assert len(data) == len(records)


def test_export_json_contains_required_keys(tmp_path, history_with_data):
    from utils.exporter import Exporter
    path = str(tmp_path / "out.json")
    Exporter.export_json(history_with_data.get_all_for_export(), path)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    for key in ["timestamp", "package", "memory_kb"]:
        assert key in data[0], f"'{key}' 키 누락"


# ── export_current_view_csv ───────────────────────────────────────────────────

def test_export_current_view_csv(tmp_path, sample_snapshot):
    from utils.exporter import Exporter
    path = str(tmp_path / "cur.csv")
    Exporter.export_current_view_csv(sample_snapshot, path)
    assert os.path.exists(path)

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == sample_snapshot.total_process_count


# ── ReconnectWorker ───────────────────────────────────────────────────────────

def test_reconnect_worker_imports():
    from core.adb_manager import ReconnectWorker
    assert ReconnectWorker is not None


def test_reconnect_worker_succeeds_with_mock():
    """MockAdbManager는 항상 test_connection=True → 즉시 reconnected."""
    from core.adb_manager import MockAdbManager, ReconnectWorker
    mgr      = MockAdbManager()
    worker   = ReconnectWorker(mgr, "emulator-5554", max_retries=5, interval_sec=0)
    results  = []
    worker.reconnected.connect(lambda: results.append("ok"))
    worker.start()
    deadline = time.time() + 3
    while time.time() < deadline:
        _app.processEvents()
        if results:
            break
        time.sleep(0.05)
    worker.wait(2000)
    assert results == ["ok"], "reconnected 시그널 미수신"


def test_reconnect_worker_fails_permanently():
    """test_connection이 항상 False → failed_permanently 시그널."""
    from core.adb_manager import ReconnectWorker

    class FailMock:
        def test_connection(self, _): return False

    worker  = ReconnectWorker(FailMock(), "dummy", max_retries=2, interval_sec=0)
    results = []
    worker.failed_permanently.connect(lambda: results.append("fail"))
    worker.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        _app.processEvents()
        if results:
            break
        time.sleep(0.05)
    worker.wait(3000)
    assert results == ["fail"], "failed_permanently 시그널 미수신"


# ── MainWindow 최종 확인 ──────────────────────────────────────────────────────

def test_main_window_has_history_manager():
    from ui.main_window import MainWindow
    from core.history_manager import HistoryManager
    w = MainWindow()
    assert isinstance(w._history, HistoryManager)


def test_main_window_has_menubar():
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.menuBar() is not None
    assert w.menuBar().actions(), "메뉴바에 액션이 없음"


def test_main_window_has_file_menu():
    from ui.main_window import MainWindow
    w = MainWindow()
    menu_titles = [a.text() for a in w.menuBar().actions()]
    assert any("파일" in t for t in menu_titles), f"파일 메뉴 없음: {menu_titles}"


def test_main_window_has_settings_menu():
    from ui.main_window import MainWindow
    w = MainWindow()
    menu_titles = [a.text() for a in w.menuBar().actions()]
    assert any("설정" in t for t in menu_titles), f"설정 메뉴 없음: {menu_titles}"


def test_spec_file_exists():
    """PyInstaller .spec 파일이 생성되어 있어야 함."""
    spec = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "MemInfoMonitor.spec"
    )
    assert os.path.exists(spec), f".spec 파일 없음: {spec}"


# ── PollingWorker 완료성 검증 + 즉시 재시도 ──────────────────────────────────

class _AlwaysIncompleteAdb:
    """항상 Tuning: 라인이 없는 불완전한 응답을 반환하는 Mock."""
    def __init__(self):
        self.calls = 0
    def run_meminfo(self, serial):
        self.calls += 1
        return "Total PSS by OOM adjustment:\n  100K: Native\n"  # Tuning 없음


class _OnceIncompleteThenCompleteAdb:
    """첫 호출은 불완전, 이후는 Tuning: 라인 포함 완전 응답."""
    def __init__(self):
        self.calls = 0
    def run_meminfo(self, serial):
        self.calls += 1
        if self.calls == 1:
            return "Total PSS by OOM adjustment:\n"
        with open(FIXTURE, encoding="utf-8") as f:
            return f.read() + "\n   Tuning: 512 (large 512), oom 322,560K\n"


def test_polling_worker_skips_interval_on_incomplete():
    """불완전 응답 시 폴링 주기를 SKIP 하고 즉시 재시도해야 한다."""
    from core.polling_worker import PollingWorker
    from core.meminfo_parser import parse

    adb = _AlwaysIncompleteAdb()
    worker = PollingWorker(adb, parse, "dev", interval_sec=999)

    errors = []
    worker.error_occurred.connect(lambda m: errors.append(m))
    worker.start()

    # 0.4초 동안 여러 번 재시도가 발생해야 한다 (interval=999s 무시)
    deadline = time.time() + 0.4
    while time.time() < deadline:
        _app.processEvents()
        time.sleep(0.02)
    worker.stop()

    assert adb.calls >= 3, f"즉시 재시도 누락: {adb.calls}회 호출"
    assert any("불완전" in m or "받지 못했습니다" in m for m in errors)


def test_polling_worker_completes_with_tuning_line():
    """Tuning: 라인 포함 응답은 정상 파싱·emit 되어야 한다."""
    from core.polling_worker import PollingWorker
    from core.meminfo_parser import parse

    adb = _OnceIncompleteThenCompleteAdb()
    worker = PollingWorker(adb, parse, "dev", interval_sec=999)

    snaps = []
    worker.snapshot_ready.connect(lambda s: snaps.append(s))
    worker.start()

    deadline = time.time() + 1.0
    while time.time() < deadline and not snaps:
        _app.processEvents()
        time.sleep(0.02)
    worker.stop()

    assert snaps, "Tuning: 라인 포함 응답이 emit 되지 않음"
    assert snaps[0].total_process_count > 0


def test_polling_worker_backoff_after_consecutive_failures():
    """연속 5회 실패 후에는 즉시 재시도 대신 백오프가 발생해야 한다."""
    from core.polling_worker import (
        PollingWorker, _MAX_CONSECUTIVE_INCOMPLETE, _BACKOFF_ON_INCOMPLETE_SEC,
    )
    from core.meminfo_parser import parse

    adb = _AlwaysIncompleteAdb()
    worker = PollingWorker(adb, parse, "dev", interval_sec=999)
    worker.start()

    # MAX 만큼 호출까지는 즉시 재시도, 이후엔 백오프 → 호출 빈도 급감
    deadline = time.time() + (_BACKOFF_ON_INCOMPLETE_SEC + 0.5)
    while time.time() < deadline:
        _app.processEvents()
        time.sleep(0.02)
    worker.stop()

    # 백오프 없으면 100회+ 호출되겠지만, 백오프 적용 시 훨씬 적게 호출됨
    assert adb.calls >= _MAX_CONSECUTIVE_INCOMPLETE, \
        f"최소 {_MAX_CONSECUTIVE_INCOMPLETE}회 호출 기대, 실제 {adb.calls}회"
    assert adb.calls < 50, \
        f"백오프가 적용되지 않은 듯: {adb.calls}회 호출"
