import re
import time
from .data_models import ADJ_ORDER, ADJGroup, MemInfoSnapshot, ProcessEntry

SECTION_START = "Total PSS by OOM adjustment:"

# 프로세스 라인: "(pid N)" 또는 "(pid N / activities)" 패턴 필수
# 예) "        223,725K: surfaceflinger (pid 2539)"
#     "        102,600K: com.android.settings (pid 19399 / activities)"
#     "         57,396K: com.google.android.gms.persistent (pid 27425) (user 150)"
# 들여쓰기는 메모리 자릿수에 따라 가변 (6~12칸)이므로 \s+ 만 요구.
_PROCESS_LINE = re.compile(
    r"^\s+(\d[\d,]*)K:\s+(.+?)\s+\(pid\s+(\d+)(?:\s*/[^)]*)?\)"
)

# ADJ 헤더 라인: "(pid)" 없음, 들여쓰기 2~5칸 가변
# 카테고리 텍스트 검증은 ADJ_ORDER 화이트리스트로 수행 (오인식 차단)
_ADJ_HEADER = re.compile(r"^\s+(\d[\d,]*)K:\s+(.+?)\s*$")

# 다음 섹션 시작 감지 ("Total PSS by category:" 등)
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

        if not stripped:
            continue

        if _NEXT_SECTION.match(stripped):
            break

        try:
            # 우선 프로세스 라인 시도 — "(pid N)" 패턴이 결정적 시그널
            m_proc = _PROCESS_LINE.match(line)
            if m_proc and current_group is not None:
                entry = ProcessEntry(
                    adj_category=current_group.adj_category,
                    adj_order=current_group.adj_order,
                    memory_kb=_to_int(m_proc.group(1)),
                    package_name=m_proc.group(2).strip(),
                    pid=int(m_proc.group(3)),
                    timestamp=snapshot.timestamp,
                )
                current_group.processes.append(entry)
                continue

            # ADJ 헤더 시도 — 화이트리스트에 있을 때만 인정
            m_adj = _ADJ_HEADER.match(line)
            if m_adj:
                category = m_adj.group(2).strip()
                if category in ADJ_ORDER:
                    current_group = ADJGroup(
                        adj_category=category,
                        adj_order=ADJ_ORDER[category],
                        total_memory_kb=_to_int(m_adj.group(1)),
                    )
                    snapshot.adj_groups.append(current_group)
                # 미지의 카테고리는 조용히 스킵 (프로세스 라인 오인식 방지)

        except Exception:
            continue

    return snapshot
