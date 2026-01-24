# Neutron(네트워킹) API와 상호 작용하기 위한 클라이언트 함수들을 제공하는 파일입니다.
# V 원본 라이센스 (original license)
# Copyright 2021 99cloud
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

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from fastapi import status
from fastapi.exceptions import HTTPException
from keystoneauth1.exceptions.http import Unauthorized
from keystoneauth1.session import Session
from neutronclient.v2_0.client import _GeneratorWithMeta

from skyline_apiserver import schemas
from skyline_apiserver.client import utils
from skyline_apiserver.config import CONF

import httpx
import random
from skyline_apiserver.schemas.portforward import PortForwardRequest
from skyline_apiserver.config import CONF, setting


# This function is used by the /portforward endpoint and should be kept.
def create_port_forwarding(req: PortForwardRequest, profile: schemas.Profile):
    try:
        session = utils.generate_session(profile)
        region = profile.region
        nc = utils.neutron_client(session=session, region=region)

        # Check for conflicts
        existing_pfs = nc.list_port_forwardings(floatingip_id=req.floating_ip_id).get(
            "port_forwardings", []
        )
        for pf in existing_pfs:
            if pf["external_port"] == req.external_port:
                return {
                    "success": False,
                    "error": f"External port {req.external_port} is already in use on this floating IP.",
                }

        body = {
            "port_forwarding": {
                "protocol": req.protocol,
                "internal_ip_address": req.internal_ip,
                "internal_port": req.internal_port,
                "external_port": req.external_port,
            }
        }
        pf = nc.create_port_forwarding(floatingip_id=req.floating_ip_id, body=body)[
            "port_forwarding"
        ]

        fip = nc.show_floatingip(req.floating_ip_id)

        result = {
            "success": True,
            "port_forwarding": {
                "floating_ip_address": fip["floatingip"]["floating_ip_address"],
                "internal_ip_address": pf["internal_ip_address"],
                "internal_port": pf["internal_port"],
                "external_port": pf["external_port"],
                "protocol": pf["protocol"],
                "status": "ACTIVE",
                "assigned_port": pf["external_port"],
                "public_ip": fip["floatingip"]["floating_ip_address"],
            },
        }
        return result

    except Exception as e:
        return {"success": False, "error": str(e)}


def get_floating_ip(
    session: Session, region: str, floating_ip_id: str
) -> Dict[str, Any]:
    nc = utils.neutron_client(session=session, region=region)
    return nc.show_floatingip(floating_ip_id)


def find_floating_ip_for_ssh(session: Session, region: str) -> Dict[str, Any]:
    ssh_fip_id = CONF.openstack.ssh_floating_ip_id
    if not ssh_fip_id:
        raise Exception("SSH Floating IP ID is not configured in skyline.yaml.")
    
    # 시스템 세션 사용 (다른 프로젝트의 floating IP도 조회 가능)
    from skyline_apiserver.client.utils import get_system_session
    system_session = get_system_session()
    nc = utils.neutron_client(session=system_session, region=region)
    return nc.show_floatingip(ssh_fip_id)["floatingip"]


def find_available_floating_ip(session: Session, region: str) -> Dict[str, Any]:
    project_id = CONF.openstack.shared_floating_ip_project_id
    if not project_id:
        raise Exception("Shared floating IP project ID is not configured.")

    nc = utils.neutron_client(session=session, region=region)
    fips = nc.list_floatingips(tenant_id=project_id, port_id="")
    if not fips.get("floatingips"):
        raise Exception("No available floating IPs found in the shared project.")
    return fips["floatingips"][0]


