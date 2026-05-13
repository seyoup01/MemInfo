"""STEP 6 검증: 메인 모니터링 뷰 및 PollingWorker"""
import os
import sys
import time
import pytest

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

_app = QApplication.instance() or QApplication(sys.argv)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_meminfo.txt")


@pytest.fixture
def sample_snapshot():
    from core.meminfo_parser import parse
    with open(FIXTURE, encoding="utf-8") as f:
        return parse(f.read(), "test_device")


# ── MainView 렌더링 ───────────────────────────────────────────────────────────

def test_main_view_imports():
    from ui.main_view import MainView
    assert MainView is not None


def test_main_view_top_level_count(sample_snapshot):
    """ADJ 그룹 헤더 수 = snapshot.adj_groups 수."""
    from ui.main_view import MainView
    view = MainView()
    view.update_data(sample_snapshot)
    assert view.tree.topLevelItemCount() == len(sample_snapshot.adj_groups), \
        f"기대: {len(sample_snapshot.adj_groups)}, 실제: {view.tree.topLevelItemCount()}"


def test_main_view_child_count_per_group(sample_snapshot):
    """각 ADJ 그룹의 자식 수 = 해당 그룹의 프로세스 수."""
    from ui.main_view import MainView
    view = MainView()
    view.update_data(sample_snapshot)

    for i, group in enumerate(sample_snapshot.adj_groups):
        top = view.tree.topLevelItem(i)
        assert top.childCount() == len(group.processes), \
            f"{group.adj_category}: 기대 {len(group.processes)}개, 실제 {top.childCount()}개"


def test_main_view_no_duplicate_on_double_update(sample_snapshot):
    """update_data() 2회 연속 호출 시 중복 행이 생기지 않아야 함."""
    from ui.main_view import MainView
    view = MainView()
    view.update_data(sample_snapshot)
    view.update_data(sample_snapshot)
    assert view.tree.topLevelItemCount() == len(sample_snapshot.adj_groups)


def test_main_view_total_process_rows(sample_snapshot):
    """전체 프로세스 행 수 = total_process_count."""
    from ui.main_view import MainView
    view = MainView()
    view.update_data(sample_snapshot)

    total = sum(
        view.tree.topLevelItem(i).childCount()
        for i in range(view.tree.topLevelItemCount())
    )
    assert total == sample_snapshot.total_process_count


def test_main_view_header_has_adj_name(sample_snapshot):
    """ADJ 헤더 행에 카테고리명이 포함되어야 함."""
    from ui.main_view import MainView
    view = MainView()
    view.update_data(sample_snapshot)

    for i, group in enumerate(sample_snapshot.adj_groups):
        header = view.tree.topLevelItem(i)
        assert group.adj_category in header.text(0), \
            f"{group.adj_category} 이름이 헤더 텍스트에 없음: '{header.text(0)}'"


def test_main_view_process_row_columns(sample_snapshot):
    """프로세스 행의 Package Name, PID 컬럼이 채워져 있어야 함."""
    from ui.main_view import MainView, COL_PACKAGE, COL_PID
    view = MainView()
    view.update_data(sample_snapshot)

    for i in range(view.tree.topLevelItemCount()):
        parent = view.tree.topLevelItem(i)
        for j in range(parent.childCount()):
            child = parent.child(j)
            assert child.text(COL_PACKAGE) != "", f"Package Name 비어있음 (row {i},{j})"
            assert child.text(COL_PID) != "",     f"PID 비어있음 (row {i},{j})"


def test_main_view_collapse_tracking(sample_snapshot):
    """그룹 접기 상태가 collapsed_groups에 기록되는지 확인."""
    from ui.main_view import MainView
    view = MainView()
    view.update_data(sample_snapshot)

    # 첫 번째 그룹 접기
    first_cat = sample_snapshot.adj_groups[0].adj_category
    view.collapsed_groups.add(first_cat)

    # 재 렌더링 후 해당 그룹이 접혀있는지
    view.update_data(sample_snapshot)
    top = view.tree.topLevelItem(0)
    assert not top.isExpanded(), f"{first_cat} 그룹이 접혀있어야 하는데 펼쳐짐"


def test_main_view_update_with_empty_snapshot():
    """빈 스냅샷으로 update_data() 호출 시 예외 없이 빈 트리 표시."""
    from ui.main_view import MainView
    from core.data_models import MemInfoSnapshot
    view = MainView()
    empty = MemInfoSnapshot("test", time.time())
    view.update_data(empty)
    assert view.tree.topLevelItemCount() == 0


# ── PollingWorker ─────────────────────────────────────────────────────────────

def test_polling_worker_imports():
    from core.polling_worker import PollingWorker, compute_delta
    assert PollingWorker is not None
    assert compute_delta is not None


