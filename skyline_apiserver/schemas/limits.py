from pydantic import BaseModel
from typing import Dict, Any, Optional

class QuotaUsage(BaseModel):
    in_use: int
    limit: int
    reserved: Optional[int] = 0

class QuotaSet(BaseModel):
    instances: QuotaUsage
    cores: QuotaUsage
    ram: QuotaUsage
    volumes: QuotaUsage
    snapshots: QuotaUsage
    gigabytes: QuotaUsage
    floatingip: QuotaUsage
    network: QuotaUsage
    port: QuotaUsage
    router: QuotaUsage
    subnet: QuotaUsage
    security_group: QuotaUsage
    security_group_rule: QuotaUsage
    port_forwardings: QuotaUsage

class LimitSummary(BaseModel):
    quotas: QuotaSet