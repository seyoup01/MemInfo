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

    # dumpsys meminfo 는 부하 큰 기기에서 15초 이상 걸릴 수 있어 30초로 설정
    TIMEOUT       = 30   # run_meminfo 전용
    TIMEOUT_SHORT = 5    # devices/getprop/echo 등 즉답 명령용

    def __init__(self):
        self._adb = resolve_adb_path()

    def _run(self, *args, timeout: int | None = None) -> str:
        """ADB 명령 실행. 실패/타임아웃 시 빈 문자열 반환."""
        try:
            result = subprocess.run(
                [self._adb, *args],
                capture_output=True,
                text=True,
                timeout=timeout if timeout is not None else self.TIMEOUT_SHORT,
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            return ""
        except Exception:
            return ""

    def get_devices(self) -> list[AdbDevice]:
        """연결된 기기 목록 반환. 각 기기의 모델명도 조회."""
        output = self._run("devices", timeout=self.TIMEOUT_SHORT)
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
        raw = self._run(
            "-s", serial, "shell", "getprop", "ro.product.model",
            timeout=self.TIMEOUT_SHORT,
        )
        return raw.strip() or "Unknown"

    def test_connection(self, serial: str) -> bool:
        """기기와 통신 가능한지 echo 명령으로 확인."""
        raw = self._run(
            "-s", serial, "shell", "echo", "ok",
            timeout=self.TIMEOUT_SHORT,
        )
        return raw.strip() == "ok"

    def run_meminfo(self, serial: str) -> str:
        """dumpsys meminfo 실행. 실패 시 빈 문자열 반환 (예외 상위 전파 금지)."""
        return self._run(
            "-s", serial, "shell", "dumpsys", "meminfo",
            timeout=self.TIMEOUT,
        )

    def run_meminfo_for_pid(self, serial: str, pid: int) -> str:
        """dumpsys meminfo | grep 'pid <N>' 실행. 4줄 정도의 짧은 응답.
        파이프와 따옴표는 device 측 sh 가 해석.
        """
        return self._run(
            "-s", serial, "shell", f"dumpsys meminfo | grep 'pid {pid}'",
            timeout=self.TIMEOUT,
        )

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
                raw = f.read()
        except FileNotFoundError:
            return ""
        # 픽스처에 Tuning: 라인이 없으면 PollingWorker 완료성 검증을 위해 append
        if "Tuning:" not in raw:
            raw = raw.rstrip() + "\n   Tuning: 512 (large 512), oom 322,560K\n"
        return raw

    def run_meminfo_for_pid(self, serial: str, pid: int) -> str:
        """전체 meminfo 에서 해당 PID 라인만 grep 형태로 시뮬레이션 (4줄)."""
        try:
            with open(self._FIXTURE, encoding="utf-8") as f:
                raw = f.read()
        except FileNotFoundError:
            return ""
        # 실제 grep 결과를 흉내내기 어려우므로 픽스처에서 해당 pid 포함 라인 추출 후
        # 4줄이 안 되면 (PSS by process 1줄 + OOM 2줄) 형태로 합성하여 반환.
        lines = [l for l in raw.splitlines() if f"(pid {pid})" in l]
        if not lines:
            return ""
        # 테스트 호환: 최소 3줄 확보 (3번째 줄을 fast worker 가 사용)
        while len(lines) < 4:
            lines.append(lines[-1])
        return "\n".join(lines[:4]) + "\n"

    def test_connection(self, serial: str) -> bool:
        return True

    def is_device_online(self, serial: str) -> bool:
        return True
