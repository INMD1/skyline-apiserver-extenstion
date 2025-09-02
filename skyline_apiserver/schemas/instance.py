from pydantic import BaseModel

class Console(BaseModel):
    url: str
    type: str
