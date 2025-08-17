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

from typing import Any

from fastapi import status
from fastapi.exceptions import HTTPException
from keystoneauth1.exceptions.http import Unauthorized
from keystoneauth1.session import Session
from neutronclient.v2_0.client import _GeneratorWithMeta

from skyline_apiserver import schemas
from skyline_apiserver.client import utils
    
import httpx
from schemas.portforward import PortForwardRequest
from config import setting

## 개인적으로 추가
def create_port_forwarding(conn, fip_id, internal_ip, internal_port, external_port=None, protocol='tcp'):
    try:
        if not external_port:
            external_port = get_next_available_port(conn, fip_id)
        return conn.network.create_port_forwarding(
            floatingip_id=fip_id,
            external_port=external_port,
            internal_port=internal_port,
            internal_ip_address=internal_ip,
            protocol=protocol
        )
    except Exception as e:
        raise Exception(f"포트포워딩 생성 실패: {e}")

def delete_port_forwarding(conn, fip_id, pf_id):
    try:
        return conn.network.delete_port_forwarding(floatingip_id=fip_id, port_forwarding_id=pf_id)
    except Exception as e:
        raise Exception(f"포트포워딩 삭제 실패: {e}")

def create_security_group_rule(conn, sg_id, direction, remote_group_id):
    try:
        return conn.network.create_security_group_rule(
            security_group_id=sg_id,
            direction=direction,
            remote_group_id=remote_group_id,
            ethertype='IPv4'
        )
    except Exception as e:
        raise Exception(f"보안 그룹 룰 생성 실패: {e}")
    

def list_networks(
    profile: schemas.Profile,
    session: Session,
    global_request_id: str,
    **kwargs: Any,
) -> Any:
    try:
        nc = utils.neutron_client(
            session=session,
            region=profile.region,
            global_request_id=global_request_id,
        )
        return nc.list_networks(**kwargs)
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

def find_fip_for_ssh(conn, tag="ssh-public"):
    """
    특정 태그나 설명이 붙은 Floating IP를 찾아 반환
    """
    for fip in conn.network.floating_ips():
        if (getattr(fip, "description", "") == tag) or (hasattr(fip, "tags") and tag in fip.tags):
            return fip
    raise Exception("SSH 전용 Floating IP를 찾을 수 없습니다.")