def test_polling_worker_emits_snapshots():
    """1초 주기로 5초간 실행 → 최소 3회 이상 수신."""
    from core.polling_worker import PollingWorker
    from core.adb_manager import MockAdbManager
    from core.meminfo_parser import parse

    received = []
    loop_done = [False]

    mgr = MockAdbManager()
    worker = PollingWorker(mgr, parse, "emulator-5554", 1)
    worker.snapshot_ready.connect(lambda snap: received.append(snap))

    worker.start()

    # Qt 이벤트 루프를 5초간 돌려 시그널 수신
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: setattr(timer, '_done', True))
    timer.start(5000)

    deadline = time.time() + 6
    while time.time() < deadline:
        _app.processEvents()
        if getattr(timer, '_done', False):
            break
        time.sleep(0.05)

    worker.stop()

    assert len(received) >= 3, \
        f"5초/1초 주기 실행에서 최소 3회 기대, 실제 {len(received)}회"


def test_polling_worker_snapshot_has_processes():
    """수신된 스냅샷에 프로세스가 포함되어 있어야 함."""
    from core.polling_worker import PollingWorker
    from core.adb_manager import MockAdbManager
    from core.meminfo_parser import parse

    received = []
    mgr = MockAdbManager()
    worker = PollingWorker(mgr, parse, "emulator-5554", 1)
    worker.snapshot_ready.connect(lambda snap: received.append(snap))
    worker.start()

    deadline = time.time() + 3
    while time.time() < deadline and not received:
        _app.processEvents()
        time.sleep(0.05)

    worker.stop()

    assert received, "스냅샷을 한 번도 수신하지 못함"
    assert received[0].total_process_count > 0


def test_polling_worker_stop_within_2s():
    """stop() 호출 후 2초 내에 스레드가 종료되어야 함."""
    from core.polling_worker import PollingWorker
    from core.adb_manager import MockAdbManager
    from core.meminfo_parser import parse

    mgr = MockAdbManager()
    worker = PollingWorker(mgr, parse, "emulator-5554", 5)
    worker.start()
    time.sleep(0.2)   # 워커가 첫 폴링에 진입하도록 잠시 대기

    t0 = time.time()
    worker.stop()
    elapsed = time.time() - t0

    assert not worker.isRunning(), "stop() 후에도 스레드가 실행 중"
    assert elapsed < 2.5, f"stop()에 {elapsed:.1f}초 소요 (2초 초과)"


def test_compute_delta_marks_new_process():
    """이전 스냅샷에 없는 프로세스는 is_new=True 여야 함."""
    from core.polling_worker import compute_delta
    from core.meminfo_parser import parse
    import copy

    with open(FIXTURE, encoding="utf-8") as f:
        raw = f.read()

    snap1 = parse(raw, "test")
    snap2 = parse(raw, "test")

    # snap2에 새 프로세스 추가
    from core.data_models import ProcessEntry
    new_proc = ProcessEntry("Foreground", 4, 9999, "com.brand.new", 7777)
    snap2.adj_groups[2].processes.append(new_proc)

    result = compute_delta(snap2, prev=snap1)

    new_procs = [
        p for g in result.adj_groups for p in g.processes if p.is_new
    ]
    assert any(p.package_name == "com.brand.new" for p in new_procs), \
        "신규 프로세스가 is_new=True로 표시되지 않음"


def test_compute_delta_marks_gone_process():
    """이전 스냅샷에 있었으나 현재 없는 프로세스는 is_gone=True 여야 함."""
    from core.polling_worker import compute_delta
    from core.meminfo_parser import parse

    with open(FIXTURE, encoding="utf-8") as f:
        raw = f.read()

    snap1 = parse(raw, "test")
    snap2 = parse(raw, "test")

    # snap2에서 첫 번째 그룹의 첫 번째 프로세스 제거
    removed_pkg = snap2.adj_groups[0].processes.pop(0).package_name

    result = compute_delta(snap2, prev=snap1)

    gone_procs = [
        p for g in result.adj_groups for p in g.processes if p.is_gone
    ]
    assert any(p.package_name == removed_pkg for p in gone_procs), \
        f"{removed_pkg}가 is_gone=True로 표시되지 않음"


def test_compute_delta_prev_memory_kb():
    """기존 프로세스의 prev_memory_kb가 이전 스냅샷 값으로 설정되어야 함."""
    from core.polling_worker import compute_delta
    from core.meminfo_parser import parse

    with open(FIXTURE, encoding="utf-8") as f:
        raw = f.read()

    snap1 = parse(raw, "test")
    snap2 = parse(raw, "test")

    # snap2의 첫 프로세스 메모리를 인위적으로 변경
    proc2 = snap2.adj_groups[0].processes[0]
    proc2.memory_kb = proc2.memory_kb + 500

    result = compute_delta(snap2, prev=snap1)

    # 변경된 프로세스의 prev_memory_kb 확인
    changed = next(
        p for g in result.adj_groups for p in g.processes
        if p.package_name == proc2.package_name and not p.is_gone
    )
    assert changed.prev_memory_kb > 0, "prev_memory_kb가 0으로 남아있음"
    assert changed.delta_kb == 500, \
        f"delta_kb 불일치: 기대 500, 실제 {changed.delta_kb}"
