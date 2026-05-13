"""STEP 8 검증: 임계값 필터 뷰 및 프로세스 선택 뷰"""
import copy
import json
import os
import sys

import pytest
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_meminfo.txt")


@pytest.fixture
def sample_snapshot():
    from core.meminfo_parser import parse
    with open(FIXTURE, encoding="utf-8") as f:
        return parse(f.read(), "test_device")


# ── ThresholdView import ──────────────────────────────────────────────────────

def test_threshold_view_imports():
    from ui.threshold_view import ThresholdView
    assert ThresholdView is not None


# ── ThresholdView 기본값 ──────────────────────────────────────────────────────

def test_threshold_default_is_50000():
    from ui.threshold_view import ThresholdView
    tv = ThresholdView()
    assert tv.threshold_kb == 50_000


def test_threshold_spin_initial_value():
    from ui.threshold_view import ThresholdView
    tv = ThresholdView()
    assert tv._spin.value() == 50_000


# ── ThresholdView 필터 로직 ──────────────────────────────────────────────────

def test_threshold_filter_50000_shows_one_process(sample_snapshot):
    """threshold=50000 → 98765KB 프로세스(com.android.systemui)만 통과."""
    from ui.threshold_view import ThresholdView
    tv = ThresholdView()
    tv._threshold_kb = 50_000
    _, total, shown = tv._apply_filter(sample_snapshot)
    assert total == sample_snapshot.total_process_count
    assert shown == 1


def test_threshold_filter_50000_correct_process(sample_snapshot):
    """threshold=50000 → 통과한 프로세스가 98765KB 이상이어야 함."""
    from ui.threshold_view import ThresholdView
    tv = ThresholdView()
    tv._threshold_kb = 50_000
    filtered, _, _ = tv._apply_filter(sample_snapshot)
    for g in filtered.adj_groups:
        for p in g.processes:
            assert p.memory_kb >= 50_000, f"{p.package_name}: {p.memory_kb} < 50000"


def test_threshold_filter_zero_shows_all(sample_snapshot):
    """threshold=0 → 전체 프로세스 표시."""
    from ui.threshold_view import ThresholdView
    tv = ThresholdView()
    tv._threshold_kb = 0
    _, total, shown = tv._apply_filter(sample_snapshot)
    assert shown == total == sample_snapshot.total_process_count


def test_threshold_filter_very_high_shows_none(sample_snapshot):
    """threshold=999999999 → 표시되는 프로세스 없음."""
    from ui.threshold_view import ThresholdView
    tv = ThresholdView()
    tv._threshold_kb = 999_999_999
    _, _, shown = tv._apply_filter(sample_snapshot)
    assert shown == 0


def test_threshold_filter_10000_shows_three(sample_snapshot):
    """threshold=10000 → 98765, 45000, 12000KB 3개 통과."""
    from ui.threshold_view import ThresholdView
    tv = ThresholdView()
    tv._threshold_kb = 10_000
    _, _, shown = tv._apply_filter(sample_snapshot)
    assert shown == 3


# ── ThresholdView update_data ─────────────────────────────────────────────────

def test_threshold_update_data_renders(sample_snapshot):
    """update_data() 호출 후 내부 MainView에 데이터가 표시되어야 함."""
    from ui.threshold_view import ThresholdView
    tv = ThresholdView()
    tv._threshold_kb = 0   # 전체 표시
    tv.update_data(sample_snapshot)
    total_rows = sum(
        tv._view.tree.topLevelItem(i).childCount()
        for i in range(tv._view.tree.topLevelItemCount())
    )
    assert total_rows == sample_snapshot.total_process_count


def test_threshold_update_data_count_label(sample_snapshot):
    """update_data() 후 결과 레이블에 숫자가 반영되어야 함."""
    from ui.threshold_view import ThresholdView
    tv = ThresholdView()
    tv._threshold_kb = 50_000
    tv.update_data(sample_snapshot)
    lbl = tv._lbl_count.text()
    assert "1" in lbl and "7" in lbl, f"레이블 오류: '{lbl}'"


# ── ThresholdView 단위 전환 ───────────────────────────────────────────────────

