from datetime import datetime

from PyQt6.QtWidgets import (
    QDockWidget, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

_MAX_ROWS = 100

_COL_TIME    = 0
_COL_PKG     = 1
_COL_MEM     = 2
_COL_THR     = 3

_HEADERS = ["시각", "패키지명", "메모리(KB)", "임계값(KB)"]


class AlertLogPanel(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("알림 로그", parent)
        self.setAllowedAreas(
            __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.DockWidgetArea.BottomDockWidgetArea
            | __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.DockWidgetArea.RightDockWidgetArea
        )
        self._build_ui()

    def _build_ui(self):
        container = QWidget()
        layout    = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        btn_row   = QHBoxLayout()
        btn_clear = QPushButton("로그 지우기")
        btn_clear.clicked.connect(self._clear)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._table = QTableWidget()
        self._table.setColumnCount(len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setColumnWidth(_COL_TIME,  80)
        self._table.setColumnWidth(_COL_PKG,  240)
        self._table.setColumnWidth(_COL_MEM,   90)
        self._table.setColumnWidth(_COL_THR,   90)
        layout.addWidget(self._table)

        self.setWidget(container)

    # ── 공개 API ─────────────────────────────────────────────────────────────

    def add_alert(
        self, package_name: str, memory_kb: int, threshold_kb: int
    ) -> None:
        """알림 1건을 로그 최상단에 삽입."""
        self._table.insertRow(0)
        self._table.setItem(0, _COL_TIME, QTableWidgetItem(
            datetime.now().strftime("%H:%M:%S")
        ))
        self._table.setItem(0, _COL_PKG,  QTableWidgetItem(package_name))
        self._table.setItem(0, _COL_MEM,  QTableWidgetItem(f"{memory_kb:,}"))
        self._table.setItem(0, _COL_THR,  QTableWidgetItem(f"{threshold_kb:,}"))

        # 최대 건수 초과 시 마지막 행 제거
        if self._table.rowCount() > _MAX_ROWS:
            self._table.removeRow(self._table.rowCount() - 1)

    def row_count(self) -> int:
        return self._table.rowCount()

    def _clear(self):
        self._table.setRowCount(0)
