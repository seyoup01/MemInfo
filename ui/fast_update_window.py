"""'차트 빠르게 Update' 별도 윈도우.

선택한 PID 들에 대해 `dumpsys meminfo | grep 'pid <N>'` 형식으로 빠르게 폴링하고
내부 ChartView 에 누적한다. 닫히면 `closed` 시그널을 emit 하여 메인 윈도우가
정상 폴링을 재개할 수 있게 한다.
"""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMainWindow, QStatusBar,
    QVBoxLayout, QWidget,
)

from core.fast_polling_worker import FastPollingWorker
from ui.chart_view import ChartView

# 본 창 전용 인터벌 (1s 부터 시작, 메인 toolbar 와 별도)
_FAST_INTERVAL_MAP: dict[str, int] = {
    "1s": 1, "2s": 2, "3s": 3, "4s": 4, "5s": 5,
    "10s": 10, "20s": 20, "30s": 30,
    "1분": 60, "5분": 300, "10분": 600,
}
_FAST_INTERVAL_LABELS = list(_FAST_INTERVAL_MAP.keys())
_DEFAULT_LABEL = "1s"


class FastUpdateWindow(QMainWindow):
    closed = pyqtSignal()

    def __init__(
        self,
        adb_manager,
        serial: str,
        packages_with_pids: list[tuple[str, int]],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("차트 빠르게 Update")
        self.resize(1100, 640)

        self._adb     = adb_manager
        self._serial  = serial
        self._procs   = list(packages_with_pids)
        self._worker: FastPollingWorker | None = None

        self._build_ui()
        self._start_worker()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        layout  = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)

        # 컨트롤 행
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("업데이트 주기:"))

        self._interval_combo = QComboBox()
        self._interval_combo.addItems(_FAST_INTERVAL_LABELS)
        self._interval_combo.setCurrentText(_DEFAULT_LABEL)
        self._interval_combo.setFixedWidth(80)
        self._interval_combo.currentTextChanged.connect(self._on_interval_changed)
        ctrl.addWidget(self._interval_combo)

        ctrl.addSpacing(16)
        ctrl.addWidget(QLabel(
            f"선택 프로세스: {len(self._procs)}개 (PID 기반 grep 병렬 폴링)"
        ))
        ctrl.addStretch()
        layout.addLayout(ctrl)

        # 차트
        self._chart = ChartView()
        self._chart.set_packages([p for p, _ in self._procs])
        layout.addWidget(self._chart)

        self.setCentralWidget(central)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage(
            f"기기 {self._serial} — {len(self._procs)}개 프로세스를 "
            f"{_DEFAULT_LABEL} 주기로 빠르게 폴링 중"
        )

    # ── 슬롯 ──────────────────────────────────────────────────────────────────

    def _on_interval_changed(self, label: str):
        sec = _FAST_INTERVAL_MAP.get(label, 1)
        if self._worker:
            self._worker.set_interval(sec)
        self._status.showMessage(
            f"기기 {self._serial} — {len(self._procs)}개 프로세스를 "
            f"{label} 주기로 빠르게 폴링 중"
        )

    def _on_error(self, msg: str):
        self._status.showMessage(f"오류: {msg}", 3000)

    # ── 워커 관리 ─────────────────────────────────────────────────────────────

    def _start_worker(self):
        sec = _FAST_INTERVAL_MAP.get(self._interval_combo.currentText(), 1)
        self._worker = FastPollingWorker(
            self._adb, self._serial, self._procs, sec
        )
        self._worker.snapshot_ready.connect(self._chart.add_data_point)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    def _stop_worker(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        self._worker = None

    # ── 종료 처리 ─────────────────────────────────────────────────────────────

    def closeEvent(self, ev):
        self._stop_worker()
        self.closed.emit()
        super().closeEvent(ev)
