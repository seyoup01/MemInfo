import csv
import json
from datetime import datetime

from core.data_models import MemInfoSnapshot

_CSV_FIELDS = ["timestamp", "device_id", "adj", "package", "pid", "memory_kb"]


class Exporter:
    @staticmethod
    def export_csv(records: list[dict], file_path: str) -> None:
        """HistoryManager.get_all_for_export() 결과를 CSV로 저장."""
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)

    @staticmethod
    def export_json(records: list[dict], file_path: str) -> None:
        """HistoryManager.get_all_for_export() 결과를 JSON으로 저장."""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    @staticmethod
    def export_current_view_csv(snapshot: MemInfoSnapshot, file_path: str) -> None:
        """현재 스냅샷을 단건 CSV로 저장."""
        ts = datetime.fromtimestamp(snapshot.timestamp).isoformat()
        rows = [
            {
                "timestamp": ts,
                "device_id": snapshot.device_id,
                "adj":       p.adj_category,
                "package":   p.package_name,
                "pid":       p.pid,
                "memory_kb": p.memory_kb,
            }
            for g in snapshot.adj_groups
            for p in g.processes
        ]
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
