from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class Flavor(BaseModel):
    id: str
    name: str
    vcpus: int
    ram: int
    disk: int
    is_public: bool
    extra_specs: Dict[str, Any]

class FlavorsResponse(BaseModel):
    flavors: List[Flavor]
