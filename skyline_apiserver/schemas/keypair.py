from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel

class Keypair(BaseModel):
    name: str
    fingerprint: str
    public_key: str
    type: str

class KeypairDetail(Keypair):
    private_key: Optional[str] = None

class KeypairsResponse(BaseModel):
    keypairs: List[Keypair]

class KeypairCreate(BaseModel):
    name: str
    public_key: Optional[str] = None
