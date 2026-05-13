"""STEP 9 검증: 차트 뷰 및 알림 매니저"""
import copy
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


# ── AlertManager imports ──────────────────────────────────────────────────────

def test_alert_manager_imports():
    from core.alert_manager import AlertManager, AlertRule
    assert AlertManager is not None
    assert AlertRule is not None


# ── AlertManager 기본 동작 ────────────────────────────────────────────────────

def test_alert_fires_when_threshold_exceeded(sample_snapshot):
    """memory > threshold → 알림 발동."""
    from core.alert_manager import AlertManager
    mgr = AlertManager(alert_sound=False)
    # com.kakao.talk = 45000 KB, threshold 40000 → 초과
    mgr.set_rule("com.kakao.talk", threshold_kb=40_000)
    fired = mgr.check_snapshot(sample_snapshot)
    assert "com.kakao.talk" in fired


def test_alert_not_fired_when_below_threshold(sample_snapshot):
    """memory < threshold → 알림 없음."""
    from core.alert_manager import AlertManager
    mgr = AlertManager(alert_sound=False)
    # com.kakao.talk = 45000 KB, threshold 50000 → 미초과
    mgr.set_rule("com.kakao.talk", threshold_kb=50_000)
    fired = mgr.check_snapshot(sample_snapshot)
    assert "com.kakao.talk" not in fired


def test_alert_no_repeat_while_triggered(sample_snapshot):
    """triggered=True 상태에서 동일 스냅샷 재확인 → 재발 없음."""
    from core.alert_manager import AlertManager
    mgr = AlertManager(alert_sound=False)
    mgr.set_rule("com.kakao.talk", threshold_kb=40_000)
    mgr.check_snapshot(sample_snapshot)   # 1회 발동
    fired2 = mgr.check_snapshot(sample_snapshot)  # 재확인
    assert len(fired2) == 0, "같은 상태에서 재발동됨"


def test_alert_triggered_state(sample_snapshot):
    """초과 후 triggered=True 상태여야 함."""
    from core.alert_manager import AlertManager
    mgr = AlertManager(alert_sound=False)
    mgr.set_rule("com.kakao.talk", threshold_kb=40_000)
    mgr.check_snapshot(sample_snapshot)
    assert mgr.rules()["com.kakao.talk"].triggered is True


def test_alert_reset_on_significant_drop(sample_snapshot):
    """10% 이상 감소 시 triggered=False 리셋."""
    from core.alert_manager import AlertManager
    mgr = AlertManager(alert_sound=False)
    mgr.set_rule("com.kakao.talk", threshold_kb=40_000)

    # 1) 알림 발동 (45000 KB)
    mgr.check_snapshot(sample_snapshot)
    rule = mgr.rules()["com.kakao.talk"]
    assert rule.triggered is True
    last_alert = rule.last_alert_kb   # 45000

    # 2) 메모리를 90% 미만으로 낮춘 스냅샷 생성 (< 45000 * 0.9 = 40500)
    snap2 = copy.deepcopy(sample_snapshot)
    for g in snap2.adj_groups:
        for p in g.processes:
            if p.package_name == "com.kakao.talk":
                p.memory_kb = 30_000   # 40500 미만
    mgr.check_snapshot(snap2)

    assert mgr.rules()["com.kakao.talk"].triggered is False, \
        "10% 이상 감소 후 triggered가 리셋되지 않음"


def test_alert_no_reset_on_small_drop(sample_snapshot):
    """10% 미만 감소 시 triggered 유지."""
    from core.alert_manager import AlertManager
    mgr = AlertManager(alert_sound=False)
    mgr.set_rule("com.kakao.talk", threshold_kb=40_000)
    mgr.check_snapshot(sample_snapshot)   # 발동 (45000)

    # 45000 * 0.9 = 40500 → 40600은 아직 90% 이상
    snap2 = copy.deepcopy(sample_snapshot)
    for g in snap2.adj_groups:
        for p in g.processes:
            if p.package_name == "com.kakao.talk":
                p.memory_kb = 42_000   # > 40500
    mgr.check_snapshot(snap2)

    assert mgr.rules()["com.kakao.talk"].triggered is True


def test_alert_refires_after_reset(sample_snapshot):
    """리셋 후 다시 임계값 초과 → 재발동."""
    from core.alert_manager import AlertManager
    mgr = AlertManager(alert_sound=False)
    mgr.set_rule("com.kakao.talk", threshold_kb=40_000)

    # 1) 발동
    mgr.check_snapshot(sample_snapshot)

    # 2) 큰 폭 감소 → 리셋
    snap_low = copy.deepcopy(sample_snapshot)
    for g in snap_low.adj_groups:
        for p in g.processes:
            if p.package_name == "com.kakao.talk":
                p.memory_kb = 20_000
    mgr.check_snapshot(snap_low)
    assert mgr.rules()["com.kakao.talk"].triggered is False

    # 3) 다시 초과
    fired = mgr.check_snapshot(sample_snapshot)
    assert "com.kakao.talk" in fired, "리셋 후 재발동 실패"


