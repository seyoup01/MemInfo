import copy

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from core.data_models import MemInfoSnapshot
from ui.main_view import MainView

_KB_PER_MB = 1024
_QUICK_MB  = [10, 50, 100, 200, 500]


class ThresholdView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._threshold_kb = 50_000
        self._unit = "KB"
        self._last_snapshot: MemInfoSnapshot | None = None
        self._build_ui()

    @property
    def threshold_kb(self) -> int:
        return self._threshold_kb

    # ── UI 구성 ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 0)
        layout.setSpacing(4)

        ctrl = QHBoxLayout()

        ctrl.addWidget(QLabel("최소 메모리:"))

        self._spin = QSpinBox()
        self._spin.setRange(0, 10_000_000)
        self._spin.setValue(self._threshold_kb)
        self._spin.setSingleStep(1_000)
        self._spin.setGroupSeparatorShown(True)
        self._spin.setFixedWidth(130)
        self._spin.valueChanged.connect(self._on_spin_changed)
        ctrl.addWidget(self._spin)

        self._rb_kb = QRadioButton("KB")
        self._rb_mb = QRadioButton("MB")
        self._rb_kb.setChecked(True)
        self._unit_group = QButtonGroup(self)
        self._unit_group.addButton(self._rb_kb, 0)
        self._unit_group.addButton(self._rb_mb, 1)
        self._unit_group.idToggled.connect(self._on_unit_toggled)
        ctrl.addWidget(self._rb_kb)
        ctrl.addWidget(self._rb_mb)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 10_000_000)
        self._slider.setValue(self._threshold_kb)
        self._slider.setFixedWidth(200)
        self._slider.valueChanged.connect(self._on_slider_changed)
        ctrl.addWidget(self._slider)

        for mb in _QUICK_MB:
            btn = QPushButton(f"{mb}MB")
            btn.setFixedWidth(55)
            btn.clicked.connect(lambda checked, m=mb: self._set_threshold_mb(m))
            ctrl.addWidget(btn)

        btn_all = QPushButton("전체 보기")
        btn_all.clicked.connect(lambda: self._set_threshold_kb(0))
        ctrl.addWidget(btn_all)

        ctrl.addStretch()

        self._lbl_count = QLabel("필터 결과: -")
        ctrl.addWidget(self._lbl_count)

        layout.addLayout(ctrl)

        self._view = MainView()
        layout.addWidget(self._view)

    # ── 이벤트 슬롯 ──────────────────────────────────────────────────────────

    def _on_spin_changed(self, value: int):
        self._slider.blockSignals(True)
        self._slider.setValue(value)
        self._slider.blockSignals(False)
        self._threshold_kb = value * _KB_PER_MB if self._unit == "MB" else value
        self._rerender()

    def _on_slider_changed(self, value: int):
        self._spin.blockSignals(True)
        self._spin.setValue(value)
        self._spin.blockSignals(False)
        self._threshold_kb = value * _KB_PER_MB if self._unit == "MB" else value
        self._rerender()

    def _on_unit_toggled(self, btn_id: int, checked: bool):
        if not checked:
            return
        new_unit = "KB" if btn_id == 0 else "MB"
        if new_unit == self._unit:
            return

        old_kb     = self._threshold_kb
        self._unit = new_unit

        self._spin.blockSignals(True)
        self._slider.blockSignals(True)

        if new_unit == "MB":
            display_val        = max(0, old_kb // _KB_PER_MB)
            self._threshold_kb = display_val * _KB_PER_MB
            self._spin.setRange(0, 10_000)
            self._slider.setRange(0, 10_000)
        else:
            display_val = old_kb
            self._spin.setRange(0, 10_000_000)
            self._slider.setRange(0, 10_000_000)

        self._spin.setValue(display_val)
        self._slider.setValue(display_val)

        self._spin.blockSignals(False)
        self._slider.blockSignals(False)
        self._rerender()

    def _set_threshold_mb(self, mb: int):
        if self._unit == "MB":
            self._spin.setValue(mb)
        else:
            self._spin.setValue(mb * _KB_PER_MB)

    def _set_threshold_kb(self, kb: int):
        if self._unit == "KB":
            self._spin.setValue(kb)
        else:
            self._spin.setValue(kb // _KB_PER_MB)

    # ── 공개 API ─────────────────────────────────────────────────────────────

    def update_data(self, snapshot: MemInfoSnapshot) -> None:
        self._last_snapshot = snapshot
        self._rerender()

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    def _rerender(self):
        if self._last_snapshot is None:
            return
        filtered_snap, total, shown = self._apply_filter(self._last_snapshot)
        self._view.update_data(filtered_snap)
        self._lbl_count.setText(
            f"필터 결과: {shown}개 프로세스 (전체 {total}개 중)"
        )

    def _apply_filter(
        self, snapshot: MemInfoSnapshot
    ) -> tuple[MemInfoSnapshot, int, int]:
        total  = snapshot.total_process_count
        result = copy.copy(snapshot)
        result.adj_groups = []
        shown  = 0

        for g in snapshot.adj_groups:
            procs = [p for p in g.processes if p.memory_kb >= self._threshold_kb]
            if not procs:
                continue
            ng = copy.copy(g)
            ng.processes       = procs
            ng.total_memory_kb = sum(p.memory_kb for p in procs)
            result.adj_groups.append(ng)
            shown += len(procs)

        return result, total, shown
