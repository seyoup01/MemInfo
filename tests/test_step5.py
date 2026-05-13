"""STEP 5 검증: 메인 윈도우 뼈대, 툴바, 상태바"""
import sys
import pytest

# QApplication 싱글턴 — 모듈 레벨에서 한 번만 생성
from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication(sys.argv)


# ── Toolbar 로직 (QApplication 필요) ─────────────────────────────────────────

def test_toolbar_interval_to_sec_basic():
    from ui.toolbar import Toolbar
    assert Toolbar._interval_to_sec("1s")   == 1
    assert Toolbar._interval_to_sec("5s")   == 5
    assert Toolbar._interval_to_sec("30s")  == 30
    assert Toolbar._interval_to_sec("1분")  == 60
    assert Toolbar._interval_to_sec("5분")  == 300
    assert Toolbar._interval_to_sec("10분") == 600


def test_toolbar_interval_to_sec_all_labels():
    from ui.toolbar import Toolbar, _INTERVAL_MAP
    for label, expected in _INTERVAL_MAP.items():
        assert Toolbar._interval_to_sec(label) == expected, \
            f"{label} → 기대 {expected}초, 실제 {Toolbar._interval_to_sec(label)}초"


def test_toolbar_interval_unknown_returns_default():
    from ui.toolbar import Toolbar
    assert Toolbar._interval_to_sec("unknown") == 5


def test_toolbar_default_interval_is_5s():
    from ui.toolbar import Toolbar
    tb = Toolbar()
    assert tb.current_interval_sec() == 5


def test_toolbar_initial_state_start_enabled():
    """초기 상태: 시작 버튼만 활성화."""
    from ui.toolbar import Toolbar
    tb = Toolbar()
    assert tb.start_btn.isEnabled()
    assert not tb.pause_btn.isEnabled()
    assert not tb.stop_btn.isEnabled()


def test_toolbar_populate_devices():
    from ui.toolbar import Toolbar
    from core.adb_manager import AdbDevice
    tb = Toolbar()
    devices = [
        AdbDevice("R5CN12345", "SM-G998B", "online"),
        AdbDevice("emulator-5554", "Mock_Device", "online"),
    ]
    tb.populate_devices(devices)
    assert tb.device_combo.count() == 2


def test_toolbar_current_serial_empty_initially():
    from ui.toolbar import Toolbar
    tb = Toolbar()
    # 기기가 없으면 빈 문자열
    assert tb.current_serial() == ""


def test_toolbar_current_serial_after_populate():
    from ui.toolbar import Toolbar
    from core.adb_manager import AdbDevice
    tb = Toolbar()
    devices = [AdbDevice("R5CN12345", "SM-G998B", "online")]
    tb.populate_devices(devices)
    tb.device_combo.setCurrentIndex(0)
    assert tb.current_serial() == "R5CN12345"


# ── StatusBar ────────────────────────────────────────────────────────────────

def test_statusbar_update_status_connected():
    from ui.status_bar import StatusBar
    sb = StatusBar()
    sb.update_status(connected=True)
    assert "연결됨" in sb._conn_label.text()


def test_statusbar_update_status_disconnected():
    from ui.status_bar import StatusBar
    sb = StatusBar()
    sb.update_status(connected=False)
    assert "끊김" in sb._conn_label.text()


def test_statusbar_update_status_reconnecting():
    from ui.status_bar import StatusBar
    sb = StatusBar()
    sb.update_status(connected=False, reconnecting=True)
    assert "재연결" in sb._conn_label.text()


def test_statusbar_update_collection():
    from ui.status_bar import StatusBar
    sb = StatusBar()
    sb.update_collection(process_count=47, collection_num=10, elapsed_sec=65)
    assert "47" in sb._proc_label.text()
    assert "10" in sb._collect_label.text()
    assert "경과" in sb._elapsed_label.text()


def test_statusbar_update_last_time():
    import time
    from ui.status_bar import StatusBar
    sb = StatusBar()
    ts = time.time()
    sb.update_last_time(ts)
    assert "마지막 업데이트" in sb._time_label.text()
    assert "--:--:--" not in sb._time_label.text()


# ── Settings 연동 ─────────────────────────────────────────────────────────────

def test_settings_last_device_key():
    from utils.settings import Settings
    import tempfile, os
    tmp = tempfile.mktemp(suffix=".json")
    s = Settings(path=tmp)
    s.set("last_device", "R5CN99999")
    s2 = Settings(path=tmp)
    assert s2.get("last_device") == "R5CN99999"
    os.remove(tmp)


# ── MainWindow 기본 구조 ──────────────────────────────────────────────────────

def test_main_window_creates_without_error():
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w is not None
    w.close()


def test_main_window_has_3_tabs():
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.tabs.count() >= 3   # STEP 9에서 Chart 탭 추가로 4개 이상
    w.close()


def test_main_window_tab_labels():
    from ui.main_window import MainWindow
    w = MainWindow()
    labels = [w.tabs.tabText(i) for i in range(w.tabs.count())]
    assert any("Main" in l for l in labels)
    assert any("Threshold" in l or "Filter" in l for l in labels)
    assert any("Process" in l or "Select" in l for l in labels)
    w.close()


def test_main_window_has_toolbar():
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.toolbar is not None
    w.close()


def test_main_window_has_statusbar():
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.status_bar is not None
    w.close()


def test_main_window_minimum_size():
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.minimumWidth()  >= 1280
    assert w.minimumHeight() >= 720
    w.close()