def find_portforward_floating_ip(session: Session, region: str) -> Dict[str, Any]:
    """
    portforward_floating_ip_ids 배열에서 랜덤하게 Floating IP를 선택합니다.
    배열이 비어있으면 기존 방식(shared project)을 사용합니다.
    
    설정값은 UUID 또는 IP 주소 둘 다 가능합니다:
    - UUID: '43ffccff-79a6-4729-84c9-ee295a0d1f77'
    - IP 주소: 'XXX.XXX.XXX.XXX'
    """
    fip_ids_or_ips = CONF.openstack.portforward_floating_ip_ids
    if not fip_ids_or_ips:
        # 배열이 비어있으면 기존 방식 사용
        return find_available_floating_ip(session, region)

    # 랜덤하게 선택
    selected_value = random.choice(fip_ids_or_ips)
    
    # 시스템 세션 사용 (다른 프로젝트의 floating IP도 조회 가능)
    from skyline_apiserver.client.utils import get_system_session
    system_session = get_system_session()
    nc = utils.neutron_client(session=system_session, region=region)
    
    try:
        # UUID 형식인지 확인 (8-4-4-4-12 형식)
        if len(selected_value) == 36 and selected_value.count('-') == 4:
            # UUID로 직접 조회
            return nc.show_floatingip(selected_value)["floatingip"]
        else:
            # IP 주소로 조회 - 모든 floating IP를 가져와서 수동 검색
            # all_projects=True 파라미터로 모든 프로젝트의 floating IP 조회
            all_fips = nc.list_floatingips().get("floatingips", [])
            for fip in all_fips:
                if fip.get("floating_ip_address") == selected_value:
                    return fip
            
            # 찾지 못한 경우
            raise Exception(f"No floating IP found with address: {selected_value}")
    except Exception as e:
        raise Exception(f"Failed to get floating IP '{selected_value}': {str(e)}")





def find_port_by_internal_ip(
    session: Session, region: str, internal_ip: str
) -> Optional[str]:
    """
    Internal IP 주소로 Neutron Port UUID를 찾습니다.
    포트포워딩 생성 시 필수적으로 필요합니다.
    """
    nc = utils.neutron_client(session=session, region=region)
    try:
        # fixed_ips 필터로 해당 IP를 가진 포트 검색
        ports = nc.list_ports(fixed_ips=f"ip_address={internal_ip}").get("ports", [])
        if not ports:
            raise Exception(f"No port found with internal IP: {internal_ip}")
        
        # 첫 번째 포트 반환 (보통 하나만 있음)
        return ports[0]["id"]
    except Exception as e:
        raise Exception(f"Failed to find port for IP {internal_ip}: {str(e)}")


def create_port_forwarding_rule(
    session: Session,
    region: str,
    floatingip_id: str,
    internal_ip_address: str,
    internal_port: int,
    external_port: int = None,
    protocol: str = "tcp",
) -> Dict[str, Any]:
    nc = utils.neutron_client(session=session, region=region)
    
    # Auto-assign port if not specified
    if external_port is None:
        external_port = find_random_available_port(session, region, floatingip_id)
    
    # Internal IP로부터 Port UUID 찾기 (필수)
    internal_port_id = find_port_by_internal_ip(session, region, internal_ip_address)
    
    body = {
        "port_forwarding": {
            "protocol": protocol,
            "internal_ip_address": internal_ip_address,
            "internal_port_id": internal_port_id,  # Port UUID (필수)
            "internal_port": internal_port,
            "external_port": external_port,
        }
    }
    
    # POST /v2.0/floatingips/{floatingip_id}/port_forwardings
    return nc.create_port_forwarding(floatingip=floatingip_id, body=body)["port_forwarding"]


def delete_port_forwarding_rule(
    session: Session, region: str, floatingip_id: str, pf_id: str
):
    # 시스템 세션 사용 (다른 프로젝트의 floating IP 접근을 위해)
    from skyline_apiserver.client.utils import get_system_session
    system_session = get_system_session()
    nc = utils.neutron_client(session=system_session, region=region)
    # DELETE /v2.0/floatingips/{floatingip_id}/port_forwardings/{port_forwarding_id}
    nc.delete_port_forwarding(floatingip_id, pf_id)


def get_port_forwarding_rules(
    session: Session, region: str, floatingip_id: str
) -> list:
    nc = utils.neutron_client(session=session, region=region)
    return nc.list_port_forwardings(floatingip=floatingip_id).get(
        "port_forwardings", []
    )


