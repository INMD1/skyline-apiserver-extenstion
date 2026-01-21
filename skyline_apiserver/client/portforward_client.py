# 외부 포트포워딩 API 클라이언트
# Proxy VM의 포트포워딩 서비스에 HTTP 요청을 보내는 클라이언트

import httpx
from typing import Any, Dict, List, Optional

from skyline_apiserver.config import CONF
from skyline_apiserver.schemas.portforward import (
    PortForwardingCreate,
    PortForwardingUpdate,
    PortForwardingResponse,
    FloatingIPStatus,
    StatusResponse,
    PortAllocationResponse,
)


class PortForwardClientError(Exception):
    """포트포워딩 클라이언트 에러"""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"PortForward API Error ({status_code}): {detail}")


def _get_base_url() -> str:
    """외부 API 기본 URL 반환"""
    url = str(CONF.openstack.portforward_api_url)
    return url.rstrip("/")


def _get_headers(token: Optional[str] = None) -> Dict[str, str]:
    """HTTP 헤더 생성"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _handle_response(response: httpx.Response) -> Dict[str, Any]:
    """응답 처리 및 에러 핸들링"""
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise PortForwardClientError(response.status_code, detail)
    
    if response.status_code == 204:
        return {}
    
    return response.json()


# ===== 포트포워딩 CRUD =====

def create_portforwarding(
    request: PortForwardingCreate,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """포트포워딩 규칙 생성"""
    url = f"{_get_base_url()}/portforward"
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            url,
            headers=_get_headers(token),
            json=request.model_dump(exclude_none=True),
        )
        return _handle_response(response)


def list_portforwardings(
    status_filter: Optional[str] = None,
    floating_ip: Optional[str] = None,
    service_type: Optional[str] = None,
    vm_id: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """포트포워딩 규칙 목록 조회"""
    url = f"{_get_base_url()}/portforward"
    params = {}
    if status_filter:
        params["status_filter"] = status_filter
    if floating_ip:
        params["floating_ip"] = floating_ip
    if service_type:
        params["service_type"] = service_type
    if vm_id:
        params["vm_id"] = vm_id
    
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers=_get_headers(token), params=params)
        return _handle_response(response)


def get_portforwardings_by_vm(
    vm_id: str,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """VM별 포트포워딩 규칙 조회"""
    url = f"{_get_base_url()}/portforward/vm/{vm_id}"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers=_get_headers(token))
        return _handle_response(response)


def get_portforwarding(
    rule_id: str,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """특정 포트포워딩 규칙 조회"""
    url = f"{_get_base_url()}/portforward/{rule_id}"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers=_get_headers(token))
        return _handle_response(response)


def update_portforwarding(
    rule_id: str,
    request: PortForwardingUpdate,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """포트포워딩 규칙 업데이트"""
    url = f"{_get_base_url()}/portforward/{rule_id}"
    with httpx.Client(timeout=30.0) as client:
        response = client.patch(
            url,
            headers=_get_headers(token),
            json=request.model_dump(exclude_none=True),
        )
        return _handle_response(response)


def delete_portforwarding(
    rule_id: str,
    token: Optional[str] = None,
) -> None:
    """포트포워딩 규칙 삭제"""
    url = f"{_get_base_url()}/portforward/{rule_id}"
    with httpx.Client(timeout=30.0) as client:
        response = client.delete(url, headers=_get_headers(token))
        _handle_response(response)


# ===== 상태 조회 =====

def get_status(token: Optional[str] = None) -> Dict[str, Any]:
    """시스템 상태 조회"""
    url = f"{_get_base_url()}/status"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers=_get_headers(token))
        return _handle_response(response)


def get_floating_ips(token: Optional[str] = None) -> List[Dict[str, Any]]:
    """Floating IP 상태 조회"""
    url = f"{_get_base_url()}/floating-ips"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers=_get_headers(token))
        return _handle_response(response)


def preview_port_allocation(
    service_type: str = "other",
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """포트 할당 미리보기"""
    url = f"{_get_base_url()}/port-allocation/preview"
    params = {"service_type": service_type}
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers=_get_headers(token), params=params)
        return _handle_response(response)


def health_check() -> Dict[str, Any]:
    """헬스 체크"""
    url = f"{_get_base_url()}/health"
    with httpx.Client(timeout=10.0) as client:
        response = client.get(url)
        return _handle_response(response)
