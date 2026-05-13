from dataclasses import dataclass, field
import time

ADJ_ORDER = {
    "Native": 0,
    "System": 1,
    "Persistent": 2,
    "Persistent Service": 3,
    "Foreground": 4,
    "Visible": 5,
    "Perceptible": 6,
    "Perceptible Low": 7,
    "A Services": 8,
    "B Services": 9,
    "Picked": 10,
    "Cached": 11,
}


@dataclass
class ProcessEntry:
    adj_category: str
    adj_order: int
    memory_kb: int
    package_name: str
    pid: int
    timestamp: float = field(default_factory=time.time)
    prev_memory_kb: int = 0
    is_new: bool = False
    is_gone: bool = False

    @property
    def memory_mb(self) -> float:
        return round(self.memory_kb / 1024, 1)

    @property
    def delta_kb(self) -> int:
        return self.memory_kb - self.prev_memory_kb


@dataclass
class ADJGroup:
    adj_category: str
    adj_order: int
    total_memory_kb: int = 0
    processes: list = field(default_factory=list)

    @property
    def total_memory_mb(self) -> float:
        return round(self.total_memory_kb / 1024, 1)


@dataclass
class MemInfoSnapshot:
    device_id: str
    timestamp: float
    adj_groups: list = field(default_factory=list)

    @property
    def total_process_count(self) -> int:
        return sum(len(g.processes) for g in self.adj_groups)