def test_alert_remove_rule(sample_snapshot):
    """remove_rule() 후 해당 패키지 알림 없음."""
    from core.alert_manager import AlertManager
    mgr = AlertManager(alert_sound=False)
    mgr.set_rule("com.kakao.talk", threshold_kb=40_000)
    mgr.remove_rule("com.kakao.talk")
    fired = mgr.check_snapshot(sample_snapshot)
    assert "com.kakao.talk" not in fired


def test_alert_multiple_rules(sample_snapshot):
    """복수 규칙 동시 확인."""
    from core.alert_manager import AlertManager
    mgr = AlertManager(alert_sound=False)
    # com.kakao.talk(45000) > 40000 → 발동
    # com.android.systemui(98765) > 90000 → 발동
    mgr.set_rule("com.kakao.talk", threshold_kb=40_000)
    mgr.set_rule("com.android.systemui", threshold_kb=90_000)
    fired = mgr.check_snapshot(sample_snapshot)
    assert "com.kakao.talk" in fired
    assert "com.android.systemui" in fired


def test_alert_unknown_package_ignored(sample_snapshot):
    """스냅샷에 없는 패키지 규칙 → 알림 없음."""
    from core.alert_manager import AlertManager
    mgr = AlertManager(alert_sound=False)
    mgr.set_rule("com.nonexistent.app", threshold_kb=0)
    fired = mgr.check_snapshot(sample_snapshot)
    assert "com.nonexistent.app" not in fired


# ── AlertLogPanel ─────────────────────────────────────────────────────────────

def test_alert_log_panel_imports():
    from ui.alert_log_panel import AlertLogPanel
    assert AlertLogPanel is not None


def test_alert_log_add_alert():
    from ui.alert_log_panel import AlertLogPanel
    panel = AlertLogPanel()
    panel.add_alert("com.kakao.talk", 50_000, 40_000)
    assert panel.row_count() == 1


def test_alert_log_max_rows():
    """100건 초과 시 오래된 행 제거."""
    from ui.alert_log_panel import AlertLogPanel, _MAX_ROWS
    panel = AlertLogPanel()
    for i in range(_MAX_ROWS + 5):
        panel.add_alert(f"pkg{i}", i * 1000, 40_000)
    assert panel.row_count() == _MAX_ROWS


def test_alert_log_clear():
    from ui.alert_log_panel import AlertLogPanel
    panel = AlertLogPanel()
    panel.add_alert("com.test", 10_000, 5_000)
    panel._clear()
    assert panel.row_count() == 0


# ── ChartView ─────────────────────────────────────────────────────────────────

def test_chart_view_imports():
    from ui.chart_view import ChartView
    assert ChartView is not None


def test_chart_set_packages(sample_snapshot):
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.set_packages(["com.kakao.talk", "com.android.systemui"])
    assert chart._packages == ["com.kakao.talk", "com.android.systemui"]


def test_chart_set_packages_max_10():
    from ui.chart_view import ChartView, _MAX_PACKAGES
    chart = ChartView()
    pkgs = [f"com.pkg{i}" for i in range(15)]
    chart.set_packages(pkgs)
    assert len(chart._packages) == _MAX_PACKAGES


def test_chart_add_data_point_no_error(sample_snapshot):
    """add_data_point() 호출 시 예외 없어야 함."""
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.set_packages(["com.kakao.talk", "com.android.systemui"])
    chart.add_data_point(sample_snapshot)
    chart.add_data_point(sample_snapshot)
    assert len(chart._xs) == 2


def test_chart_data_accumulates(sample_snapshot):
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.set_packages(["com.kakao.talk"])
    for _ in range(5):
        chart.add_data_point(sample_snapshot)
    assert len(chart._xs) == 5
    assert len(chart._ys["com.kakao.talk"]) == 5


def test_chart_sample_count_limit(sample_snapshot):
    """sample_count 초과 시 오래된 데이터 제거."""
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.set_packages(["com.kakao.talk"])
    chart._sample_count = 3
    for _ in range(5):
        chart.add_data_point(sample_snapshot)
    assert len(chart._xs) == 3
    assert len(chart._ys["com.kakao.talk"]) == 3


def test_chart_clear(sample_snapshot):
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.set_packages(["com.kakao.talk"])
    chart.add_data_point(sample_snapshot)
    chart.clear()
    assert len(chart._xs) == 0


def test_chart_add_data_without_packages(sample_snapshot):
    """set_packages 없이 add_data_point → 예외 없음."""
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.add_data_point(sample_snapshot)   # should not raise


