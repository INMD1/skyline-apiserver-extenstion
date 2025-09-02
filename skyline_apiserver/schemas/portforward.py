# 포트 포워딩 API와 관련된 데이터 스키마를 정의하는 파일입니다.
from pydantic import BaseModel

class PortForwardRequest(BaseModel):
    floating_ip_id: str
    internal_ip: str
    internal_port: int
    external_port: int
    protocol: str = "tcp"

class PortForwardResponse(BaseModel):
    floating_ip_address: str
    internal_ip_address: str
    internal_port: int
    external_port: int
    protocol: str
    status: str
    assigned_port: int
    public_ip: str