def test_threshold_unit_toggle_kb_to_mb():
    """KB→MB 전환: spin이 MB 단위로 바뀌어야 함."""
    from ui.threshold_view import ThresholdView
    tv = ThresholdView()
    tv._threshold_kb = 51_200   # 50 MB
    tv._rb_mb.setChecked(True)
    assert tv._unit == "MB"
    assert tv._spin.value() == 50   # 51200 // 1024 = 50


def test_threshold_unit_set_50mb():
    """MB 모드에서 spin=50 → threshold_kb = 51200."""
    from ui.threshold_view import ThresholdView
    tv = ThresholdView()
    tv._rb_mb.setChecked(True)
    tv._spin.setValue(50)
    assert tv.threshold_kb == 50 * 1024


def test_threshold_unit_toggle_mb_to_kb():
    """MB→KB 전환: spin이 KB 단위로 바뀌어야 함."""
    from ui.threshold_view import ThresholdView
    tv = ThresholdView()
    tv._rb_mb.setChecked(True)   # KB→MB
    tv._spin.setValue(100)        # 100 MB
    tv._rb_kb.setChecked(True)   # MB→KB
    assert tv._unit == "KB"
    assert tv.threshold_kb == 100 * 1024


# ── SelectionView import ──────────────────────────────────────────────────────

def test_selection_view_imports():
    from ui.selection_view import SelectionView
    assert SelectionView is not None


# ── SelectionView 초기 상태 ───────────────────────────────────────────────────

def test_selection_initially_empty():
    from ui.selection_view import SelectionView
    sv = SelectionView()
    assert sv.selected_packages == []


def test_selection_list_empty_before_update():
    from ui.selection_view import SelectionView
    sv = SelectionView()
    assert sv._list.count() == 0


# ── SelectionView update_data ─────────────────────────────────────────────────

def test_selection_update_data_populates_list(sample_snapshot):
    """update_data() 후 왼쪽 목록에 모든 프로세스가 표시되어야 함."""
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv.update_data(sample_snapshot)
    assert sv._list.count() == sample_snapshot.total_process_count


def test_selection_update_data_all_unchecked(sample_snapshot):
    """최초 update_data() 시 체크박스는 모두 해제 상태여야 함."""
    from PyQt6.QtCore import Qt
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv.update_data(sample_snapshot)
    for i in range(sv._list.count()):
        assert sv._list.item(i).checkState() == Qt.CheckState.Unchecked


def test_selection_all_procs_populated(sample_snapshot):
    """update_data() 후 _all_procs에 프로세스가 채워져야 함."""
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv.update_data(sample_snapshot)
    assert len(sv._all_procs) == sample_snapshot.total_process_count


# ── SelectionView 선택 기능 ───────────────────────────────────────────────────

def test_selection_select_all(sample_snapshot):
    """전체 선택 후 selected_packages 수 = 전체 프로세스 수."""
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv.update_data(sample_snapshot)
    sv._select_all()
    assert len(sv.selected_packages) == sample_snapshot.total_process_count


def test_selection_select_none(sample_snapshot):
    """전체 해제 후 selected_packages가 비어야 함."""
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv.update_data(sample_snapshot)
    sv._select_all()
    sv._select_none()
    assert sv.selected_packages == []


def test_selection_selected_packages_sorted():
    """selected_packages 결과가 정렬된 리스트여야 함."""
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv._selected_packages = {"zzz.app", "aaa.app", "mmm.app"}
    pkgs = sv.selected_packages
    assert pkgs == sorted(pkgs)


# ── SelectionView 종료 프로세스 추적 ──────────────────────────────────────────

def test_selection_gone_process_tracked(sample_snapshot):
    """선택된 프로세스가 새 스냅샷에 없으면 _gone_procs에 기록되어야 함."""
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv.update_data(sample_snapshot)

    first_proc = sample_snapshot.adj_groups[0].processes[0]
    pkg = first_proc.package_name
    sv._selected_packages.add(pkg)

    # 해당 프로세스 제거한 새 스냅샷
    snap2 = copy.deepcopy(sample_snapshot)
    snap2.adj_groups[0].processes = [
        p for p in snap2.adj_groups[0].processes if p.package_name != pkg
    ]
    sv.update_data(snap2)

    assert pkg in sv._gone_procs, f"{pkg}가 _gone_procs에 없음"


