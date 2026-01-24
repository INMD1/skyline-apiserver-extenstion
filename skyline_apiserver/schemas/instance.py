from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class Console(BaseModel):
    url: str
    type: str

class Instance(BaseModel):
    id: str
    name: str
    status: str
    addresses: Dict[str, Any]
    created: str
    flavor: Dict[str, Any]
    image: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True