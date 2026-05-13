import winsound
from dataclasses import dataclass, field

from core.data_models import MemInfoSnapshot

try:
    from plyer import notification as _plyer_notify
    _PLYER_OK = True
except Exception:
    _PLYER_OK = False

_RESET_RATIO = 0.9   # 마지막 알림 KB의 90% 미만으로 내려가면 triggered 리셋


@dataclass
class AlertRule:
    package_name:   str
    threshold_kb:   int
    last_alert_kb:  int  = 0
    triggered:      bool = False


class AlertManager:
    def __init__(self, alert_sound: bool = True):
        self._rules: dict[str, AlertRule] = {}
        self._alert_sound = alert_sound

    # ── 규칙 관리 ─────────────────────────────────────────────────────────────

    def set_rule(self, package_name: str, threshold_kb: int) -> None:
        if package_name in self._rules:
            self._rules[package_name].threshold_kb = threshold_kb
        else:
            self._rules[package_name] = AlertRule(package_name, threshold_kb)

    def remove_rule(self, package_name: str) -> None:
        self._rules.pop(package_name, None)

    def rules(self) -> dict[str, AlertRule]:
        return dict(self._rules)

    # ── 스냅샷 확인 ──────────────────────────────────────────────────────────

    def check_snapshot(self, snapshot: MemInfoSnapshot) -> list[str]:
        """임계값 초과 패키지 리스트 반환. 내부 triggered 상태 갱신."""
        proc_map = {
            p.package_name: p
            for g in snapshot.adj_groups
            for p in g.processes
        }
        fired: list[str] = []

        for pkg, rule in self._rules.items():
            proc = proc_map.get(pkg)
            if proc is None:
                continue

            mem = proc.memory_kb

            if not rule.triggered:
                if mem > rule.threshold_kb:
                    rule.triggered     = True
                    rule.last_alert_kb = mem
                    fired.append(pkg)
            else:
                # 마지막 알림 KB의 90% 아래로 내려가면 리셋
                if mem < rule.last_alert_kb * _RESET_RATIO:
                    rule.triggered = False

        return fired

    # ── 알림 발송 ─────────────────────────────────────────────────────────────

    def fire_alerts(
        self, packages: list[str], snapshot: MemInfoSnapshot
    ) -> None:
        if not packages:
            return

        proc_map = {
            p.package_name: p
            for g in snapshot.adj_groups
            for p in g.processes
        }

        for pkg in packages:
            proc = proc_map.get(pkg)
            mem_mb = f"{proc.memory_kb / 1024:.1f} MB" if proc else "?"
            rule   = self._rules.get(pkg)
            thr_mb = f"{rule.threshold_kb / 1024:.1f} MB" if rule else "?"

            if _PLYER_OK:
                try:
                    _plyer_notify.notify(
                        title="메모리 임계값 초과",
                        message=f"{pkg}\n현재: {mem_mb} / 임계값: {thr_mb}",
                        app_name="MemInfoMonitor",
                        timeout=5,
                    )
                except Exception:
                    pass

        if self._alert_sound:
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass
