from datetime import datetime

from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from core.data_models import MemInfoSnapshot
from utils.sorter import FLAT_CATEGORY, SortKey, SortOrder, sort_snapshot

# ── 컬럼 인덱스 상수 ──────────────────────────────────────────────────────────
COL_ADJ     = 0
COL_PACKAGE = 1
COL_PID     = 2
COL_PSS_KB  = 3
COL_PSS_MB  = 4
COL_DELTA   = 5
COL_TIME    = 6

HEADERS = ["ADJ", "Package Name", "PID", "PSS(KB)", "PSS(MB)", "Δ", "업데이트"]

# 컬럼 → 정렬 키 매핑 (없으면 정렬 불가)
_COL_SORT = {
    COL_ADJ:     SortKey.ADJ,
    COL_PACKAGE: SortKey.NAME,
    COL_PID:     SortKey.PID,
    COL_PSS_KB:  SortKey.MEMORY,
    COL_PSS_MB:  SortKey.MEMORY,
}

# ── 색상 상수 ─────────────────────────────────────────────────────────────────
_CLR_HEADER_BG  = QColor("#1E1E2E")
_CLR_HEADER_FG  = QColor("#CDD6F4")
_CLR_FLAT_BG    = QColor("#2D3748")   # 플랫 정렬 헤더
_CLR_FLAT_FG    = QColor("#E2E8F0")
_CLR_NEW        = QColor("#2E7D32")   # 다크 테마 흰 글자 대비용 어두운 녹색
_CLR_GONE       = QColor("#6E5A8C")   # 다크 테마 흰 글자 대비용 보라
_CLR_DELTA_UP   = QColor("#D32F2F")
_CLR_DELTA_DOWN = QColor("#1565C0")


def _bold_font() -> QFont:
    f = QFont()
    f.setBold(True)
    return f


