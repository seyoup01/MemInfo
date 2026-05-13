from datetime import datetime
from collections import defaultdict, deque

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget,
)

from core.data_models import MemInfoSnapshot

_MAX_PACKAGES  = 10
_DEFAULT_SAMPLES = 200
_PALETTE = [
    "#E53935", "#8E24AA", "#1E88E5", "#43A047", "#FB8C00",
    "#00ACC1", "#FFB300", "#6D4C41", "#546E7A", "#D81B60",
]


class _TimeAxisItem(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        return [
            datetime.fromtimestamp(v).strftime("%H:%M:%S")
            if v > 0 else ""
            for v in values
        ]


class ChartView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._packages: list[str]                    = []
        self._sample_count: int                      = _DEFAULT_SAMPLES
        self._xs: deque[float]                       = deque()
        self._ys: dict[str, deque[int]]              = defaultdict(deque)
        self._curves: dict[str, pg.PlotDataItem]     = {}
        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 컨트롤 행
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("표시 범위:"))

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(50, 1_000)
        self._slider.setValue(_DEFAULT_SAMPLES)
        self._slider.setFixedWidth(180)
        self._slider.valueChanged.connect(self._on_sample_count_changed)
        ctrl.addWidget(self._slider)

        self._lbl_samples = QLabel(f"{_DEFAULT_SAMPLES} 샘플")
        ctrl.addWidget(self._lbl_samples)

        ctrl.addStretch()
        self._legend_layout = QHBoxLayout()
        ctrl.addLayout(self._legend_layout)
        layout.addLayout(ctrl)

        # pyqtgraph 차트
        self._plot = pg.PlotWidget(
            axisItems={"bottom": _TimeAxisItem(orientation="bottom")}
        )
        self._plot.setBackground("#1E1E2E")
        self._plot.setLabel("left", "PSS (KB)")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.getPlotItem().getViewBox().setMouseEnabled(x=True, y=True)

        layout.addWidget(self._plot)

    # ── 공개 API ─────────────────────────────────────────────────────────────

    def set_packages(self, packages: list[str]) -> None:
        """모니터링할 패키지 목록 설정 (최대 10개)."""
        self._packages = list(packages[:_MAX_PACKAGES])
        self._xs.clear()
        self._ys.clear()
        self._curves.clear()
        self._plot.clear()
        self._rebuild_legend()
        self._rebuild_curves()

    def add_data_point(self, snapshot: MemInfoSnapshot) -> None:
        """스냅샷에서 설정된 패키지 데이터를 추출해 그래프에 추가."""
        if not self._packages:
            return

        proc_map = {
            p.package_name: p
            for g in snapshot.adj_groups
            for p in g.processes
        }

        self._xs.append(snapshot.timestamp)
        if len(self._xs) > self._sample_count:
            self._xs.popleft()

        for pkg in self._packages:
            proc = proc_map.get(pkg)
            val  = proc.memory_kb if proc else 0
            q    = self._ys[pkg]
            q.append(val)
            if len(q) > self._sample_count:
                q.popleft()

        self._update_curves()

    def clear(self) -> None:
        self._xs.clear()
        self._ys.clear()
        for curve in self._curves.values():
            curve.setData([], [])

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _on_sample_count_changed(self, value: int):
        self._sample_count = value
        self._lbl_samples.setText(f"{value} 샘플")
        # 넘치는 데이터 제거
        while len(self._xs) > value:
            self._xs.popleft()
        for q in self._ys.values():
            while len(q) > value:
                q.popleft()
        self._update_curves()

    def _rebuild_curves(self):
        for i, pkg in enumerate(self._packages):
            color = _PALETTE[i % len(_PALETTE)]
            pen   = pg.mkPen(color=color, width=2)
            curve = self._plot.plot(pen=pen, name=pkg)
            self._curves[pkg] = curve

    def _rebuild_legend(self):
        # 기존 범례 제거
        for i in reversed(range(self._legend_layout.count())):
            w = self._legend_layout.itemAt(i).widget()
            if w:
                w.deleteLater()

        for i, pkg in enumerate(self._packages):
            color = _PALETTE[i % len(_PALETTE)]
            badge = QLabel("●")
            badge.setStyleSheet(f"color: {color}; font-size: 14px;")
            self._legend_layout.addWidget(badge)
            lbl = QLabel(pkg.split(".")[-1])   # 마지막 패키지 세그먼트만
            lbl.setToolTip(pkg)
            self._legend_layout.addWidget(lbl)

    def _update_curves(self):
        xs = list(self._xs)
        for pkg, curve in self._curves.items():
            ys = list(self._ys[pkg])
            n  = min(len(xs), len(ys))
            curve.setData(xs[-n:], ys[-n:])
