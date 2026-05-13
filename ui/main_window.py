import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog, QInputDialog, QMainWindow,
    QMessageBox, QTabWidget,
)

from core.adb_manager import AdbManager, MockAdbManager, ReconnectWorker
from core.alert_manager import AlertManager
from core.history_manager import HistoryManager
from core.meminfo_parser import parse as meminfo_parse
from core.polling_worker import PollingWorker
from ui.alert_log_panel import AlertLogPanel
from ui.chart_view import ChartView
from ui.fast_update_window import FastUpdateWindow
from ui.main_view import MainView
from ui.selection_view import SelectionView
from ui.status_bar import StatusBar
from ui.threshold_view import ThresholdView
from ui.toolbar import Toolbar
from utils.exporter import Exporter
from utils.settings import Settings


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings          = Settings()
        self._adb, self._adb_mock = self._create_adb_manager()
        self._worker: PollingWorker | None           = None
        self._reconnect: ReconnectWorker | None      = None
        self._fast_win: FastUpdateWindow | None      = None
        self._fast_was_running                       = False
        self._collection_num    = 0
        self._start_time: float | None = None
        self._paused            = False
        self._error_count       = 0
        self._alert_manager     = AlertManager(
            alert_sound=self._settings.get("alert_sound") or True
        )
        self._history           = HistoryManager(
            max_records=self._settings.get("max_history") or 1000
        )

        self._build_ui()
        self._build_menu()
        self._connect_signals()
        self._refresh_devices()

    # ── ADB 매니저 초기화 ────────────────────────────────────────────────────

    @staticmethod
    def _create_adb_manager() -> tuple:
        """ADB 실행 파일이 있으면 AdbManager, 없으면 MockAdbManager 반환."""
        try:
            mgr = AdbManager()
            return mgr, False   # (manager, is_mock)
        except FileNotFoundError:
            return MockAdbManager(), True

    # ── UI 구성 ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("Android PSS Memory Monitor")
        self.setMinimumSize(1280, 720)

        # 툴바
        self.toolbar = Toolbar()
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._wrap_toolbar())

        # 탭
        self.tabs = QTabWidget()

        self.main_view      = MainView()
        self.threshold_view = ThresholdView()
        self.selection_view = SelectionView()

        self.chart_view = ChartView()

        self.tabs.addTab(self.main_view,      "📋 Main View")
        self.tabs.addTab(self.threshold_view, "🔍 Threshold Filter")
        self.tabs.addTab(self.selection_view, "📌 Process Select")
        self.tabs.addTab(self.chart_view,     "📈 Chart")

        self.setCentralWidget(self.tabs)

        # 알림 로그 패널 (기본 숨김)
        self.alert_log = AlertLogPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.alert_log)
        self.alert_log.hide()

        # 상태바
        self.status_bar = StatusBar()
        self.setStatusBar(self.status_bar)

    def _build_menu(self):
        mbar = self.menuBar()

        # 파일 메뉴
        file_menu = mbar.addMenu("파일(&F)")

        act_csv_view = QAction("현재 뷰 CSV 저장...", self)
        act_csv_view.setShortcut(QKeySequence("Ctrl+S"))
        act_csv_view.triggered.connect(self._export_current_csv)
        file_menu.addAction(act_csv_view)

        act_csv_all = QAction("전체 히스토리 CSV 저장...", self)
        act_csv_all.triggered.connect(self._export_history_csv)
        file_menu.addAction(act_csv_all)

        act_json_all = QAction("전체 히스토리 JSON 저장...", self)
        act_json_all.triggered.connect(self._export_history_json)
        file_menu.addAction(act_json_all)

        file_menu.addSeparator()

        act_quit = QAction("종료", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # 설정 메뉴
        set_menu = mbar.addMenu("설정(&S)")

        act_max_hist = QAction("히스토리 최대 건수...", self)
        act_max_hist.triggered.connect(self._set_max_history)
        set_menu.addAction(act_max_hist)

        act_sound = QAction("알림음 On/Off", self)
        act_sound.setCheckable(True)
        act_sound.setChecked(bool(self._settings.get("alert_sound")))
        act_sound.toggled.connect(
            lambda on: self._settings.set("alert_sound", on)
        )
        set_menu.addAction(act_sound)

        act_clear_hist = QAction("히스토리 초기화", self)
        act_clear_hist.triggered.connect(self._clear_history)
        set_menu.addAction(act_clear_hist)

        set_menu.addSeparator()

        act_reload_adb = QAction("ADB 재탐색", self)
        act_reload_adb.setToolTip("ADB 설치 후 재탐색하여 실제 기기 연결")
        act_reload_adb.triggered.connect(self._reload_adb)
        set_menu.addAction(act_reload_adb)

    def _wrap_toolbar(self):
        from PyQt6.QtWidgets import QToolBar
        qt_toolbar = QToolBar("메인 툴바", self)
        qt_toolbar.setMovable(False)
        qt_toolbar.addWidget(self.toolbar)
        return qt_toolbar

    # ── 시그널 연결 ───────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.toolbar.refresh_devices.connect(self._refresh_devices)
        self.toolbar.device_selected.connect(self._on_device_selected)
        self.toolbar.interval_changed.connect(self._on_interval_changed)
        self.toolbar.start_clicked.connect(self._on_start)
        self.toolbar.pause_clicked.connect(self._on_pause)
        self.toolbar.stop_clicked.connect(self._on_stop)
        self.selection_view.chart_requested.connect(self._on_chart_requested)
        # Process Select 의 체크박스 변경이 즉시 Chart 에 반영되도록 자동 동기화
        self.selection_view.selection_changed.connect(self._on_selection_changed)
        # 차트 빠르게 Update — 별도 윈도우
        self.selection_view.fast_chart_requested.connect(self._on_fast_chart_requested)

    # ── 슬롯 ─────────────────────────────────────────────────────────────────

    def _refresh_devices(self):
        # ADB 없이 실행 중이면 경고 표시
        if self._adb_mock:
            self.status_bar.showMessage(
                "⚠ ADB를 찾을 수 없습니다. Mock 모드로 실행 중 — "
                "Android SDK Platform-Tools를 설치하고 PATH에 추가하세요.",
                0,  # 0 = 영구 표시
            )

        devices = self._adb.get_devices()
        self.toolbar.populate_devices(devices)
        last = self._settings.get("last_device")
        if last:
            for i in range(self.toolbar.device_combo.count()):
                if self.toolbar.device_combo.itemData(i) == last:
                    self.toolbar.device_combo.setCurrentIndex(i)
                    break
        if devices:
            self.status_bar.update_status(connected=not self._adb_mock)

    def _on_device_selected(self, serial: str):
        ok = self._adb.test_connection(serial)
        self.status_bar.update_status(connected=ok)
        self._settings.set("last_device", serial)

    def _on_interval_changed(self, sec: int):
        if self._worker and self._worker.isRunning():
            self._worker.set_interval(sec)

    def _on_start(self):
        if self._paused and self._worker:
            # 일시정지 → 재개
            self._paused = False
            self._worker.set_interval(self.toolbar.current_interval_sec())
            return

        self._start_worker()

    def _on_pause(self):
        if self._worker and self._worker.isRunning():
            if not self._paused:
                # 폴링 주기를 매우 길게 설정하여 사실상 정지
                self._worker.set_interval(99999)
                self._paused = True
            else:
                self._worker.set_interval(self.toolbar.current_interval_sec())
                self._paused = False

    def _on_stop(self):
        self._stop_worker()
        self._collection_num = 0
        self._start_time = None
        self._paused = False
        self.toolbar.reset_start_button()

    def _on_snapshot(self, snapshot):
        self._collection_num += 1
        self._error_count = 0   # 성공 시 에러 카운트 리셋
        self._last_snap = snapshot
        self.main_view.update_data(snapshot)
        self.threshold_view.update_data(snapshot)
        self.selection_view.update_data(snapshot)
        self.chart_view.add_data_point(snapshot)
        self._history.save_snapshot(snapshot)

        # 알림 확인
        fired = self._alert_manager.check_snapshot(snapshot)
        if fired:
            self._alert_manager.fire_alerts(fired, snapshot)
            proc_map = {
                p.package_name: p
                for g in snapshot.adj_groups for p in g.processes
            }
            for pkg in fired:
                proc = proc_map.get(pkg)
                rule = self._alert_manager.rules().get(pkg)
                if proc and rule:
                    self.alert_log.add_alert(pkg, proc.memory_kb, rule.threshold_kb)
            self.alert_log.show()

        elapsed = int(time.time() - self._start_time) if self._start_time else 0
        self.status_bar.update_last_time(snapshot.timestamp)
        self.status_bar.update_collection(
            process_count=snapshot.total_process_count,
            collection_num=self._collection_num,
            elapsed_sec=elapsed,
        )

    def _on_error(self, msg: str):
        self._error_count += 1
        self.status_bar.showMessage(f"오류: {msg}", 3000)
        if self._error_count >= 3 and self._reconnect is None:
            serial = self.toolbar.current_serial()
            if serial:
                self._start_reconnect(serial)

    def _start_reconnect(self, serial: str):
        self._reconnect = ReconnectWorker(self._adb, serial)
        self._reconnect.reconnected.connect(self._on_reconnected)
        self._reconnect.failed_permanently.connect(self._on_reconnect_failed)
        self._reconnect.start()
        self.status_bar.update_status(connected=False, reconnecting=True)

    def _on_reconnected(self):
        self._reconnect = None
        self._error_count = 0
        self.status_bar.update_status(connected=True)
        self._start_worker()

    def _on_reconnect_failed(self):
        self._reconnect = None
        self._stop_worker()
        QMessageBox.warning(
            self, "재연결 실패",
            "기기에 재연결하지 못했습니다.\n수동으로 연결 후 다시 시작하세요."
        )

    def _on_selection_changed(self, packages: list):
        """Process Select 의 체크박스 변경을 Chart 에 즉시 반영 (데이터 보존)."""
        self.chart_view.set_packages(packages)

    def _on_chart_requested(self, packages: list):
        """'차트 보기 ▶' 버튼: 패키지 정합성 + Chart 탭으로 전환."""
        self.chart_view.set_packages(packages)
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i).endswith("Chart"):
                self.tabs.setCurrentIndex(i)
                break

    def _on_fast_chart_requested(self, pairs: list):
        """'차트 빠르게 Update': 메인 폴링 중단 + 별도 윈도우로 grep 병렬 폴링."""
        if not pairs:
            return
        if self._fast_win is not None:
            self._fast_win.raise_()
            self._fast_win.activateWindow()
            return

        self._fast_was_running = bool(self._worker and self._worker.isRunning())
        self._stop_worker()                # 전체 dumpsys 폴링 중단

        serial = self.toolbar.current_serial()
        self._fast_win = FastUpdateWindow(self._adb, serial, pairs, self)
        self._fast_win.closed.connect(self._on_fast_window_closed)
        self._fast_win.show()

    def _on_fast_window_closed(self):
        """fast 윈도우가 닫혔을 때 — 이전에 폴링 중이었다면 재개."""
        self._fast_win = None
        if self._fast_was_running:
            self._fast_was_running = False
            self._start_worker()

    # ── 메뉴 액션 핸들러 ─────────────────────────────────────────────────────

    def _reload_adb(self):
        """ADB를 재탐색하여 실제 기기 연결로 전환."""
        self._stop_worker()
        self._adb, self._adb_mock = self._create_adb_manager()
        if self._adb_mock:
            QMessageBox.warning(
                self, "ADB 없음",
                "ADB를 찾을 수 없습니다.\n\n"
                "Android SDK Platform-Tools를 설치하고\n"
                "PATH에 추가한 뒤 다시 시도하세요.\n\n"
                "다운로드: https://developer.android.com/tools/releases/platform-tools"
            )
        else:
            self.status_bar.clearMessage()
            QMessageBox.information(self, "ADB 연결", "ADB를 찾았습니다. 기기 목록을 새로고침합니다.")
        self._refresh_devices()

    def _export_current_csv(self):
        if not hasattr(self, '_last_snap') or self._last_snap is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "현재 뷰 CSV 저장", "", "CSV 파일 (*.csv)"
        )
        if path:
            Exporter.export_current_view_csv(self._last_snap, path)

    def _export_history_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "히스토리 CSV 저장", "", "CSV 파일 (*.csv)"
        )
        if path:
            Exporter.export_csv(self._history.get_all_for_export(), path)

    def _export_history_json(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "히스토리 JSON 저장", "", "JSON 파일 (*.json)"
        )
        if path:
            Exporter.export_json(self._history.get_all_for_export(), path)

    def _set_max_history(self):
        current = self._settings.get("max_history") or 1000
        val, ok = QInputDialog.getInt(
            self, "히스토리 최대 건수", "최대 레코드 수:",
            value=current, min=100, max=100_000, step=100,
        )
        if ok:
            self._settings.set("max_history", val)
            self._history.max_records = val

    def _clear_history(self):
        if QMessageBox.question(
            self, "히스토리 초기화",
            "저장된 히스토리를 모두 삭제하시겠습니까?",
        ) == QMessageBox.StandardButton.Yes:
            self._history.clear()

    # ── 워커 관리 ─────────────────────────────────────────────────────────────

    def _start_worker(self):
        self._stop_worker()
        serial = self.toolbar.current_serial()
        if not serial:
            return

        self._start_time = time.time()
        self._collection_num = 0
        interval = self.toolbar.current_interval_sec()

        self._worker = PollingWorker(self._adb, meminfo_parse, serial, interval)
        self._worker.snapshot_ready.connect(self._on_snapshot)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()
        self.status_bar.update_status(connected=True)

    def _stop_worker(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        self._worker = None

    # ── 창 닫기 ───────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        # fast update 윈도우가 열려 있으면 함께 정리
        if self._fast_win is not None:
            try:
                self._fast_win.close()
            except Exception:
                pass
            self._fast_win = None
        self._stop_worker()
        if self._reconnect and self._reconnect.isRunning():
            self._reconnect.terminate()
            self._reconnect.wait(1000)
        serial = self.toolbar.current_serial()
        if serial:
            self._settings.set("last_device", serial)
        super().closeEvent(event)