class MainView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.collapsed_groups: set[str] = set()
        self._sort_key:   SortKey   = SortKey.ADJ
        self._sort_order: SortOrder = SortOrder.ASC
        self._last_snapshot: MemInfoSnapshot | None = None
        self._build_ui()

    # ── UI 구성 ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(HEADERS))
        self.tree.setHeaderLabels(HEADERS)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setSortingEnabled(False)   # 자체 정렬 사용
        self.tree.setAnimated(False)

        # 컬럼 너비
        self.tree.setColumnWidth(COL_ADJ,     130)
        self.tree.setColumnWidth(COL_PACKAGE, 300)
        self.tree.setColumnWidth(COL_PID,      70)
        self.tree.setColumnWidth(COL_PSS_KB,  110)
        self.tree.setColumnWidth(COL_PSS_MB,   80)
        self.tree.setColumnWidth(COL_DELTA,   120)
        self.tree.setColumnWidth(COL_TIME,     90)

        # 헤더 클릭으로 정렬
        self.tree.header().setSectionsClickable(True)
        self.tree.header().sectionClicked.connect(self._on_header_clicked)

        # 접기/펼치기 추적
        self.tree.itemExpanded.connect(self._on_expanded)
        self.tree.itemCollapsed.connect(self._on_collapsed)

        layout.addWidget(self.tree)

    # ── 시그널 슬롯 ───────────────────────────────────────────────────────────

    def _on_expanded(self, item: QTreeWidgetItem):
        cat = item.data(COL_ADJ, Qt.ItemDataRole.UserRole)
        if cat and cat != FLAT_CATEGORY:
            self.collapsed_groups.discard(cat)

    def _on_collapsed(self, item: QTreeWidgetItem):
        cat = item.data(COL_ADJ, Qt.ItemDataRole.UserRole)
        if cat and cat != FLAT_CATEGORY:
            self.collapsed_groups.add(cat)

    def _on_header_clicked(self, col: int):
        new_key = _COL_SORT.get(col)
        if new_key is None:
            return

        if self._sort_key == new_key:
            # ASC → DESC → 기본(ADJ ASC) 순환
            if self._sort_order == SortOrder.ASC:
                self._sort_order = SortOrder.DESC
            else:
                self._sort_key   = SortKey.ADJ
                self._sort_order = SortOrder.ASC
        else:
            self._sort_key   = new_key
            self._sort_order = SortOrder.ASC

        self._update_sort_icons()

        if self._last_snapshot is not None:
            self._render(self._last_snapshot)

    # ── 공개 API ─────────────────────────────────────────────────────────────

    def update_data(self, snapshot: MemInfoSnapshot) -> None:
        """외부에서 새 스냅샷을 받을 때 호출."""
        self._last_snapshot = snapshot
        self._render(snapshot)

    def current_sort(self) -> tuple[SortKey, SortOrder]:
        return self._sort_key, self._sort_order

    # ── 내부: 렌더링 ──────────────────────────────────────────────────────────

    def _render(self, snapshot: MemInfoSnapshot) -> None:
        sorted_snap = sort_snapshot(snapshot, self._sort_key, self._sort_order)

        # 스크롤 위치 저장 (재렌더 후 화면 위치 유지)
        vbar = self.tree.verticalScrollBar()
        hbar = self.tree.horizontalScrollBar()
        saved_v = vbar.value()
        saved_h = hbar.value()

        self.tree.blockSignals(True)
        self.tree.clear()

        for group in sorted_snap.adj_groups:
            self._add_adj_group(group)

        self.tree.blockSignals(False)

        # 스크롤 위치 복원 (범위 초과 시 Qt가 자동 클램프)
        vbar.setValue(saved_v)
        hbar.setValue(saved_h)

    def _add_adj_group(self, group) -> None:
        is_flat = (group.adj_category == FLAT_CATEGORY)
        header  = QTreeWidgetItem(self.tree)
        header.setData(COL_ADJ, Qt.ItemDataRole.UserRole, group.adj_category)

        if is_flat:
            header.setText(
                COL_ADJ,
                f"  전체 {len(group.processes)}개 프로세스"
                f"        합계: {group.total_memory_kb:,} KB  ({group.total_memory_kb / 1024:.1f} MB)",
            )
            bg, fg = _CLR_FLAT_BG, _CLR_FLAT_FG
        else:
            header.setText(
                COL_ADJ,
                f"  {group.adj_category}"
                f"        합계: {group.total_memory_kb:,} KB  ({group.total_memory_mb} MB)",
            )
            bg, fg = _CLR_HEADER_BG, _CLR_HEADER_FG

        header.setFont(COL_ADJ, _bold_font())
        for col in range(len(HEADERS)):
            header.setBackground(col, QBrush(bg))
            header.setForeground(col, QBrush(fg))

        row_idx = self.tree.indexOfTopLevelItem(header)
        self.tree.setFirstColumnSpanned(row_idx, QModelIndex(), True)

        for proc in group.processes:
            self._add_process_row(header, proc)

        if is_flat:
            header.setExpanded(True)
        else:
            header.setExpanded(group.adj_category not in self.collapsed_groups)

    def _add_process_row(self, parent: QTreeWidgetItem, proc) -> None:
        item = QTreeWidgetItem(parent)

        item.setText(COL_ADJ,     proc.adj_category)
        item.setText(COL_PACKAGE, proc.package_name)
        item.setText(COL_PID,     str(proc.pid))
        item.setText(COL_PSS_KB,  f"{proc.memory_kb:,}")
        item.setText(COL_PSS_MB,  f"{proc.memory_mb}")
        item.setText(COL_TIME,    datetime.fromtimestamp(proc.timestamp).strftime("%H:%M:%S"))

        item.setTextAlignment(COL_PSS_KB, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setTextAlignment(COL_PSS_MB, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setTextAlignment(COL_PID,    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 델타 (▲ 빨강 / ▼ 파랑 / -)
        if proc.delta_kb > 0:
            item.setText(COL_DELTA, f"▲ +{proc.delta_kb:,}")
            item.setForeground(COL_DELTA, QBrush(_CLR_DELTA_UP))
        elif proc.delta_kb < 0:
            item.setText(COL_DELTA, f"▼ {proc.delta_kb:,}")
            item.setForeground(COL_DELTA, QBrush(_CLR_DELTA_DOWN))
        else:
            item.setText(COL_DELTA, "-")

        # 신규/종료 행 배경 하이라이트
        if proc.is_gone:
            for col in range(len(HEADERS)):
                item.setBackground(col, QBrush(_CLR_GONE))
        elif proc.is_new:
            for col in range(len(HEADERS)):
                item.setBackground(col, QBrush(_CLR_NEW))

    # ── 내부: 정렬 아이콘 ─────────────────────────────────────────────────────

    def _update_sort_icons(self) -> None:
        for col, label in enumerate(HEADERS):
            if col in _COL_SORT and _COL_SORT[col] == self._sort_key:
                icon = "▲" if self._sort_order == SortOrder.ASC else "▼"
                self.tree.headerItem().setText(col, f"{label} {icon}")
            else:
                self.tree.headerItem().setText(col, label)
