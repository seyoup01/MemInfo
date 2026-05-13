"""STEP 7 검증: 정렬 기능 및 델타 시각화"""
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


def _all_procs(snap):
    """스냅샷의 모든 프로세스를 평탄화."""
    return [p for g in snap.adj_groups for p in g.processes]


# ── 정렬 로직 (utils/sorter) ──────────────────────────────────────────────────

def test_sorter_imports():
    from utils.sorter import SortKey, SortOrder, sort_snapshot
    assert SortKey is not None
    assert SortOrder is not None
    assert sort_snapshot is not None


def test_sort_memory_desc(sample_snapshot):
    from utils.sorter import SortKey, SortOrder, sort_snapshot
    sorted_snap = sort_snapshot(sample_snapshot, SortKey.MEMORY, SortOrder.DESC)
    mems = [p.memory_kb for p in _all_procs(sorted_snap)]
    assert mems == sorted(mems, reverse=True), \
        f"Memory 내림차순 정렬 실패: {mems}"


def test_sort_memory_asc(sample_snapshot):
    from utils.sorter import SortKey, SortOrder, sort_snapshot
    sorted_snap = sort_snapshot(sample_snapshot, SortKey.MEMORY, SortOrder.ASC)
    mems = [p.memory_kb for p in _all_procs(sorted_snap)]
    assert mems == sorted(mems), f"Memory 오름차순 정렬 실패: {mems}"


def test_sort_name_asc(sample_snapshot):
    from utils.sorter import SortKey, SortOrder, sort_snapshot
    sorted_snap = sort_snapshot(sample_snapshot, SortKey.NAME, SortOrder.ASC)
    names = [p.package_name.lower() for p in _all_procs(sorted_snap)]
    assert names == sorted(names), f"Name 오름차순 정렬 실패: {names}"


def test_sort_name_desc(sample_snapshot):
    from utils.sorter import SortKey, SortOrder, sort_snapshot
    sorted_snap = sort_snapshot(sample_snapshot, SortKey.NAME, SortOrder.DESC)
    names = [p.package_name.lower() for p in _all_procs(sorted_snap)]
    assert names == sorted(names, reverse=True), f"Name 내림차순 정렬 실패"


def test_sort_pid_asc(sample_snapshot):
    from utils.sorter import SortKey, SortOrder, sort_snapshot
    sorted_snap = sort_snapshot(sample_snapshot, SortKey.PID, SortOrder.ASC)
    pids = [p.pid for p in _all_procs(sorted_snap)]
    assert pids == sorted(pids), f"PID 오름차순 정렬 실패: {pids}"


def test_sort_pid_desc(sample_snapshot):
    from utils.sorter import SortKey, SortOrder, sort_snapshot
    sorted_snap = sort_snapshot(sample_snapshot, SortKey.PID, SortOrder.DESC)
    pids = [p.pid for p in _all_procs(sorted_snap)]
    assert pids == sorted(pids, reverse=True), f"PID 내림차순 정렬 실패"


def test_sort_adj_asc_group_order(sample_snapshot):
    from utils.sorter import SortKey, SortOrder, sort_snapshot
    from core.data_models import ADJ_ORDER
    sorted_snap = sort_snapshot(sample_snapshot, SortKey.ADJ, SortOrder.ASC)
    orders = [g.adj_order for g in sorted_snap.adj_groups]
    assert orders == sorted(orders), f"ADJ 오름차순 그룹 순서 실패: {orders}"


def test_sort_adj_desc_group_order(sample_snapshot):
    from utils.sorter import SortKey, SortOrder, sort_snapshot
    sorted_snap = sort_snapshot(sample_snapshot, SortKey.ADJ, SortOrder.DESC)
    orders = [g.adj_order for g in sorted_snap.adj_groups]
    assert orders == sorted(orders, reverse=True), "ADJ 내림차순 그룹 순서 실패"


def test_sort_adj_processes_sorted_by_memory_within_group(sample_snapshot):
    """ADJ 정렬 시 각 그룹 내 프로세스는 memory 내림차순이어야 함."""
    from utils.sorter import SortKey, SortOrder, sort_snapshot
    sorted_snap = sort_snapshot(sample_snapshot, SortKey.ADJ, SortOrder.ASC)
    for g in sorted_snap.adj_groups:
        if len(g.processes) > 1:
            mems = [p.memory_kb for p in g.processes]
            assert mems == sorted(mems, reverse=True), \
                f"{g.adj_category} 그룹 내 프로세스 정렬 실패: {mems}"


