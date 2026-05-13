"""STEP 3 검증: ADB 매니저"""
import pytest
from core.adb_manager import AdbDevice, MockAdbManager, resolve_adb_path


# ── AdbDevice ─────────────────────────────────────────────────────────────────

def test_adb_device_fields():
    d = AdbDevice("R5CN12345", "SM-G998B", "online")
    assert d.serial == "R5CN12345"
    assert d.model == "SM-G998B"
    assert d.status == "online"


# ── MockAdbManager ────────────────────────────────────────────────────────────

def test_mock_get_devices_returns_list():
    mgr = MockAdbManager()
    devices = mgr.get_devices()
    assert isinstance(devices, list)
    assert len(devices) >= 1


def test_mock_device_has_required_fields():
    mgr = MockAdbManager()
    device = mgr.get_devices()[0]
    assert isinstance(device, AdbDevice)
    assert device.serial != ""
    assert device.model != ""
    assert device.status in ("online", "offline", "unauthorized")


def test_mock_run_meminfo_returns_nonempty_string():
    mgr = MockAdbManager()
    raw = mgr.run_meminfo("emulator-5554")
    assert isinstance(raw, str)
    assert len(raw) > 0


def test_mock_run_meminfo_contains_target_section():
    mgr = MockAdbManager()
    raw = mgr.run_meminfo("emulator-5554")
    assert "Total PSS by OOM adjustment:" in raw


def test_mock_test_connection_returns_bool():
    mgr = MockAdbManager()
    result = mgr.test_connection("emulator-5554")
    assert isinstance(result, bool)
    assert result is True


def test_mock_is_device_online_returns_bool():
    mgr = MockAdbManager()
    result = mgr.is_device_online("emulator-5554")
    assert isinstance(result, bool)
    assert result is True


def test_mock_run_meminfo_parseable():
    """Mock 출력이 실제 파서로 처리 가능한지 확인."""
    from core.meminfo_parser import parse
    mgr = MockAdbManager()
    raw = mgr.run_meminfo("emulator-5554")
    snap = parse(raw, "emulator-5554")
    assert snap.total_process_count > 0
    assert len(snap.adj_groups) > 0


# ── resolve_adb_path ──────────────────────────────────────────────────────────

def test_resolve_adb_path_returns_string_or_raises():
    """ADB 설치 여부와 무관하게 문자열 경로 또는 FileNotFoundError여야 함."""
    try:
        path = resolve_adb_path()
        assert isinstance(path, str)
        assert len(path) > 0
    except FileNotFoundError:
        pass  # ADB 미설치 환경에서는 정상 동작


def test_resolve_adb_path_never_returns_none():
    try:
        path = resolve_adb_path()
        assert path is not None
    except FileNotFoundError:
        pass


# ── AdbManager (실제 ADB 있는 경우만) ────────────────────────────────────────

def test_real_adb_manager_skips_if_no_adb():
    """실제 ADB가 없으면 skip, 있으면 get_devices()가 리스트를 반환하는지 확인."""
    try:
        resolve_adb_path()
    except FileNotFoundError:
        pytest.skip("ADB 없음 - Mock 모드로 진행 (정상)")

    from core.adb_manager import AdbManager
    mgr = AdbManager()
    devices = mgr.get_devices()
    assert isinstance(devices, list)
    # 기기가 연결된 경우 AdbDevice 타입인지 확인
    for d in devices:
        assert isinstance(d, AdbDevice)
        assert d.status in ("online", "offline", "unauthorized")
