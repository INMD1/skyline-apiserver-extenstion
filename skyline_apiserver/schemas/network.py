from pydantic import BaseModel
from typing import List, Optional

class Network(BaseModel):
    id: str
    name: str
    status: str
    subnets: List[str]
    tenant_id: str
    admin_state_up: bool
    shared: bool

    class Config:
        from_attributes = True

class NetworkList(BaseModel):
    networks: List[Network]