def test_selection_gone_process_shows_in_table(sample_snapshot):
    """종료된 프로세스가 오른쪽 테이블에 '종료됨' 상태로 표시되어야 함."""
    from ui.selection_view import SelectionView, _COL_STATUS
    sv = SelectionView()
    sv.update_data(sample_snapshot)

    first_proc = sample_snapshot.adj_groups[0].processes[0]
    pkg = first_proc.package_name
    sv._selected_packages.add(pkg)

    snap2 = copy.deepcopy(sample_snapshot)
    snap2.adj_groups[0].processes = [
        p for p in snap2.adj_groups[0].processes if p.package_name != pkg
    ]
    sv.update_data(snap2)

    # 테이블에서 해당 행 찾기
    found = False
    for row in range(sv._table.rowCount()):
        if sv._table.item(row, 0) and sv._table.item(row, 0).text() == pkg:
            status = sv._table.item(row, _COL_STATUS).text()
            assert status == "종료됨", f"상태가 '종료됨'이 아님: '{status}'"
            found = True
    assert found, f"{pkg} 행이 테이블에 없음"


def test_selection_restarted_process_badge(sample_snapshot):
    """사라졌다가 재등장한 프로세스에 '재시작됨' 배지가 달려야 함."""
    from ui.selection_view import SelectionView, _COL_STATUS
    sv = SelectionView()
    sv.update_data(sample_snapshot)

    first_proc = sample_snapshot.adj_groups[0].processes[0]
    pkg = first_proc.package_name
    sv._selected_packages.add(pkg)

    # 1) 사라짐
    snap2 = copy.deepcopy(sample_snapshot)
    snap2.adj_groups[0].processes = [
        p for p in snap2.adj_groups[0].processes if p.package_name != pkg
    ]
    sv.update_data(snap2)
    assert pkg in sv._gone_procs

    # 2) 재등장 (원본 스냅샷)
    sv.update_data(sample_snapshot)
    assert pkg not in sv._gone_procs, "재등장 후 gone_procs에서 제거되어야 함"

    # 테이블에서 재시작됨 배지 확인
    for row in range(sv._table.rowCount()):
        if sv._table.item(row, 0) and sv._table.item(row, 0).text() == pkg:
            status = sv._table.item(row, _COL_STATUS).text()
            assert status == "재시작됨", f"재시작 배지 없음: '{status}'"
            break


# ── SelectionView JSON 저장/불러오기 ──────────────────────────────────────────

def test_selection_json_format(tmp_path):
    """저장 JSON 포맷이 {"packages": [...]} 이어야 함."""
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv._selected_packages = {"com.kakao.talk", "com.example.app"}

    path = str(tmp_path / "sel.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"packages": sv.selected_packages}, f, ensure_ascii=False)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    assert "packages" in data
    assert set(data["packages"]) == {"com.kakao.talk", "com.example.app"}


def test_selection_load_sets_packages(tmp_path, sample_snapshot):
    """JSON 파일 로드 후 _selected_packages가 올바르게 설정되어야 함."""
    from ui.selection_view import SelectionView
    sv = SelectionView()
    sv.update_data(sample_snapshot)

    pkgs = ["com.kakao.talk", "com.example.launcher"]
    path = str(tmp_path / "sel.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"packages": pkgs}, f)

    # 파일 다이얼로그 없이 직접 로드 로직만 검증
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    sv._selected_packages = set(data.get("packages", []))
    sv._refresh_list()
    sv._refresh_table()

    assert set(sv.selected_packages) == set(pkgs)


# ── MainWindow 연결 확인 ──────────────────────────────────────────────────────

def test_main_window_has_threshold_view():
    from ui.main_window import MainWindow
    from ui.threshold_view import ThresholdView
    w = MainWindow()
    assert isinstance(w.threshold_view, ThresholdView)


def test_main_window_has_selection_view():
    from ui.main_window import MainWindow
    from ui.selection_view import SelectionView
    w = MainWindow()
    assert isinstance(w.selection_view, SelectionView)


def test_main_window_threshold_tab_is_real(sample_snapshot):
    """Threshold 탭이 QLabel 플레이스홀더가 아닌 실제 뷰여야 함."""
    from PyQt6.QtWidgets import QLabel
    from ui.main_window import MainWindow
    w = MainWindow()
    threshold_widget = w.tabs.widget(1)
    assert not isinstance(threshold_widget, QLabel), \
        "Threshold 탭이 아직 QLabel 플레이스홀더임"