def test_sort_preserves_process_count(sample_snapshot):
    """정렬 후 전체 프로세스 수가 변하지 않아야 함."""
    from utils.sorter import SortKey, SortOrder, sort_snapshot
    original_count = sample_snapshot.total_process_count
    for key in SortKey:
        for order in SortOrder:
            sorted_snap = sort_snapshot(sample_snapshot, key, order)
            count = sum(len(g.processes) for g in sorted_snap.adj_groups)
            assert count == original_count, \
                f"{key}/{order} 정렬 후 프로세스 수 변화: {count} != {original_count}"


def test_sort_does_not_mutate_original(sample_snapshot):
    """sort_snapshot이 원본 스냅샷을 변경하지 않아야 함."""
    from utils.sorter import SortKey, SortOrder, sort_snapshot
    original_order = [g.adj_category for g in sample_snapshot.adj_groups]
    sort_snapshot(sample_snapshot, SortKey.MEMORY, SortOrder.DESC)
    after_order = [g.adj_category for g in sample_snapshot.adj_groups]
    assert original_order == after_order, "원본 스냅샷이 변형됨"


# ── MainView 정렬 UI ──────────────────────────────────────────────────────────

def test_main_view_default_sort_is_adj(sample_snapshot):
    from ui.main_view import MainView
    from utils.sorter import SortKey, SortOrder
    v = MainView()
    v.update_data(sample_snapshot)
    key, order = v.current_sort()
    assert key   == SortKey.ADJ
    assert order == SortOrder.ASC


def test_main_view_sort_changes_on_memory_column_click(sample_snapshot):
    """PSS(KB) 컬럼 헤더 클릭 → MEMORY ASC로 변경."""
    from ui.main_view import MainView, COL_PSS_KB
    from utils.sorter import SortKey, SortOrder
    v = MainView()
    v.update_data(sample_snapshot)
    v._on_header_clicked(COL_PSS_KB)
    key, order = v.current_sort()
    assert key   == SortKey.MEMORY
    assert order == SortOrder.ASC


def test_main_view_sort_cycles_asc_desc_default(sample_snapshot):
    """같은 컬럼 3번 클릭: ASC → DESC → ADJ(기본) 순환."""
    from ui.main_view import MainView, COL_PSS_KB
    from utils.sorter import SortKey, SortOrder
    v = MainView()
    v.update_data(sample_snapshot)

    v._on_header_clicked(COL_PSS_KB)          # 1클릭: MEMORY ASC
    assert v.current_sort() == (SortKey.MEMORY, SortOrder.ASC)

    v._on_header_clicked(COL_PSS_KB)          # 2클릭: MEMORY DESC
    assert v.current_sort() == (SortKey.MEMORY, SortOrder.DESC)

    v._on_header_clicked(COL_PSS_KB)          # 3클릭: 기본(ADJ ASC) 복원
    assert v.current_sort() == (SortKey.ADJ, SortOrder.ASC)


def test_main_view_sort_icon_shows_in_header(sample_snapshot):
    """정렬 중인 컬럼 헤더에 ▲ 또는 ▼ 아이콘이 있어야 함."""
    from ui.main_view import MainView, COL_PSS_KB
    v = MainView()
    v.update_data(sample_snapshot)
    v._on_header_clicked(COL_PSS_KB)          # MEMORY ASC
    header_text = v.tree.headerItem().text(COL_PSS_KB)
    assert "▲" in header_text, f"오름차순 아이콘 없음: '{header_text}'"

    v._on_header_clicked(COL_PSS_KB)          # MEMORY DESC
    header_text = v.tree.headerItem().text(COL_PSS_KB)
    assert "▼" in header_text, f"내림차순 아이콘 없음: '{header_text}'"


def test_main_view_memory_sort_renders_descending(sample_snapshot):
    """MEMORY DESC 정렬 후 트리의 전체 프로세스가 내림차순으로 렌더링되어야 함."""
    from ui.main_view import MainView, COL_PSS_KB, COL_ADJ
    from utils.sorter import SortKey, SortOrder
    v = MainView()
    v._sort_key   = SortKey.MEMORY
    v._sort_order = SortOrder.DESC
    v.update_data(sample_snapshot)

    # 플랫 그룹 하나로 렌더링됨
    assert v.tree.topLevelItemCount() == 1
    parent = v.tree.topLevelItem(0)
    mems = []
    for i in range(parent.childCount()):
        child = parent.child(i)
        mems.append(int(child.text(COL_PSS_KB).replace(",", "")))
    assert mems == sorted(mems, reverse=True), f"렌더링 순서 불일치: {mems}"


