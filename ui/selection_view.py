import json

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from core.data_models import MemInfoSnapshot, ProcessEntry

_CLR_GONE      = QColor("#6E5A8C")   # 다크 테마 흰 글자 대비용 보라
_CLR_RESTARTED = QColor("#1565C0")   # 다크 테마 흰 글자 대비용 진파랑

_COL_PKG    = 0
_COL_PID    = 1
_COL_KB     = 2
_COL_DELTA  = 3
_COL_STATUS = 4

_HEADERS = ["Package Name", "PID", "PSS(KB)", "Δ", "상태"]

_RESTARTED_CYCLES = 2


class SelectionView(QWidget):
    chart_requested   = pyqtSignal(list)   # "차트 보기 ▶" 버튼 (탭 전환용)
    selection_changed = pyqtSignal(list)   # 체크박스/전체선택 등 선택 변화 즉시 emit

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_packages: set[str]        = set()
        self._gone_procs: dict[str, ProcessEntry] = {}
        self._restarted_cycles: dict[str, int]   = {}
        self._all_procs: dict[str, ProcessEntry] = {}
        self._build_ui()

    @property
    def selected_packages(self) -> list[str]:
        return sorted(self._selected_packages)

    # ── UI 구성 ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 왼쪽: 전체 프로세스 목록
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._search = QLineEdit()
        self._search.setPlaceholderText("패키지명 검색...")
        self._search.textChanged.connect(self._on_search)

        self._list = QListWidget()
        self._list.itemChanged.connect(self._on_item_changed)

        btn_row = QHBoxLayout()
        btn_all  = QPushButton("전체 선택")
        btn_none = QPushButton("전체 해제")
        btn_all.clicked.connect(self._select_all)
        btn_none.clicked.connect(self._select_none)
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)

        left_layout.addWidget(QLabel("전체 프로세스:"))
        left_layout.addWidget(self._search)
        left_layout.addWidget(self._list)
        left_layout.addLayout(btn_row)

        # 오른쪽: 선택 프로세스 모니터링
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        top_btns = QHBoxLayout()
        btn_save  = QPushButton("저장")
        btn_load  = QPushButton("불러오기")
        btn_clear = QPushButton("초기화")
        btn_chart = QPushButton("차트 보기 ▶")
        btn_save.clicked.connect(self._save_selection)
        btn_load.clicked.connect(self._load_selection)
        btn_clear.clicked.connect(self._clear_selection)
        btn_chart.clicked.connect(
            lambda: self.chart_requested.emit(self.selected_packages)
        )
        top_btns.addWidget(btn_save)
        top_btns.addWidget(btn_load)
        top_btns.addWidget(btn_clear)
        top_btns.addWidget(btn_chart)
        top_btns.addStretch()

        self._lbl_sel_count = QLabel("선택: 0개")
        top_btns.addWidget(self._lbl_sel_count)

        self._table = QTableWidget()
        self._table.setColumnCount(len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setColumnWidth(_COL_PKG,    250)
        self._table.setColumnWidth(_COL_PID,     60)
        self._table.setColumnWidth(_COL_KB,      90)
        self._table.setColumnWidth(_COL_DELTA,   90)
        self._table.setColumnWidth(_COL_STATUS,  80)

        right_layout.addLayout(top_btns)
        right_layout.addWidget(self._table)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([300, 600])

        layout.addWidget(splitter)

    # ── 공개 API ─────────────────────────────────────────────────────────────

    def update_data(self, snapshot: MemInfoSnapshot) -> None:
        current_map: dict[str, ProcessEntry] = {
            p.package_name: p
            for g in snapshot.adj_groups
            for p in g.processes
        }

        # 이전에 gone이었다가 다시 나타난 경우 → 재시작
        for pkg in list(self._gone_procs.keys()):
            if pkg in current_map:
                del self._gone_procs[pkg]
                self._restarted_cycles[pkg] = _RESTARTED_CYCLES

        # 선택된 패키지 중 사라진 경우 → gone 추적
        for pkg in self._selected_packages:
            if pkg in self._all_procs and pkg not in current_map:
                self._gone_procs[pkg] = self._all_procs[pkg]

        # 재시작 카운트다운
        for pkg in list(self._restarted_cycles.keys()):
            self._restarted_cycles[pkg] -= 1
            if self._restarted_cycles[pkg] <= 0:
                del self._restarted_cycles[pkg]

        self._all_procs = current_map
        self._refresh_list()
        self._refresh_table()

    # ── 왼쪽 패널 ────────────────────────────────────────────────────────────

    def _refresh_list(self):
        search   = self._search.text().lower()
        all_pkgs = sorted(self._all_procs.keys())

        self._list.blockSignals(True)
        self._list.clear()
        for pkg in all_pkgs:
            if search and search not in pkg.lower():
                continue
            item = QListWidgetItem(pkg)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            state = (
                Qt.CheckState.Checked
                if pkg in self._selected_packages
                else Qt.CheckState.Unchecked
            )
            item.setCheckState(state)
            self._list.addItem(item)
        self._list.blockSignals(False)

    def _on_search(self, _text: str):
        self._refresh_list()

    def _on_item_changed(self, item: QListWidgetItem):
        pkg = item.text()
        if item.checkState() == Qt.CheckState.Checked:
            self._selected_packages.add(pkg)
        else:
            self._selected_packages.discard(pkg)
        self._refresh_table()
        self._lbl_sel_count.setText(f"선택: {len(self._selected_packages)}개")
        self.selection_changed.emit(self.selected_packages)

    def _select_all(self):
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            item = self._list.item(i)
            self._selected_packages.add(item.text())
            item.setCheckState(Qt.CheckState.Checked)
        self._list.blockSignals(False)
        self._refresh_table()
        self._lbl_sel_count.setText(f"선택: {len(self._selected_packages)}개")
        self.selection_changed.emit(self.selected_packages)

    def _select_none(self):
        self._list.blockSignals(True)
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._list.blockSignals(False)
        self._selected_packages.clear()
        self._refresh_table()
        self._lbl_sel_count.setText("선택: 0개")
        self.selection_changed.emit(self.selected_packages)

    # ── 오른쪽 패널 ──────────────────────────────────────────────────────────

    def _refresh_table(self):
        self._table.setRowCount(0)

        for pkg in sorted(self._selected_packages):
            row = self._table.rowCount()
            self._table.insertRow(row)

            if pkg in self._gone_procs:
                proc   = self._gone_procs[pkg]
                status = "종료됨"
                bg     = _CLR_GONE
            elif pkg in self._restarted_cycles:
                proc   = self._all_procs.get(pkg)
                if proc is None:
                    continue
                status = "재시작됨"
                bg     = _CLR_RESTARTED
            elif pkg in self._all_procs:
                proc   = self._all_procs[pkg]
                status = ""
                bg     = None
            else:
                self._table.setItem(row, _COL_PKG, QTableWidgetItem(pkg))
                self._table.setItem(row, _COL_STATUS, QTableWidgetItem("대기"))
                continue

            if proc.delta_kb > 0:
                delta_text = f"▲ +{proc.delta_kb:,}"
            elif proc.delta_kb < 0:
                delta_text = f"▼ {proc.delta_kb:,}"
            else:
                delta_text = "-"

            cells = [
                QTableWidgetItem(pkg),
                QTableWidgetItem(str(proc.pid)),
                QTableWidgetItem(f"{proc.memory_kb:,}"),
                QTableWidgetItem(delta_text),
                QTableWidgetItem(status),
            ]
            for col, cell in enumerate(cells):
                if col in (_COL_PID, _COL_KB, _COL_DELTA):
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if bg is not None:
                    cell.setBackground(QBrush(bg))
                self._table.setItem(row, col, cell)

    def _save_selection(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "선택 목록 저장", "", "JSON 파일 (*.json)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"packages": self.selected_packages}, f,
                      ensure_ascii=False, indent=2)

    def _load_selection(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "선택 목록 불러오기", "", "JSON 파일 (*.json)"
        )
        if not path:
            return
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._selected_packages = set(data.get("packages", []))
        self._refresh_list()
        self._refresh_table()
        self._lbl_sel_count.setText(f"선택: {len(self._selected_packages)}개")
        self.selection_changed.emit(self.selected_packages)

    def _clear_selection(self):
        self._selected_packages.clear()
        self._refresh_list()
        self._refresh_table()
        self._lbl_sel_count.setText("선택: 0개")
        self.selection_changed.emit(self.selected_packages)