def get_port_forwardings_by_internal_ip(
    session: Session, region: str, internal_ip: str
) -> List[Dict[str, Any]]:
    """
    특정 Internal IP (VM)에 연결된 모든 포트포워딩 규칙을 조회합니다.
    시스템 세션을 사용하여 다른 프로젝트의 floating IP도 조회합니다.
    """
    # 시스템 세션 사용 (공유 floating IP 조회를 위해)
    from skyline_apiserver.client.utils import get_system_session
    system_session = get_system_session()
    nc = utils.neutron_client(session=system_session, region=region)
    
    # 모든 floating IP 조회
    all_fips = nc.list_floatingips().get("floatingips", [])

    result = []
    for fip in all_fips:
        try:
            # 각 floating IP의 port forwarding 규칙 조회
            pfs = nc.list_port_forwardings(floatingip=fip["id"]).get("port_forwardings", [])
            for pf in pfs:
                if pf.get("internal_ip_address") == internal_ip:
                    result.append({
                        "id": pf["id"],
                        "floating_ip_id": fip["id"],
                        "floating_ip_address": fip["floating_ip_address"],
                        "internal_ip_address": pf["internal_ip_address"],
                        "internal_port": pf["internal_port"],
                        "external_port": pf["external_port"],
                        "protocol": pf["protocol"],
                    })
        except Exception:
            # floating IP에 접근 권한이 없거나 오류 발생 시 스킵
            continue
    
    return result


def find_random_available_port(session: Session, region: str, floatingip_id: str, 
                                 min_port: int = 10, max_port: int = 1000) -> int:
    """Find a random available port on a floating IP."""
    nc = utils.neutron_client(session=session, region=region)
    existing_pfs = nc.list_port_forwardings(floatingip=floatingip_id).get("port_forwardings", [])
    used_ports = {pf["external_port"] for pf in existing_pfs}
    
    # Try to find an available port (max 100 attempts)
    for _ in range(100):
        port = random.randint(min_port, max_port)
        if port not in used_ports:
            return port
    
    raise Exception(f"Could not find available port on floating IP {floatingip_id}")


def find_best_floating_ip_for_vm(session: Session, region: str, internal_ip: str) -> Dict[str, Any]:
    """
    Find the best floating IP for a VM using sticky allocation logic.
    If the VM already has port forwarding rules, prefer the same IP.
    Otherwise, choose from the configured port_forwarding_ip_ids pool.
    """
    nc = utils.neutron_client(session=session, region=region)
    
    # Check if VM already has port forwarding rules
    existing_pfs = get_vm_port_forwardings(session, region, internal_ip)
    
    if existing_pfs:
        # Use the same floating IP as the first existing rule
        first_fip_id = existing_pfs[0]["floating_ip_id"]
        try:
            fip = nc.show_floatingip(first_fip_id)["floatingip"]
            # Check if there's room for more port forwardings
            pfs = nc.list_port_forwardings(floatingip_id=first_fip_id).get("port_forwardings", [])
            # Arbitrary limit: if less than 50 port forwardings, use this IP
            if len(pfs) < 50:
                return fip
        except Exception:
            pass  # Fall through to select a new IP
    
    # No existing rules or existing IP is full, select from pool
    port_forwarding_ip_ids = CONF.openstack.port_forwarding_ip_ids
    if not port_forwarding_ip_ids:
        raise Exception("No port forwarding IPs configured in port_forwarding_ip_ids.")
    
    # Find the IP with the least port forwardings
    best_fip = None
    min_pf_count = float('inf')
    
    for fip_id in port_forwarding_ip_ids:
        try:
            fip = nc.show_floatingip(fip_id)["floatingip"]
            pfs = nc.list_port_forwardings(floatingip_id=fip_id).get("port_forwardings", [])
            pf_count = len(pfs)
            
            if pf_count < min_pf_count:
                min_pf_count = pf_count
                best_fip = fip
        except Exception as e:
            continue  # Skip invalid floating IP IDs
    
    if not best_fip:
        raise Exception("No available floating IPs found in port_forwarding_ip_ids pool.")
    
    return best_fip


