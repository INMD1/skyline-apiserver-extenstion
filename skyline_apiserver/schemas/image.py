from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field

class Image(BaseModel):
    id: str
    name: str
    status: str
    visibility: str
    size: int
    disk_format: Optional[str] = None
    owner: str
    created_at: str
    updated_at: str
    tags: List[str]
    min_disk: int
    min_ram: int
    protected: bool

class ImagesResponse(BaseModel):
    images: List[Image]
