from datetime import datetime
from collections import defaultdict, deque

import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from core.data_models import MemInfoSnapshot

_MAX_PACKAGES    = 10
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


class _KbAxisItem(pg.AxisItem):
    """PSS(KB) Y축 — 콤마 구분 정수 포맷 (1e+06 등 과학표기 차단)."""
    def tickStrings(self, values, scale, spacing):
        return [f"{int(round(v)):,}" for v in values]


class ChartView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._packages: list[str]                  = []
        self._sample_count: int                    = _DEFAULT_SAMPLES
        self._xs: deque[float]                     = deque()
        self._ys: dict[str, deque[int]]            = defaultdict(deque)
        self._curves: dict[str, pg.PlotDataItem]   = {}
        self._labels: dict[str, pg.TextItem]       = {}
        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 컨트롤 행
        ctrl = QHBoxLayout()

        # 패키지명 표시 토글 (기본 ON)
        self._chk_labels = QCheckBox("패키지명 표시")
        self._chk_labels.setChecked(True)
        self._chk_labels.toggled.connect(self._on_toggle_labels)
        ctrl.addWidget(self._chk_labels)

        ctrl.addStretch()

        # 차트에 표시되는 패키지들의 PSS 합계
        self._lbl_chart_sum = QLabel("합계: 0 KB")
        self._lbl_chart_sum.setStyleSheet("font-weight: bold;")
        ctrl.addWidget(self._lbl_chart_sum)

        ctrl.addSpacing(12)

        # 우측 범례
        self._legend_layout = QHBoxLayout()
        ctrl.addLayout(self._legend_layout)
        layout.addLayout(ctrl)

        # pyqtgraph 차트
        self._plot = pg.PlotWidget(
            axisItems={
                "bottom": _TimeAxisItem(orientation="bottom"),
                "left":   _KbAxisItem(orientation="left"),
            }
        )
        self._plot.setBackground("#1E1E2E")
        self._plot.setLabel("left", "PSS (KB)")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        # 과학적 표기 (k/M/G prefix) 차단 — 콤마 포맷만 사용
        self._plot.getAxis("left").enableAutoSIPrefix(False)

        self._vb = self._plot.getPlotItem().getViewBox()
        self._vb.setMouseEnabled(x=True, y=True)
        # PSS 는 음수가 없으므로 Y축을 0 이상으로 클램프
        self._vb.setLimits(yMin=0)
        self._plot.setYRange(0, 1)

        layout.addWidget(self._plot)

    # ── 공개 API ─────────────────────────────────────────────────────────────

    def set_packages(self, packages: list[str]) -> None:
        """모니터링할 패키지 목록 설정 (최대 10개).
        유지되는 패키지의 누적 데이터는 보존, 추가/제거된 패키지만 곡선 정리.
        """
        new_packages = list(packages[:_MAX_PACKAGES])
        new_set      = set(new_packages)

        # 1. 빠진 패키지 곡선/라벨/데이터 제거
        for pkg in list(self._curves.keys()):
            if pkg not in new_set:
                self._plot.removeItem(self._curves.pop(pkg))
                self._ys.pop(pkg, None)
                if pkg in self._labels:
                    self._plot.removeItem(self._labels.pop(pkg))

        # 2. 새 패키지 곡선 + 끝점 텍스트 라벨 추가
        self._packages = new_packages
        labels_visible = self._chk_labels.isChecked()
        for i, pkg in enumerate(self._packages):
            if pkg not in self._curves:
                color = _PALETTE[i % len(_PALETTE)]
                self._curves[pkg] = self._plot.plot(
                    pen=pg.mkPen(color=color, width=2), name=pkg,
                )
                label = pg.TextItem(
                    text=pkg,            # Full 패키지명 (식별성 우선)
                    color=color,
                    anchor=(0, 0),       # top-left 모서리가 데이터 포인트 → 텍스트는 점의 아래/우측에 렌더
                )
                label.setVisible(labels_visible)
                self._plot.addItem(label)
                self._labels[pkg] = label

        # 3. 선택된 패키지가 없으면 시간축도 의미 없음 — 정리
        if not self._packages:
            self._xs.clear()

        self._rebuild_legend()
        self._update_curves()

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
        for label in self._labels.values():
            label.setPos(0, 0)

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _on_toggle_labels(self, checked: bool):
        for label in self._labels.values():
            label.setVisible(checked)

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
            lbl = QLabel(pkg.split(".")[-1])
            lbl.setToolTip(pkg)
            self._legend_layout.addWidget(lbl)

    def _update_curves(self):
        xs = list(self._xs)
        max_y = 0
        total = 0
        for pkg, curve in self._curves.items():
            ys = list(self._ys[pkg])
            n  = min(len(xs), len(ys))
            curve.setData(xs[-n:], ys[-n:])

            # 곡선 끝점에 패키지명 라벨 이동
            if n > 0 and pkg in self._labels:
                self._labels[pkg].setPos(xs[-1], ys[-1])

            if ys:
                local_max = max(ys[-n:]) if n else 0
                if local_max > max_y:
                    max_y = local_max
                total += ys[-1]

        # Y축은 항상 0부터, 상단은 최대값의 110%
        if max_y > 0:
            self._vb.setYRange(0, max_y * 1.1, padding=0)
        else:
            self._vb.setYRange(0, 1, padding=0)

        # 차트 합계 라벨
        self._lbl_chart_sum.setText(f"합계: {total:,} KB")
