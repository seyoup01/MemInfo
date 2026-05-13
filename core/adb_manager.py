import os
import shutil
import subprocess
import time
from dataclasses import dataclass

from PyQt6.QtCore import QThread, pyqtSignal


# ── ADB 경로 해석 ─────────────────────────────────────────────────────────────

def resolve_adb_path() -> str:
    """번들 ADB → 시스템 PATH 순으로 탐색. 없으면 FileNotFoundError."""
    bundle = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "adb", "adb.exe",
    )
    if os.path.isfile(bundle):
        return bundle

    system_adb = shutil.which("adb")
    if system_adb:
        return system_adb

    raise FileNotFoundError(
        "ADB를 찾을 수 없습니다. assets/adb/adb.exe를 배치하거나 "
        "Android SDK Platform-Tools를 PATH에 추가하세요."
    )


# ── 데이터 클래스 ─────────────────────────────────────────────────────────────

@dataclass
class AdbDevice:
    serial: str
    model: str
    status: str  # "online" / "offline" / "unauthorized"


# ── AdbManager ────────────────────────────────────────────────────────────────

class AdbManager:
    """실제 ADB 실행 파일을 subprocess로 호출하는 매니저."""

    TIMEOUT = 5  # 초

    def __init__(self):
        self._adb = resolve_adb_path()

    def _run(self, *args) -> str:
        """ADB 명령 실행. 실패/타임아웃 시 빈 문자열 반환."""
        try:
            result = subprocess.run(
                [self._adb, *args],
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT,
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            return ""
        except Exception:
            return ""

    def get_devices(self) -> list[AdbDevice]:
        """연결된 기기 목록 반환. 각 기기의 모델명도 조회."""
        output = self._run("devices")
        devices: list[AdbDevice] = []

        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            serial = parts[0]
            status = parts[1]  # online / offline / unauthorized

            model = self._get_model(serial) if status == "online" else ""
            devices.append(AdbDevice(serial=serial, model=model, status=status))

        return devices

    def _get_model(self, serial: str) -> str:
        raw = self._run("-s", serial, "shell", "getprop", "ro.product.model")
        return raw.strip() or "Unknown"

    def test_connection(self, serial: str) -> bool:
        """기기와 통신 가능한지 echo 명령으로 확인."""
        raw = self._run("-s", serial, "shell", "echo", "ok")
        return raw.strip() == "ok"

    def run_meminfo(self, serial: str) -> str:
        """dumpsys meminfo 실행. 실패 시 빈 문자열 반환 (예외 상위 전파 금지)."""
        return self._run("-s", serial, "shell", "dumpsys", "meminfo")

    def is_device_online(self, serial: str) -> bool:
        return self.test_connection(serial)


# ── ReconnectWorker ───────────────────────────────────────────────────────────

class ReconnectWorker(QThread):
    reconnected        = pyqtSignal()
    failed_permanently = pyqtSignal()

    def __init__(
        self,
        adb_manager,
        serial: str,
        max_retries: int  = 10,
        interval_sec: int = 3,
        parent=None,
    ):
        super().__init__(parent)
        self.adb_manager  = adb_manager
        self.serial       = serial
        self.max_retries  = max_retries
        self.interval_sec = interval_sec

    def run(self):
        for _ in range(self.max_retries):
            time.sleep(self.interval_sec)
            if self.adb_manager.test_connection(self.serial):
                self.reconnected.emit()
                return
        self.failed_permanently.emit()


# ── MockAdbManager ────────────────────────────────────────────────────────────

class MockAdbManager:
    """ADB 없이 테스트할 수 있는 Mock. sample_meminfo.txt를 읽어 반환."""

    _FIXTURE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", "fixtures", "sample_meminfo.txt",
    )

    def get_devices(self) -> list[AdbDevice]:
        return [AdbDevice("emulator-5554", "Mock_Device", "online")]

    def run_meminfo(self, serial: str) -> str:
        try:
            with open(self._FIXTURE, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def test_connection(self, serial: str) -> bool:
        return True

    def is_device_online(self, serial: str) -> bool:
        return True