def create_security_group(
    session: Session,
    region: str,
    name: str,
    description: str,
    project_id: Optional[str] = None
) -> Dict[str, Any]:
    nc = utils.neutron_client(session=session, region=region)
    body = {
        "security_group": {
            "name": name,
            "description": description,
        }
    }
    if project_id:
        body["security_group"]["project_id"] = project_id
    
    return nc.create_security_group(body)["security_group"]


def create_security_group_rule(
    session: Session,
    region: str,
    sg_id: str,
    direction: str,
    remote_group_id: Optional[str] = None,
    remote_ip_prefix: Optional[str] = None,
    protocol: Optional[str] = "tcp",
    port_range_min: Optional[int] = 1,
    port_range_max: Optional[int] = 65535,
    ethertype: str = "IPv4",
    project_id: Optional[str] = None,
):
    nc = utils.neutron_client(session=session, region=region)
    
    rule_def = {
        "security_group_id": sg_id,
        "direction": direction,
        "ethertype": ethertype,
    }
    
    if remote_group_id:
        rule_def["remote_group_id"] = remote_group_id
    if remote_ip_prefix:
        rule_def["remote_ip_prefix"] = remote_ip_prefix
    
    if protocol == "any":
        rule_def["protocol"] = None
    elif protocol:
        rule_def["protocol"] = protocol
        
    if port_range_min is not None:
        rule_def["port_range_min"] = port_range_min
    if port_range_max is not None:
        rule_def["port_range_max"] = port_range_max
        
    if project_id:
        rule_def["project_id"] = project_id

    body = {"security_group_rule": rule_def}
    return nc.create_security_group_rule(body)["security_group_rule"]


def list_networks(
    session: Session,
    profile: schemas.Profile,
    global_request_id: Optional[str] = None,
    **kwargs,
):
    try:
        nc = utils.neutron_client(
            session=session,
            region=profile.region,
            global_request_id=global_request_id,
        )
        return nc.list_networks(**kwargs)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


def list_ports(
    session: Session,
    region_name: str,
    global_request_id: str,
    retrieve_all: bool = False,
    **kwargs: Any,
) -> _GeneratorWithMeta:
    try:
        nc = utils.neutron_client(
            session=session,
            region=region_name,
            global_request_id=global_request_id,
        )
        return nc.list_ports(retrieve_all=retrieve_all, **kwargs)
    except Unauthorized as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


def get_quotas(
    session: Session, profile: schemas.Profile, global_request_id: Optional[str] = None
):
    try:
        nc = utils.neutron_client(
            session=session,
            region=profile.region,
            global_request_id=global_request_id,
        )
        return nc.show_quota(profile.project.id)["quota"]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


def list_routers(
    session: Session,
    profile: schemas.Profile,
    global_request_id: Optional[str] = None,
    **kwargs,
):
    try:
        nc = utils.neutron_client(
            session=session,
            region=profile.region,
            global_request_id=global_request_id,
        )
        return nc.list_routers(**kwargs)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


def list_subnets(
    session: Session,
    profile: schemas.Profile,
    global_request_id: Optional[str] = None,
    **kwargs,
):
    try:
        nc = utils.neutron_client(
            session=session,
            region=profile.region,
            global_request_id=global_request_id,
        )
        return nc.list_subnets(**kwargs)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


def list_security_groups(
    session: Session,
    profile: schemas.Profile,
    global_request_id: Optional[str] = None,
    **kwargs,
):
    try:
        nc = utils.neutron_client(
            session=session,
            region=profile.region,
            global_request_id=global_request_id,
        )
        return nc.list_security_groups(**kwargs)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


def list_floatingips(
    session: Session,
    profile: schemas.Profile,
    global_request_id: Optional[str] = None,
    **kwargs,
):
    try:
        nc = utils.neutron_client(
            session=session,
            region=profile.region,
            global_request_id=global_request_id,
        )
        return nc.list_floatingips(**kwargs)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
