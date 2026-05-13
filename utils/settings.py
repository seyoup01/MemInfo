import json
import os

_SETTINGS_DIR = os.path.join(os.path.expanduser("~"), ".meminfo_monitor")
_SETTINGS_PATH = os.path.join(_SETTINGS_DIR, "settings.json")

DEFAULTS: dict = {
    "poll_interval_sec": 5,
    "threshold_kb": 50000,
    "threshold_unit": "KB",
    "selected_packages": [],
    "alert_rules": {},
    "alert_sound": True,
    "max_history": 1000,
    "last_device": "",
    "chart_sample_count": 200,
    "collapsed_adj_groups": [],
}


class Settings:
    def __init__(self, path: str = _SETTINGS_PATH):
        self._path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._data: dict = {}
        self._load()

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if os.path.isfile(self._path):
            try:
                with open(self._path, encoding="utf-8") as f:
                    loaded = json.load(f)
                # 기본값에 없는 키가 파일에 있어도 허용,
                # 파일에 없는 키는 기본값으로 채움
                self._data = {**DEFAULTS, **loaded}
            except (json.JSONDecodeError, OSError):
                self._data = dict(DEFAULTS)
        else:
            self._data = dict(DEFAULTS)
            self._save()

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ── 공개 API ─────────────────────────────────────────────────────────────

    def get(self, key: str):
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._save()

    def reset(self) -> None:
        self._data = dict(DEFAULTS)
        self._save()