# ── 차트 Y축 0 이상 클램프 ───────────────────────────────────────────────────

def test_chart_view_y_axis_min_is_zero():
    """PSS 는 음수 없으므로 Y축 최소가 0 으로 제한되어야 한다."""
    from ui.chart_view import ChartView
    chart = ChartView()
    y_lim_min, _ = chart._vb.state["limits"]["yLimits"]
    assert y_lim_min == 0, f"yMin 클램프 미적용: {y_lim_min}"


def test_chart_update_curves_keeps_y_min_zero(sample_snapshot):
    """add_data_point 후에도 Y범위 하단이 0 이상이어야 한다."""
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.set_packages(["com.kakao.talk"])
    chart.add_data_point(sample_snapshot)
    y_range = chart._vb.viewRange()[1]   # [yMin, yMax]
    assert y_range[0] >= 0, f"Y축 하단이 음수: {y_range[0]}"


# ── 증분 set_packages 데이터 보존 ────────────────────────────────────────────

def test_chart_set_packages_incremental_preserves_data(sample_snapshot):
    """set_packages 로 패키지 일부만 바뀔 때 유지되는 패키지 데이터는 보존."""
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.set_packages(["com.kakao.talk", "com.android.systemui"])
    for _ in range(5):
        chart.add_data_point(sample_snapshot)

    assert len(chart._ys["com.kakao.talk"]) == 5
    assert len(chart._ys["com.android.systemui"]) == 5

    # com.android.systemui 제거 + com.example 추가
    chart.set_packages(["com.kakao.talk", "com.example"])

    assert "com.kakao.talk" in chart._curves
    assert "com.example" in chart._curves
    assert "com.android.systemui" not in chart._curves, "제거된 패키지 곡선 남음"
    assert len(chart._ys["com.kakao.talk"]) == 5, "유지된 패키지 데이터 손실됨"
    assert "com.android.systemui" not in chart._ys
    assert len(chart._ys["com.example"]) == 0


# ── SelectionView selection_changed 시그널 ───────────────────────────────────

def test_selection_view_emits_selection_changed_on_select_all(sample_snapshot):
    """전체 선택 → selection_changed 발생, 전체 패키지 포함."""
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv.update_data(sample_snapshot)

    received = []
    sv.selection_changed.connect(lambda pkgs: received.append(list(pkgs)))
    sv._select_all()

    assert received, "selection_changed 시그널 미발생"
    assert len(received[-1]) == sample_snapshot.total_process_count


def test_selection_view_emits_selection_changed_on_clear(sample_snapshot):
    """초기화 → selection_changed 가 빈 리스트로 발생."""
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv.update_data(sample_snapshot)
    sv._select_all()

    received = []
    sv.selection_changed.connect(lambda pkgs: received.append(list(pkgs)))
    sv._clear_selection()

    assert received and received[-1] == [], f"빈 리스트 기대, 실제 {received}"


def test_selection_view_emits_selection_changed_on_toggle(sample_snapshot):
    """체크박스 토글 시 selection_changed 발생."""
    from PyQt6.QtCore import Qt
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv.update_data(sample_snapshot)

    received = []
    sv.selection_changed.connect(lambda pkgs: received.append(list(pkgs)))
    # 첫 항목 체크
    item = sv._list.item(0)
    item.setCheckState(Qt.CheckState.Checked)

    assert received, "체크박스 토글 시 selection_changed 미발생"
    assert item.text() in received[-1]


# ── MainWindow 자동 동기화 ───────────────────────────────────────────────────

def test_main_window_selection_change_updates_chart(sample_snapshot):
    """SelectionView 의 선택 변경이 ChartView 패키지 목록에 즉시 반영된다."""
    from ui.main_window import MainWindow
    w = MainWindow()
    w.selection_view.update_data(sample_snapshot)

    assert w.chart_view._packages == [], "초기 chart_view._packages 비어있어야 함"

    w.selection_view._select_all()
    assert w.chart_view._packages, "선택 변경 후 chart_view 가 갱신되지 않음"
    # 최대 10개로 제한되므로 min(전체, 10) 만큼 동기화
    expected_count = min(sample_snapshot.total_process_count, 10)
    assert len(w.chart_view._packages) == expected_count


# ── Chart Y축 콤마 포맷 / SI prefix 차단 ─────────────────────────────────────

def test_chart_y_axis_uses_comma_format():
    """_KbAxisItem.tickStrings 가 콤마 구분 정수를 반환해야 한다."""
    from ui.chart_view import _KbAxisItem
    axis = _KbAxisItem(orientation="left")
    result = axis.tickStrings([1000, 200000, 1234567], 1, 1)
    assert result == ["1,000", "200,000", "1,234,567"], f"포맷 불일치: {result}"


def test_chart_y_axis_auto_si_prefix_disabled():
    """좌측 Y축의 autoSIPrefix 가 비활성화되어 1e+06 표기 차단."""
    from ui.chart_view import ChartView
    chart = ChartView()
    left_axis = chart._plot.getAxis("left")
    assert left_axis.autoSIPrefix is False


# ── Chart 슬라이더 제거 ──────────────────────────────────────────────────────

def test_chart_view_has_no_sample_count_slider():
    """'표시 범위' 슬라이더와 샘플 카운트 라벨이 제거되어야 한다."""
    from ui.chart_view import ChartView
    chart = ChartView()
    assert not hasattr(chart, "_slider")
    assert not hasattr(chart, "_lbl_samples")


def test_chart_view_sample_count_attribute_persists():
    """슬라이더 제거 후에도 _sample_count 속성은 유지 (직접 세팅으로 제어)."""
    from ui.chart_view import ChartView, _DEFAULT_SAMPLES
    chart = ChartView()
    assert chart._sample_count == _DEFAULT_SAMPLES


# ── Chart 패키지명 라벨 + 토글 ───────────────────────────────────────────────

def test_chart_has_label_toggle_checkbox():
    """패키지명 표시 토글 체크박스가 존재하고 기본 ON."""
    from ui.chart_view import ChartView
    chart = ChartView()
    assert hasattr(chart, "_chk_labels")
    assert chart._chk_labels.isChecked() is True


def test_chart_creates_text_label_per_package():
    """set_packages 후 패키지마다 TextItem 라벨이 생성된다."""
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.set_packages(["com.kakao.talk", "com.android.systemui"])
    assert len(chart._labels) == 2
    assert "com.kakao.talk" in chart._labels
    assert "com.android.systemui" in chart._labels


def test_chart_text_label_position_follows_last_point(sample_snapshot):
    """add_data_point 후 라벨이 마지막 (x, y) 위치로 이동."""
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.set_packages(["com.kakao.talk"])
    chart.add_data_point(sample_snapshot)

    last_x = chart._xs[-1]
    last_y = chart._ys["com.kakao.talk"][-1]
    pos = chart._labels["com.kakao.talk"].pos()
    assert pos.x() == last_x
    assert pos.y() == last_y


def test_chart_toggle_hides_text_labels():
    """토글 OFF 시 모든 라벨이 비가시 상태."""
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.set_packages(["com.kakao.talk", "com.android.systemui"])

    chart._chk_labels.setChecked(False)
    for label in chart._labels.values():
        assert label.isVisible() is False

    chart._chk_labels.setChecked(True)
    for label in chart._labels.values():
        assert label.isVisible() is True


def test_chart_removes_label_when_package_dropped():
    """set_packages 로 빠진 패키지의 TextItem 도 함께 제거."""
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.set_packages(["com.a", "com.b"])
    assert "com.b" in chart._labels

    chart.set_packages(["com.a"])
    assert "com.b" not in chart._labels


# ── Chart 합계 라벨 ──────────────────────────────────────────────────────────

def test_chart_sum_label_initially_zero():
    """초기 합계 라벨은 '0 KB'."""
    from ui.chart_view import ChartView
    chart = ChartView()
    assert "0" in chart._lbl_chart_sum.text()


def test_chart_sum_label_updates_with_data(sample_snapshot):
    """add_data_point 후 차트 합계가 콤마 포맷으로 표시된다."""
    from ui.chart_view import ChartView
    chart = ChartView()
    chart.set_packages(["com.kakao.talk", "com.android.systemui"])
    chart.add_data_point(sample_snapshot)

    # 샘플: com.kakao.talk=45000, com.android.systemui=98765 → 합계 143,765
    expected = (
        chart._ys["com.kakao.talk"][-1]
        + chart._ys["com.android.systemui"][-1]
    )
    text = chart._lbl_chart_sum.text()
    assert f"{expected:,}" in text, f"합계 라벨: {text}"


# ── MainWindow 연결 ──────────────────────────────────────────────────────────

def test_main_window_has_chart_view():
    from ui.main_window import MainWindow
    from ui.chart_view import ChartView
    w = MainWindow()
    assert isinstance(w.chart_view, ChartView)


def test_main_window_has_alert_manager():
    from ui.main_window import MainWindow
    from core.alert_manager import AlertManager
    w = MainWindow()
    assert isinstance(w._alert_manager, AlertManager)


def test_main_window_has_alert_log():
    from ui.main_window import MainWindow
    from ui.alert_log_panel import AlertLogPanel
    w = MainWindow()
    assert isinstance(w.alert_log, AlertLogPanel)


def test_main_window_4_tabs():
    from ui.main_window import MainWindow
    w = MainWindow()
    assert w.tabs.count() == 4
