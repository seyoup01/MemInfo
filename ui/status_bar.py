import time
from datetime import datetime, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QStatusBar


class StatusBar(QStatusBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_labels()
        self.update_status(connected=False)

    # ── UI 구성 ───────────────────────────────────────────────────────────────

    def _build_labels(self):
        self._conn_label    = QLabel("● 끊김")
        self._time_label    = QLabel("마지막 업데이트: --:--:--")
        self._proc_label    = QLabel("총 - 프로세스")
        self._collect_label = QLabel("수집 #0")
        self._elapsed_label = QLabel("경과: 00:00:00")

        sep = "  │  "
        for label in (
            self._conn_label,
            QLabel(sep),
            self._time_label,
            QLabel(sep),
            self._proc_label,
            QLabel(sep),
            self._collect_label,
            QLabel(sep),
            self._elapsed_label,
        ):
            self.addWidget(label)

    # ── 공개 API ─────────────────────────────────────────────────────────────

    def update_status(self, connected: bool, reconnecting: bool = False) -> None:
        if reconnecting:
            self._conn_label.setText("● 재연결 중")
            self._conn_label.setStyleSheet("color: #F57F17; font-weight: bold;")
        elif connected:
            self._conn_label.setText("● 연결됨")
            self._conn_label.setStyleSheet("color: #2E7D32; font-weight: bold;")
        else:
            self._conn_label.setText("● 끊김")
            self._conn_label.setStyleSheet("color: #C62828; font-weight: bold;")

    def update_collection(
        self, process_count: int, collection_num: int, elapsed_sec: int
    ) -> None:
        self._proc_label.setText(f"총 {process_count} 프로세스")
        self._collect_label.setText(f"수집 #{collection_num}")
        elapsed = str(timedelta(seconds=elapsed_sec))
        self._elapsed_label.setText(f"경과: {elapsed}")

    def update_last_time(self, timestamp: float) -> None:
        dt = datetime.fromtimestamp(timestamp)
        self._time_label.setText(f"마지막 업데이트: {dt.strftime('%H:%M:%S')}")
