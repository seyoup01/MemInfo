"""STEP 2 검증: 데이터 모델 및 meminfo 파서"""
import os
import time
import pytest

FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "sample_meminfo.txt"
)

with open(FIXTURE, encoding="utf-8") as _f:
    SAMPLE_RAW = _f.read()


# ── data_models ──────────────────────────────────────────────────────────────

def test_process_entry_memory_mb():
    from core.data_models import ProcessEntry
    p = ProcessEntry("Native", 0, 10240, "/init", 1)
    assert p.memory_mb == 10.0

def test_process_entry_delta_kb():
    from core.data_models import ProcessEntry
    p = ProcessEntry("Native", 0, 15000, "/init", 1, prev_memory_kb=10000)
    assert p.delta_kb == 5000

def test_adj_group_total_memory_mb():
    from core.data_models import ADJGroup
    g = ADJGroup("Native", 0, total_memory_kb=2048)
    assert g.total_memory_mb == 2.0

def test_snapshot_total_process_count():
    from core.data_models import MemInfoSnapshot, ADJGroup, ProcessEntry
    snap = MemInfoSnapshot("dev", time.time())
    g1 = ADJGroup("Native", 0)
    g1.processes = [ProcessEntry("Native", 0, 1000, "/init", 1)]
    g2 = ADJGroup("Foreground", 4)
    g2.processes = [
        ProcessEntry("Foreground", 4, 2000, "com.a", 2),
        ProcessEntry("Foreground", 4, 3000, "com.b", 3),
    ]
    snap.adj_groups = [g1, g2]
    assert snap.total_process_count == 3


# ── meminfo_parser ────────────────────────────────────────────────────────────

def test_parse_returns_snapshot():
    from core.meminfo_parser import parse
    from core.data_models import MemInfoSnapshot
    snap = parse(SAMPLE_RAW, "test_device")
    assert isinstance(snap, MemInfoSnapshot)

def test_parse_adj_group_count():
    from core.meminfo_parser import parse
    snap = parse(SAMPLE_RAW, "test_device")
    # 샘플: Native, System, Foreground, Visible, Cached = 5개
    assert len(snap.adj_groups) == 5, \
        f"ADJ 그룹 수 불일치: 기대=5, 실제={len(snap.adj_groups)}"

def test_parse_native_total_memory():
    from core.meminfo_parser import parse
    snap = parse(SAMPLE_RAW, "test_device")
    native = next(g for g in snap.adj_groups if g.adj_category == "Native")
    assert native.total_memory_kb == 13234, \
        f"Native 합계 불일치: 기대=13234, 실제={native.total_memory_kb}"

def test_parse_foreground_process():
    from core.meminfo_parser import parse
    snap = parse(SAMPLE_RAW, "test_device")
    fg = next(g for g in snap.adj_groups if g.adj_category == "Foreground")
    assert len(fg.processes) == 1
    assert fg.processes[0].package_name == "com.kakao.talk"

def test_parse_pid_is_int():
    from core.meminfo_parser import parse
    snap = parse(SAMPLE_RAW, "test_device")
    for group in snap.adj_groups:
        for proc in group.processes:
            assert isinstance(proc.pid, int), \
                f"{proc.package_name}의 PID가 int가 아님: {type(proc.pid)}"

def test_parse_total_process_count():
    from core.meminfo_parser import parse
    snap = parse(SAMPLE_RAW, "test_device")
    # Native(2) + System(1) + Foreground(1) + Visible(2) + Cached(1) = 7
    assert snap.total_process_count == 7, \
        f"전체 프로세스 수 불일치: 기대=7, 실제={snap.total_process_count}"

def test_parse_excludes_pss_by_process_section():
    """'Total PSS by process:' 섹션 데이터가 결과에 포함되지 않아야 함"""
    from core.meminfo_parser import parse
    snap = parse(SAMPLE_RAW, "test_device")
    all_pkgs = [p.package_name for g in snap.adj_groups for p in g.processes]
    # sample_meminfo의 "Total PSS by process:" 섹션에만 있는 중복 항목 체크
    # (실제로는 OOM 섹션에도 동일 패키지가 있으므로 중복 개수로 검증)
    # 각 패키지는 OOM 섹션에 정확히 1번씩만 나와야 함
    from collections import Counter
    counts = Counter(all_pkgs)
    for pkg, cnt in counts.items():
        assert cnt == 1, \
            f"{pkg}가 {cnt}번 파싱됨 (PSS by process 섹션이 포함된 것으로 의심)"

def test_parse_empty_string():
    from core.meminfo_parser import parse
    snap = parse("", "test_device")
    assert snap.total_process_count == 0
    assert len(snap.adj_groups) == 0

