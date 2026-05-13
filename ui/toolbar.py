from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget,
)

# 표시 레이블 → 실제 초 매핑
_INTERVAL_MAP: dict[str, int] = {
    "1s": 1, "2s": 2, "3s": 3, "4s": 4, "5s": 5,
    "10s": 10, "20s": 20, "30s": 30,
    "1분": 60, "5분": 300, "10분": 600,
}
_INTERVAL_LABELS = list(_INTERVAL_MAP.keys())


class Toolbar(QWidget):
    device_selected  = pyqtSignal(str)   # serial 전달
    interval_changed = pyqtSignal(int)   # 초 단위 정수 전달
    start_clicked    = pyqtSignal()
    pause_clicked    = pyqtSignal()
    stop_clicked     = pyqtSignal()
    refresh_devices  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._connect_signals()
        self._set_state("stopped")

    # ── UI 구성 ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)

        # 기기 선택
        layout.addWidget(QLabel("기기:"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(220)
        self.device_combo.setPlaceholderText("기기를 선택하세요")
        layout.addWidget(self.device_combo)

        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedWidth(32)
        self.refresh_btn.setToolTip("기기 목록 새로고침")
        layout.addWidget(self.refresh_btn)

        layout.addSpacing(12)

        # 폴링 주기
        layout.addWidget(QLabel("폴링:"))
        self.interval_combo = QComboBox()
        self.interval_combo.addItems(_INTERVAL_LABELS)
        self.interval_combo.setCurrentText("5s")
        self.interval_combo.setFixedWidth(70)
        layout.addWidget(self.interval_combo)

        layout.addSpacing(12)

        # 제어 버튼
        self.start_btn = QPushButton("▶ 시작")
        self.pause_btn = QPushButton("⏸ 일시정지")
        self.stop_btn  = QPushButton("⏹ 중지")
        for btn in (self.start_btn, self.pause_btn, self.stop_btn):
            btn.setFixedHeight(28)
            layout.addWidget(btn)

        layout.addStretch()

    def _connect_signals(self):
        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.device_combo.currentTextChanged.connect(self._on_device_changed)
        self.interval_combo.currentTextChanged.connect(self._on_interval_changed)
        self.start_btn.clicked.connect(self._on_start)
        self.pause_btn.clicked.connect(self._on_pause)
        self.stop_btn.clicked.connect(self._on_stop)

    # ── 슬롯 ─────────────────────────────────────────────────────────────────

    def _on_device_changed(self, text: str):
        serial = self._extract_serial(text)
        if serial:
            self.device_selected.emit(serial)

    def _on_interval_changed(self, label: str):
        self.interval_changed.emit(self._interval_to_sec(label))

    def _on_start(self):
        self._set_state("running")
        self.start_clicked.emit()

    def _on_pause(self):
        # 일시정지 ↔ 재개 토글
        if self.pause_btn.text() == "⏸ 일시정지":
            self._set_state("paused")
        else:
            self._set_state("running")
        self.pause_clicked.emit()

    def _on_stop(self):
        self._set_state("stopped")
        self.stop_clicked.emit()

    # ── 공개 메서드 ───────────────────────────────────────────────────────────

    def populate_devices(self, devices: list) -> None:
        """AdbDevice 리스트를 드롭다운에 채운다."""
        current = self.device_combo.currentText()
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for d in devices:
            label = f"{d.serial}  [{d.model}]  {d.status}"
            self.device_combo.addItem(label, userData=d.serial)
        # 이전 선택 복원 시도
        idx = self.device_combo.findText(current)
        if idx >= 0:
            self.device_combo.setCurrentIndex(idx)
        self.device_combo.blockSignals(False)

    def current_serial(self) -> str:
        idx = self.device_combo.currentIndex()
        if idx < 0:
            return ""
        data = self.device_combo.itemData(idx)
        return data if data else ""

    def current_interval_sec(self) -> int:
        return self._interval_to_sec(self.interval_combo.currentText())

    # ── 내부 유틸 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _interval_to_sec(label: str) -> int:
        return _INTERVAL_MAP.get(label, 5)

    @staticmethod
    def _extract_serial(text: str) -> str:
        """드롭다운 표시 텍스트에서 serial만 추출."""
        return text.split()[0] if text else ""

    def _set_state(self, state: str) -> None:
        """state: 'stopped' | 'running' | 'paused'"""
        if state == "stopped":
            self.start_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)
            self.pause_btn.setText("⏸ 일시정지")
            self.stop_btn.setEnabled(False)
        elif state == "running":
            self.start_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.pause_btn.setText("⏸ 일시정지")
            self.stop_btn.setEnabled(True)
        elif state == "paused":
            self.start_btn.setEnabled(True)
            self.start_btn.setText("▶ 재개")
            self.pause_btn.setEnabled(False)
            self.pause_btn.setText("▶ 재개")
            self.stop_btn.setEnabled(True)

    def reset_start_button(self):
        self.start_btn.setText("▶ 시작")
