import re
import time
from .data_models import ADJ_ORDER, ADJGroup, MemInfoSnapshot, ProcessEntry

SECTION_START = "Total PSS by OOM adjustment:"

# 프로세스 라인: 앞 공백 10개 이상 + "(pid N)" 포함
# 예) "              12,000K: /system/bin/surfaceflinger (pid 234)"
_PROCESS_LINE = re.compile(r"^\s{10,}(\d[\d,]*)K:\s+(.+?)\s+\(pid\s+(\d+)\)$")

# ADJ 헤더 라인: 앞 공백 4~8개 (숫자 우측 정렬로 가변) + "(pid N)" 없음
# 예) "    13,234K: Native"  또는  "     8,500K: Visible"
_ADJ_HEADER = re.compile(r"^\s{4,8}(\d[\d,]*)K:\s+(.+)$")

# 다음 섹션 시작 감지
_NEXT_SECTION = re.compile(r"^Total (?:PSS|RSS) by ")


def _to_int(s: str) -> int:
    return int(s.replace(",", ""))


def parse(raw_output: str, device_id: str = "") -> MemInfoSnapshot:
    snapshot = MemInfoSnapshot(device_id=device_id, timestamp=time.time())

    if not raw_output.strip():
        return snapshot

    lines = raw_output.splitlines()

    # 1. "Total PSS by OOM adjustment:" 섹션 시작 위치 탐색
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip() == SECTION_START:
            start_idx = i + 1
            break

    if start_idx is None:
        return snapshot

    # 2. 섹션 내용 파싱 (다음 섹션 헤더를 만나면 종료)
    current_group: ADJGroup | None = None

    for line in lines[start_idx:]:
        stripped = line.strip()

        # 빈 줄 무시
        if not stripped:
            continue

        # 다음 섹션 시작이면 중단
        if _NEXT_SECTION.match(stripped):
            break

        try:
            # 프로세스 라인을 먼저 시도 — "(pid N)" 유무로 ADJ 헤더와 구분
            m_proc = _PROCESS_LINE.match(line)
            if m_proc and current_group is not None:
                mem_kb = _to_int(m_proc.group(1))
                pkg = m_proc.group(2).strip()
                pid = int(m_proc.group(3))
                entry = ProcessEntry(
                    adj_category=current_group.adj_category,
                    adj_order=current_group.adj_order,
                    memory_kb=mem_kb,
                    package_name=pkg,
                    pid=pid,
                    timestamp=snapshot.timestamp,
                )
                current_group.processes.append(entry)
                continue

            # ADJ 헤더 라인 시도 (프로세스 라인이 아닌 경우)
            m_adj = _ADJ_HEADER.match(line)
            if m_adj:
                total_kb = _to_int(m_adj.group(1))
                category = m_adj.group(2).strip()
                order = ADJ_ORDER.get(category, 99)
                current_group = ADJGroup(
                    adj_category=category,
                    adj_order=order,
                    total_memory_kb=total_kb,
                )
                snapshot.adj_groups.append(current_group)

        except Exception:
            # 파싱 오류는 해당 라인 skip, 앱 크래시 방지
            continue

    return snapshot
