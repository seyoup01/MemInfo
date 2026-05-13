import copy
from enum import Enum

from core.data_models import ADJGroup, MemInfoSnapshot

# 플랫 정렬 시 사용하는 내부 센티넬 카테고리명
FLAT_CATEGORY = "__flat__"


class SortKey(Enum):
    ADJ    = "adj"
    MEMORY = "memory"
    NAME   = "name"
    PID    = "pid"


class SortOrder(Enum):
    ASC  = "asc"
    DESC = "desc"


def sort_snapshot(
    snapshot: MemInfoSnapshot,
    key: SortKey,
    order: SortOrder,
) -> MemInfoSnapshot:
    """
    ADJ순: 그룹 순서 고정, 그룹 내 프로세스는 memory 내림차순.
    나머지: ADJ 경계 무시, 전체 프로세스를 단일 리스트로 정렬.
    """
    if key == SortKey.ADJ:
        return _sort_by_adj(snapshot, order)
    return _sort_flat(snapshot, key, order)


# ── 내부 구현 ──────────────────────────────────────────────────────────────────

def _sort_by_adj(snapshot: MemInfoSnapshot, order: SortOrder) -> MemInfoSnapshot:
    reverse = (order == SortOrder.DESC)
    sorted_groups = sorted(
        snapshot.adj_groups,
        key=lambda g: g.adj_order,
        reverse=reverse,
    )
    result = copy.copy(snapshot)
    result.adj_groups = []
    for g in sorted_groups:
        ng = copy.copy(g)
        # 그룹 내 프로세스는 항상 memory 내림차순
        ng.processes = sorted(g.processes, key=lambda p: p.memory_kb, reverse=True)
        result.adj_groups.append(ng)
    return result


def _sort_flat(
    snapshot: MemInfoSnapshot,
    key: SortKey,
    order: SortOrder,
) -> MemInfoSnapshot:
    all_procs = [p for g in snapshot.adj_groups for p in g.processes]
    reverse   = (order == SortOrder.DESC)

    _key_func = {
        SortKey.MEMORY: lambda p: p.memory_kb,
        SortKey.NAME:   lambda p: p.package_name.lower(),
        SortKey.PID:    lambda p: p.pid,
    }
    all_procs.sort(key=_key_func[key], reverse=reverse)

    total_kb = sum(p.memory_kb for p in all_procs if not p.is_gone)
    flat = ADJGroup(
        adj_category=FLAT_CATEGORY,
        adj_order=-1,
        total_memory_kb=total_kb,
    )
    flat.processes = all_procs

    result = copy.copy(snapshot)
    result.adj_groups = [flat]
    return result
