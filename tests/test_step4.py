"""STEP 4 검증: 히스토리 매니저 및 설정 관리자"""
import os
import time
import tempfile
import pytest


# ── 공통 픽스처 ───────────────────────────────────────────────────────────────

@pytest.fixture
def sample_snapshot():
    """테스트용 MemInfoSnapshot (fixtures 파일 파싱)."""
    from core.meminfo_parser import parse
    fixture = os.path.join(
        os.path.dirname(__file__), "fixtures", "sample_meminfo.txt"
    )
    with open(fixture, encoding="utf-8") as f:
        raw = f.read()
    return parse(raw, "test_device")


@pytest.fixture
def tmp_db(tmp_path):
    """임시 DB 파일 경로."""
    return str(tmp_path / "test_history.db")


@pytest.fixture
def tmp_settings(tmp_path):
    """임시 설정 파일 경로."""
    return str(tmp_path / "test_settings.json")


# ── HistoryManager ────────────────────────────────────────────────────────────

def test_history_manager_creates_db(tmp_db):
    from core.history_manager import HistoryManager
    hm = HistoryManager(db_path=tmp_db)
    assert os.path.exists(tmp_db)


def test_history_manager_save_and_count(tmp_db, sample_snapshot):
    from core.history_manager import HistoryManager
    hm = HistoryManager(db_path=tmp_db)
    before = hm.record_count()
    hm.save_snapshot(sample_snapshot)
    after = hm.record_count()
    assert after > before
    assert after == sample_snapshot.total_process_count


def test_history_manager_auto_delete_on_overflow(tmp_db, sample_snapshot):
    """max_records=10, 11건 저장 → 10 이하 유지."""
    from core.history_manager import HistoryManager
    hm = HistoryManager(max_records=10, db_path=tmp_db)

    # 샘플에는 7개 프로세스 → 2회 저장 = 14건 → 10건으로 잘려야 함
    for i in range(2):
        snap = sample_snapshot
        snap.timestamp = time.time() + i
        hm.save_snapshot(snap)

    count = hm.record_count()
    assert count <= 10, f"자동 삭제 실패: {count}건 (max=10)"


def test_history_manager_auto_delete_exact(tmp_db, sample_snapshot):
    """max_records=10으로 20건 저장 시 정확히 10건 이하."""
    from core.history_manager import HistoryManager
    hm = HistoryManager(max_records=10, db_path=tmp_db)

    # 샘플 7개 프로세스 × 3회 = 21건 → 10건으로 압축
    for i in range(3):
        snap = sample_snapshot
        snap.timestamp = time.time() + i * 0.001
        hm.save_snapshot(snap)

    assert hm.record_count() <= 10


def test_get_snapshots_for_process_format(tmp_db, sample_snapshot):
    """반환 형식이 [(float, int), ...] 인지 확인."""
    from core.history_manager import HistoryManager
    hm = HistoryManager(db_path=tmp_db)
    hm.save_snapshot(sample_snapshot)
    history = hm.get_snapshots_for_process("com.kakao.talk")
    assert isinstance(history, list)
    assert len(history) > 0
    for item in history:
        assert len(item) == 2
        ts, mem = item
        assert isinstance(ts, float)
        assert isinstance(mem, int)


def test_get_snapshots_for_process_unknown_package(tmp_db, sample_snapshot):
    """없는 패키지는 빈 리스트 반환."""
    from core.history_manager import HistoryManager
    hm = HistoryManager(db_path=tmp_db)
    hm.save_snapshot(sample_snapshot)
    result = hm.get_snapshots_for_process("com.nonexistent.app")
    assert result == []


def test_get_all_for_export_returns_dicts(tmp_db, sample_snapshot):
    """내보내기용 데이터가 dict 리스트인지 확인."""
    from core.history_manager import HistoryManager
    hm = HistoryManager(db_path=tmp_db)
    hm.save_snapshot(sample_snapshot)
    records = hm.get_all_for_export()
    assert isinstance(records, list)
    assert len(records) > 0
    required_keys = {"device_id", "timestamp", "adj", "package", "pid", "memory_kb"}
    for rec in records:
        assert required_keys.issubset(rec.keys()), \
            f"필수 키 누락: {required_keys - rec.keys()}"


