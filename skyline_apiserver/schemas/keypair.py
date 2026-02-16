from datetime import datetime

class Keypair(BaseModel):
    name: str
    fingerprint: str
    public_key: str
    type: str
    created_at: Optional[datetime] = None

class KeypairDetail(Keypair):
    private_key: Optional[str] = None

class KeypairsResponse(BaseModel):
    keypairs: List[Keypair]

class KeypairCreate(BaseModel):
    name: str
    public_key: Optional[str] = None
