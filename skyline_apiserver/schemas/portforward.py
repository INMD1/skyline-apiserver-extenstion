from pydantic import BaseModel

class PortForwardRequest(BaseModel):
    floating_ip_id: str
    internal_ip: str
    internal_port: int
    external_port: int
    protocol: str = "tcp"