def test_main_view_adj_sort_renders_multiple_groups(sample_snapshot):
    """ADJ 정렬 시 여러 ADJ 그룹 헤더가 렌더링되어야 함."""
    from ui.main_view import MainView
    from utils.sorter import SortKey, SortOrder
    v = MainView()
    v._sort_key   = SortKey.ADJ
    v._sort_order = SortOrder.ASC
    v.update_data(sample_snapshot)
    assert v.tree.topLevelItemCount() == len(sample_snapshot.adj_groups)


# ── 델타 시각화 ───────────────────────────────────────────────────────────────

def test_delta_positive_shows_up_arrow(sample_snapshot):
    """delta_kb > 0 이면 Δ 셀에 ▲가 포함되어야 함."""
    from core.data_models import ProcessEntry
    from ui.main_view import MainView, COL_DELTA
    # 첫 프로세스의 delta_kb를 양수로 설정
    proc = sample_snapshot.adj_groups[0].processes[0]
    proc.prev_memory_kb = proc.memory_kb - 500
    assert proc.delta_kb == 500

    v = MainView()
    v.update_data(sample_snapshot)

    parent = v.tree.topLevelItem(0)
    child  = parent.child(0)
    assert "▲" in child.text(COL_DELTA), \
        f"▲ 없음: '{child.text(COL_DELTA)}'"


def test_delta_negative_shows_down_arrow(sample_snapshot):
    """delta_kb < 0 이면 Δ 셀에 ▼가 포함되어야 함."""
    from ui.main_view import MainView, COL_DELTA
    proc = sample_snapshot.adj_groups[0].processes[0]
    proc.prev_memory_kb = proc.memory_kb + 300
    assert proc.delta_kb == -300

    v = MainView()
    v.update_data(sample_snapshot)
    parent = v.tree.topLevelItem(0)
    child  = parent.child(0)
    assert "▼" in child.text(COL_DELTA), \
        f"▼ 없음: '{child.text(COL_DELTA)}'"


def test_delta_zero_shows_dash(sample_snapshot):
    """delta_kb == 0 이면 Δ 셀이 '-' 이어야 함."""
    from ui.main_view import MainView, COL_DELTA
    proc = sample_snapshot.adj_groups[0].processes[0]
    proc.prev_memory_kb = proc.memory_kb   # delta = 0

    v = MainView()
    v.update_data(sample_snapshot)
    parent = v.tree.topLevelItem(0)
    child  = parent.child(0)
    assert child.text(COL_DELTA) == "-", \
        f"delta=0 인데 '-' 아님: '{child.text(COL_DELTA)}'"


def test_new_process_row_has_green_background(sample_snapshot):
    """is_new=True 프로세스의 행 배경이 연두색(#E8F5E9)이어야 함."""
    from PyQt6.QtGui import QColor
    from ui.main_view import MainView, COL_PACKAGE
    proc = sample_snapshot.adj_groups[0].processes[0]
    proc.is_new = True

    v = MainView()
    v.update_data(sample_snapshot)
    parent = v.tree.topLevelItem(0)
    child  = parent.child(0)
    bg = child.background(COL_PACKAGE).color()
    assert bg == QColor("#E8F5E9"), f"신규 프로세스 배경색 불일치: {bg.name()}"


def test_gone_process_row_has_red_background(sample_snapshot):
    """is_gone=True 프로세스의 행 배경이 연빨간색(#FFEBEE)이어야 함."""
    from PyQt6.QtGui import QColor
    from ui.main_view import MainView, COL_PACKAGE
    proc = sample_snapshot.adj_groups[0].processes[0]
    proc.is_gone = True

    v = MainView()
    v.update_data(sample_snapshot)
    parent = v.tree.topLevelItem(0)
    child  = parent.child(0)
    bg = child.background(COL_PACKAGE).color()
    assert bg == QColor("#FFEBEE"), f"종료 프로세스 배경색 불일치: {bg.name()}"