def test_clear_removes_all_records(tmp_db, sample_snapshot):
    from core.history_manager import HistoryManager
    hm = HistoryManager(db_path=tmp_db)
    hm.save_snapshot(sample_snapshot)
    assert hm.record_count() > 0
    hm.clear()
    assert hm.record_count() == 0


def test_record_count_empty_db(tmp_db):
    from core.history_manager import HistoryManager
    hm = HistoryManager(db_path=tmp_db)
    assert hm.record_count() == 0


# ── Settings ──────────────────────────────────────────────────────────────────

def test_settings_creates_file(tmp_settings):
    from utils.settings import Settings
    s = Settings(path=tmp_settings)
    assert os.path.exists(tmp_settings)


def test_settings_default_values(tmp_settings):
    from utils.settings import Settings, DEFAULTS
    s = Settings(path=tmp_settings)
    for key, expected in DEFAULTS.items():
        assert s.get(key) == expected, \
            f"기본값 불일치 [{key}]: 기대={expected}, 실제={s.get(key)}"


def test_settings_set_and_get(tmp_settings):
    from utils.settings import Settings
    s = Settings(path=tmp_settings)
    s.set("poll_interval_sec", 3)
    assert s.get("poll_interval_sec") == 3


def test_settings_persistence(tmp_settings):
    """재생성 후에도 이전 값이 유지되는지 확인."""
    from utils.settings import Settings
    s1 = Settings(path=tmp_settings)
    s1.set("poll_interval_sec", 2)
    s1.set("last_device", "R5CN99999")

    s2 = Settings(path=tmp_settings)
    assert s2.get("poll_interval_sec") == 2
    assert s2.get("last_device") == "R5CN99999"


def test_settings_reset_to_defaults(tmp_settings):
    from utils.settings import Settings, DEFAULTS
    s = Settings(path=tmp_settings)
    s.set("poll_interval_sec", 99)
    s.reset()
    assert s.get("poll_interval_sec") == DEFAULTS["poll_interval_sec"]


def test_settings_unknown_key_returns_none(tmp_settings):
    from utils.settings import Settings
    s = Settings(path=tmp_settings)
    assert s.get("nonexistent_key_xyz") is None


def test_settings_set_list_value(tmp_settings):
    """리스트 값도 JSON으로 저장/복원되는지 확인."""
    from utils.settings import Settings
    s1 = Settings(path=tmp_settings)
    s1.set("selected_packages", ["com.kakao.talk", "com.example.app"])

    s2 = Settings(path=tmp_settings)
    pkgs = s2.get("selected_packages")
    assert pkgs == ["com.kakao.talk", "com.example.app"]


def test_settings_set_dict_value(tmp_settings):
    """dict 값(alert_rules)도 저장/복원되는지 확인."""
    from utils.settings import Settings
    s1 = Settings(path=tmp_settings)
    rules = {"com.kakao.talk": 50000, "com.example.app": 100000}
    s1.set("alert_rules", rules)

    s2 = Settings(path=tmp_settings)
    assert s2.get("alert_rules") == rules


def test_settings_survives_corrupted_file(tmp_settings):
    """설정 파일이 손상되어도 기본값으로 복구되어야 함."""
    from utils.settings import Settings, DEFAULTS
    # 먼저 파일 생성
    s = Settings(path=tmp_settings)
    # 파일 내용을 손상
    with open(tmp_settings, "w") as f:
        f.write("{ INVALID JSON !!!")

    # 재로드 시 기본값으로 복구
    s2 = Settings(path=tmp_settings)
    assert s2.get("poll_interval_sec") == DEFAULTS["poll_interval_sec"]