def test_parse_no_exception_on_garbage_lines():
    """잘못된 형식의 라인이 섞여도 예외 없이 나머지를 파싱해야 함"""
    from core.meminfo_parser import parse
    garbage = SAMPLE_RAW.replace(
        "              12,000K: /system/bin/surfaceflinger (pid 234)",
        "              BROKEN LINE @@@ !!!"
    )
    snap = parse(garbage, "test_device")
    # Native 그룹에서 broken 라인 제외, 나머지는 정상 파싱
    native = next(g for g in snap.adj_groups if g.adj_category == "Native")
    assert len(native.processes) == 1  # surfaceflinger 제거, /init 만 남음
    assert snap.total_process_count == 6  # 전체에서 1개 감소

def test_parse_adj_order_assigned():
    """ADJ_ORDER 딕셔너리에 있는 카테고리는 올바른 순서 번호를 가져야 함"""
    from core.meminfo_parser import parse
    from core.data_models import ADJ_ORDER
    snap = parse(SAMPLE_RAW, "test_device")
    for group in snap.adj_groups:
        expected = ADJ_ORDER.get(group.adj_category, 99)
        assert group.adj_order == expected, \
            f"{group.adj_category} adj_order 불일치: 기대={expected}, 실제={group.adj_order}"

def test_parse_memory_kb_no_comma():
    """천 단위 콤마가 제거되어 정수로 변환되었는지 확인"""
    from core.meminfo_parser import parse
    snap = parse(SAMPLE_RAW, "test_device")
    for group in snap.adj_groups:
        assert isinstance(group.total_memory_kb, int)
        for proc in group.processes:
            assert isinstance(proc.memory_kb, int)


# ── 실측 Samsung 기기 출력 검증 (12개 ADJ + 트레일링 토큰 변형) ────────────────

REAL_FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "real_meminfo.txt"
)

with open(REAL_FIXTURE, encoding="utf-8") as _f:
    REAL_RAW = _f.read()


def test_parse_real_device_adj_groups():
    """실측 데이터에서 12개 ADJ 그룹이 모두 검출되어야 한다."""
    from core.meminfo_parser import parse
    snap = parse(REAL_RAW, "real_device")
    categories = [g.adj_category for g in snap.adj_groups]
    expected = [
        "Native", "System", "Persistent", "Persistent Service",
        "Foreground", "Visible", "Perceptible", "Perceptible Low",
        "A Services", "B Services", "Picked", "Cached",
    ]
    assert categories == expected, f"카테고리 불일치: {categories}"


def test_parse_real_device_no_phantom_adj():
    """모든 adj_category가 ADJ_ORDER 화이트리스트에 포함 (오인식 0건)."""
    from core.meminfo_parser import parse
    from core.data_models import ADJ_ORDER
    snap = parse(REAL_RAW, "real_device")
    for g in snap.adj_groups:
        assert g.adj_category in ADJ_ORDER, \
            f"미지의 ADJ 카테고리: {g.adj_category!r}"
        # 프로세스 정보가 ADJ로 잘못 들어가 있는지 확인
        assert "(pid" not in g.adj_category
        assert "K:" not in g.adj_category


def test_parse_real_device_process_with_activities():
    """`(pid N / activities)` 패턴 프로세스가 정상 파싱되어야 한다."""
    from core.meminfo_parser import parse
    snap = parse(REAL_RAW, "real_device")
    all_procs = [p for g in snap.adj_groups for p in g.processes]
    # 샘플: "102,600K: com.android.settings (pid 19399 / activities)"
    settings = [p for p in all_procs if p.package_name == "com.android.settings"]
    assert settings, "com.android.settings 가 파싱되지 않음"
    assert settings[0].pid == 19399


def test_parse_real_device_process_with_user():
    """트레일링 `(user N)` 가 있어도 패키지명/PID 정상 추출."""
    from core.meminfo_parser import parse
    snap = parse(REAL_RAW, "real_device")
    all_procs = [p for g in snap.adj_groups for p in g.processes]
    # 샘플: "57,396K: com.google.android.gms.persistent (pid 27425) (user 150)"
    matches = [
        p for p in all_procs
        if p.package_name == "com.google.android.gms.persistent" and p.pid == 27425
    ]
    assert matches, "(user 150) 트레일링 프로세스가 파싱되지 않음"


def test_parse_real_device_total_native():
    """Native 그룹 총합이 1,242,354K 와 일치."""
    from core.meminfo_parser import parse
    snap = parse(REAL_RAW, "real_device")
    native = next(g for g in snap.adj_groups if g.adj_category == "Native")
    assert native.total_memory_kb == 1_242_354


def test_parse_real_device_process_under_correct_group():
    """surfaceflinger(pid 2539) 는 Native 그룹 아래에 등록되어야 한다."""
    from core.meminfo_parser import parse
    snap = parse(REAL_RAW, "real_device")
    native = next(g for g in snap.adj_groups if g.adj_category == "Native")
    sf = [p for p in native.processes if p.package_name == "surfaceflinger"]
    assert sf and sf[0].pid == 2539
    assert sf[0].memory_kb == 223_725
