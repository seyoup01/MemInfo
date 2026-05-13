"""전체 통합 테스트: MockAdb → PollingWorker → HistoryManager → Export → Alert"""
import json
import os
import sys
import time

import pytest
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_meminfo.txt")


def test_full_flow(tmp_path):
    """
    1. MockAdbManager 기기 연결
    2. PollingWorker 1초 주기 3회 수집
    3. HistoryManager 저장
    4. AlertManager 임계값 40MB → 알림 발동 확인
    5. CSV/JSON 내보내기 파일 확인
    """
    from core.adb_manager import MockAdbManager
    from core.alert_manager import AlertManager
    from core.history_manager import HistoryManager
    from core.meminfo_parser import parse
    from core.polling_worker import PollingWorker
    from utils.exporter import Exporter

    # 1. 기기 연결
    mgr     = MockAdbManager()
    devices = mgr.get_devices()
    assert devices, "기기 목록이 비어 있음"
    serial = devices[0].serial
    assert mgr.test_connection(serial), "기기 연결 실패"

    # 2. PollingWorker 3회 수집
    received = []
    worker   = PollingWorker(mgr, parse, serial, interval_sec=1)
    worker.snapshot_ready.connect(lambda s: received.append(s))
    worker.start()

    deadline = time.time() + 5
    while time.time() < deadline and len(received) < 3:
        _app.processEvents()
        time.sleep(0.05)

    worker.stop()
    assert len(received) >= 3, f"3회 이상 수집 기대, 실제 {len(received)}회"

    # 3. HistoryManager 저장
    hm = HistoryManager(db_path=str(tmp_path / "hist.db"))
    for snap in received:
        hm.save_snapshot(snap)

    count = hm.record_count()
    assert count > 0, "히스토리에 레코드가 없음"

    # 4. AlertManager: com.kakao.talk(45000KB) > 40000KB → 발동
    alert_mgr = AlertManager(alert_sound=False)
    alert_mgr.set_rule("com.kakao.talk", threshold_kb=40_000)
    fired = alert_mgr.check_snapshot(received[0])
    assert "com.kakao.talk" in fired, "알림이 발동되지 않음"

    # 5. CSV/JSON 내보내기
    records  = hm.get_all_for_export()
    csv_path = str(tmp_path / "export.csv")
    json_path = str(tmp_path / "export.json")

    Exporter.export_csv(records, csv_path)
    Exporter.export_json(records, json_path)

    assert os.path.exists(csv_path),  "CSV 파일이 없음"
    assert os.path.exists(json_path), "JSON 파일이 없음"

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) == len(records)


def test_snapshot_pipeline_parses_correctly():
    """파싱 → 스냅샷 구조 검증."""
    from core.adb_manager import MockAdbManager
    from core.meminfo_parser import parse

    mgr  = MockAdbManager()
    raw  = mgr.run_meminfo("emulator-5554")
    snap = parse(raw, "emulator-5554")

    assert snap.total_process_count > 0
    assert snap.device_id == "emulator-5554"
    for g in snap.adj_groups:
        assert g.adj_category
        assert g.total_memory_kb >= 0
        for p in g.processes:
            assert p.package_name
            assert p.pid > 0
            assert p.memory_kb > 0


def test_threshold_filter_in_context():
    """ThresholdView가 실제 스냅샷으로 올바르게 필터링하는지 검증."""
    from core.adb_manager import MockAdbManager
    from core.meminfo_parser import parse
    from ui.threshold_view import ThresholdView

    mgr  = MockAdbManager()
    raw  = mgr.run_meminfo("emulator-5554")
    snap = parse(raw, "emulator-5554")

    tv = ThresholdView()
    tv._threshold_kb = 10_000   # 10MB 이상

    _, total, shown = tv._apply_filter(snap)
    assert shown < total, "필터 후 일부 프로세스가 제외되어야 함"
    for g in tv._apply_filter(snap)[0].adj_groups:
        for p in g.processes:
            assert p.memory_kb >= 10_000


def test_selection_view_with_real_snapshot():
    """SelectionView가 실제 스냅샷으로 목록을 올바르게 구성하는지 검증."""
    from core.adb_manager import MockAdbManager
    from core.meminfo_parser import parse
    from ui.selection_view import SelectionView

    mgr  = MockAdbManager()
    raw  = mgr.run_meminfo("emulator-5554")
    snap = parse(raw, "emulator-5554")

    sv = SelectionView()
    sv.update_data(snap)

    assert sv._list.count() == snap.total_process_count
    sv._select_all()
    assert len(sv.selected_packages) == snap.total_process_count


def test_chart_view_with_multiple_snapshots():
    """ChartView가 연속된 스냅샷 데이터를 누적하는지 검증."""
    from core.adb_manager import MockAdbManager
    from core.meminfo_parser import parse
    from ui.chart_view import ChartView

    mgr  = MockAdbManager()
    raw  = mgr.run_meminfo("emulator-5554")
    snap = parse(raw, "emulator-5554")

    chart = ChartView()
    chart.set_packages(["com.kakao.talk", "com.android.systemui"])

    for _ in range(10):
        chart.add_data_point(snap)

    assert len(chart._xs) == 10
    assert len(chart._ys["com.kakao.talk"]) == 10


def test_alert_manager_with_history(tmp_path):
    """수집된 스냅샷에 AlertManager를 적용하고 결과를 검증."""
    from core.adb_manager import MockAdbManager
    from core.alert_manager import AlertManager
    from core.history_manager import HistoryManager
    from core.meminfo_parser import parse

    mgr  = MockAdbManager()
    raw  = mgr.run_meminfo("emulator-5554")
    snap = parse(raw, "emulator-5554")

    hm = HistoryManager(db_path=str(tmp_path / "alert_hist.db"))
    hm.save_snapshot(snap)

    alert_mgr = AlertManager(alert_sound=False)
    alert_mgr.set_rule("com.android.systemui", threshold_kb=90_000)
    fired = alert_mgr.check_snapshot(snap)

    assert "com.android.systemui" in fired
    assert alert_mgr.rules()["com.android.systemui"].triggered is True

    records = hm.get_all_for_export()
    assert any(r["package"] == "com.android.systemui" for r in records)
