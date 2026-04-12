# 포트포워딩 API 스키마 정의
# openapi.json 외부 API 스펙에 맞춰 정의

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ServiceTypeEnum(str, Enum):
    """서비스 유형"""
    ssh = "ssh"
    other = "other"


class ProtocolEnum(str, Enum):
    """프로토콜"""
    tcp = "tcp"
    udp = "udp"


class StatusEnum(str, Enum):
    """상태"""
    active = "active"
    inactive = "inactive"
    error = "error"
    pending = "pending"


# ===== 포트포워딩 생성/조회/수정 =====

class PortForwardingCreate(BaseModel):
    """포트포워딩 규칙 생성 요청"""
    rule_name: str = Field(..., min_length=1, max_length=255, description="규칙 이름")
    user_vm_id: str = Field(..., description="OpenStack Instance UUID")
    user_vm_name: str = Field(..., min_length=1, max_length=255, description="사용자 VM 이름")
    user_vm_internal_ip: str = Field(..., description="내부 VM IP 주소")
    user_vm_internal_port: int = Field(..., ge=1, le=65535, description="내부 포트")
    service_type: ServiceTypeEnum = Field(default=ServiceTypeEnum.other, description="서비스 유형: ssh 또는 other")
    proxy_external_ip: Optional[str] = Field(default=None, description="Floating IP (선택, 자동 선택)")
    proxy_external_port: Optional[int] = Field(default=None, ge=1, le=65535, description="외부 포트 (선택, 자동 할당)")
    protocol: ProtocolEnum = Field(default=ProtocolEnum.tcp, description="TCP 또는 UDP")
    description: Optional[str] = Field(default=None, max_length=500, description="규칙 설명")


class PortForwardingResponse(BaseModel):
    """포트포워딩 규칙 응답"""
    id: int
    rule_id: str
    rule_name: str
    user_vm_id: str
    user_vm_name: str
    user_vm_internal_ip: str
    user_vm_internal_port: int
    proxy_external_ip: str
    proxy_external_port: int
    protocol: str
    service_type: str
    status: str
    is_persistent: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    description: Optional[str]


class PortForwardingUpdate(BaseModel):
    """포트포워딩 규칙 업데이트 요청"""
    rule_name: Optional[str] = None
    user_vm_name: Optional[str] = None
    user_vm_internal_port: Optional[int] = Field(default=None, ge=1, le=65535)
    proxy_external_port: Optional[int] = Field(default=None, ge=1, le=65535)
    protocol: Optional[ProtocolEnum] = None
    status: Optional[StatusEnum] = None
    description: Optional[str] = None


# ===== 상태 관련 스키마 =====

class FloatingIPStatus(BaseModel):
    """Floating IP 상태"""
    ip: str
    role: str
    active_rules: int
    total_rules: int = Field(default=0, description="전체 규칙 수")
    max_rules: int
    usage_percent: float
    available_ports: int
    port_range: List[int] = Field(default_factory=list, description="포트 범위 [min, max]")
    ports: List[int]


class StatusResponse(BaseModel):
    """시스템 상태 응답"""
    total_rules: int
    active_rules: int
    inactive_rules: int
    pending_rules: int
    used_ports: int
    available_ports: int
    floating_ips: dict


class PortAllocationResponse(BaseModel):
    """포트 할당 미리보기 응답"""
    floating_ip: str
    external_port: int
    role: str


# ===== 목록 조회 필터 (Query Parameters) =====

class PortForwardingListFilter(BaseModel):
    """포트포워딩 목록 조회 필터"""
    status_filter: Optional[str] = None
    floating_ip: Optional[str] = None
    service_type: Optional[str] = None
    vm_id: Optional[str] = None


# ===== 레거시 호환성 (점진적 마이그레이션용) =====

class PortForwardRequest(BaseModel):
    """레거시: 기존 포트포워딩 생성 요청 (호환성 유지용)"""
    floating_ip_id: str
    internal_ip: str
    internal_port: int
    external_port: int
    protocol: str = "tcp"


class PortForwardResponse(BaseModel):
    """레거시: 기존 포트포워딩 응답 (호환성 유지용)"""
    floating_ip_address: str
    internal_ip_address: str
    internal_port: int
    external_port: int
    protocol: str
    status: str
    assigned_port: Optional[int] = None
    public_ip: Optional[str] = None