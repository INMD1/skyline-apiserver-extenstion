from pydantic import BaseModel
from typing import List, Dict, Any

class Metric(BaseModel):
    metric: Dict[str, str]
    value: List[Any]

class PerformanceData(BaseModel):
    cpu_usage: List[Metric]
    memory_usage: List[Metric]
    disk_read_bytes: List[Metric]
    disk_write_bytes: List[Metric]
    network_incoming_bytes: List[Metric]
    network_outgoing_bytes: List[Metric]
