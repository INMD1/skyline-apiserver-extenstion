# 포트포워딩 API 엔드포인트
# 외부 Proxy VM API로 프록시하는 엔드포인트 제공
#
# Copyright 2025 INMD1
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client import portforward_client, utils
from skyline_apiserver.client.openstack import nova
from skyline_apiserver.client.portforward_client import PortForwardClientError
from skyline_apiserver.schemas.portforward import (
    FloatingIPStatus,
    PortAllocationResponse,
    PortForwardingCreate,
    PortForwardingResponse,
    PortForwardingUpdate,
    ServiceTypeEnum,
    StatusResponse,
)
from skyline_apiserver.utils.roles import is_system_admin

router = APIRouter()


def _handle_client_error(e: PortForwardClientError):
    """클라이언트 에러를 HTTP 예외로 변환"""
    raise HTTPException(status_code=e.status_code, detail=e.detail)


def _get_owned_server(profile: schemas.Profile, vm_id: str):
    """Return a VM only when it belongs to the current project."""
    session = utils.generate_session(profile)
    try:
        server = nova.get_server(session, profile, vm_id)
    except Exception:
        raise HTTPException(status_code=404, detail="VM not found")

    owner_id = getattr(server, "tenant_id", None) or getattr(server, "project_id", None)
    if owner_id and owner_id != profile.project.id and not is_system_admin(profile):
        raise HTTPException(status_code=403, detail="VM does not belong to this project")
    return server


def _assert_rule_access(profile: schemas.Profile, rule: dict) -> None:
    if is_system_admin(profile):
        return
    vm_id = rule.get("user_vm_id")
    if not vm_id:
        raise HTTPException(status_code=403, detail="Rule ownership cannot be verified")
    _get_owned_server(profile, vm_id)


def _project_server_ids(profile: schemas.Profile) -> set[str]:
    session = utils.generate_session(profile)
    servers = nova.list_servers(
        profile=profile,
        session=session,
        global_request_id="",
        search_opts={"project_id": profile.project.id},
    )
    return {server.id for server in servers}


# ===== 정적 경로 (먼저 정의 - FastAPI 라우팅 우선순위) =====


@router.get("/health", tags=["Network"])
async def health_check():
    """외부 포트포워딩 서비스 헬스 체크"""
    try:
        result = await portforward_client.health_check()
        return result
    except PortForwardClientError as e:
        _handle_client_error(e)


@router.get("/status", response_model=StatusResponse, tags=["Network"])
async def get_status(
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """시스템 상태 조회"""
    try:
        result = await portforward_client.get_status(None)  # 설정 파일의 키 사용
        return result
    except PortForwardClientError as e:
        _handle_client_error(e)


@router.get("/floating-ips", response_model=List[FloatingIPStatus], tags=["Network"])
async def get_floating_ips(
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """Floating IP 상태 조회"""
    try:
        result = await portforward_client.get_floating_ips(None)  # 설정 파일의 키 사용
        return result
    except PortForwardClientError as e:
        _handle_client_error(e)


@router.get("/port-allocation/preview", response_model=PortAllocationResponse, tags=["Network"])
async def preview_port_allocation(
    service_type: ServiceTypeEnum = Query(ServiceTypeEnum.other, description="서비스 유형"),
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """포트 할당 미리보기"""
    try:
        result = await portforward_client.preview_port_allocation(
            service_type.value, None
        )  # 설정 파일의 키 사용
        return result
    except PortForwardClientError as e:
        _handle_client_error(e)


@router.get(
    "/portforward/vm/{vm_id}", response_model=List[PortForwardingResponse], tags=["Network"]
)
async def get_portforwardings_by_vm(
    vm_id: str,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """VM별 포트포워딩 규칙 조회"""
    try:
        _get_owned_server(profile, vm_id)
        result = await portforward_client.get_portforwardings_by_vm(vm_id, None)
        return result
    except PortForwardClientError as e:
        _handle_client_error(e)


# ===== 포트포워딩 CRUD =====


@router.post(
    "/portforward", response_model=PortForwardingResponse, status_code=201, tags=["Network"]
)
async def create_portforwarding(
    request: PortForwardingCreate,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """포트포워딩 규칙 생성"""
    try:
        server = _get_owned_server(profile, request.user_vm_id)
        internal_ips = {
            address.get("addr")
            for addresses in getattr(server, "addresses", {}).values()
            for address in addresses
            if address.get("OS-EXT-IPS:type") == "fixed"
        }
        if request.user_vm_internal_ip not in internal_ips:
            raise HTTPException(
                status_code=400,
                detail="Internal IP does not belong to the selected VM",
            )
        if request.user_vm_name != server.name:
            raise HTTPException(
                status_code=400,
                detail="VM name does not match the selected VM",
            )
        result = await portforward_client.create_portforwarding(request, None)
        return result
    except PortForwardClientError as e:
        _handle_client_error(e)


@router.get("/portforward", response_model=List[PortForwardingResponse], tags=["Network"])
async def list_portforwardings(
    status_filter: Optional[str] = Query(None, description="상태 필터"),
    floating_ip: Optional[str] = Query(None, description="Floating IP 필터"),
    service_type: Optional[str] = Query(None, description="서비스 유형 필터"),
    vm_id: Optional[str] = Query(None, description="VM ID 필터"),
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """포트포워딩 규칙 목록 조회"""
    try:
        result = await portforward_client.list_portforwardings(
            status_filter=status_filter,
            floating_ip=floating_ip,
            service_type=service_type,
            vm_id=vm_id,
            token=None,
        )
        if is_system_admin(profile):
            return result
        owned_vm_ids = _project_server_ids(profile)
        return [rule for rule in result if rule.get("user_vm_id") in owned_vm_ids]
    except PortForwardClientError as e:
        _handle_client_error(e)


# 동적 경로는 마지막에 정의 (/{rule_id} 패턴)


@router.get("/portforward/{rule_id}", response_model=PortForwardingResponse, tags=["Network"])
async def get_portforwarding(
    rule_id: str,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """특정 포트포워딩 규칙 조회"""
    try:
        result = await portforward_client.get_portforwarding(rule_id, None)
        _assert_rule_access(profile, result)
        return result
    except PortForwardClientError as e:
        _handle_client_error(e)


@router.patch("/portforward/{rule_id}", response_model=PortForwardingResponse, tags=["Network"])
async def update_portforwarding(
    rule_id: str,
    request: PortForwardingUpdate,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """포트포워딩 규칙 업데이트"""
    try:
        existing_rule = await portforward_client.get_portforwarding(rule_id, None)
        _assert_rule_access(profile, existing_rule)
        result = await portforward_client.update_portforwarding(rule_id, request, None)
        return result
    except PortForwardClientError as e:
        _handle_client_error(e)


@router.delete("/portforward/{rule_id}", status_code=204, tags=["Network"])
async def delete_portforwarding(
    rule_id: str,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """포트포워딩 규칙 삭제"""
    try:
        existing_rule = await portforward_client.get_portforwarding(rule_id, None)
        _assert_rule_access(profile, existing_rule)
        await portforward_client.delete_portforwarding(rule_id, None)
    except PortForwardClientError as e:
        _handle_client_error(e)
