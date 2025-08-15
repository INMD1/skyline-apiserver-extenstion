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
async def create_port_forwarding(req: PortForwardRequest):
    headers = {
        "X-Auth-Token": setting.ADMIN_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "port_forwarding": {
            "internal_ip_address": req.internal_ip,
            "internal_port": req.internal_port,
            "external_port": req.external_port,
            "protocol": req.protocol
        }
    }

    async with httpx.AsyncClient() as client:
        url = f"{setting.NEUTRON_URL}/v2.0/floatingips/{req.floating_ip_id}/port_forwardings"
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code == 201:
        return {"success": True}
    else:
        return {"success": False, "error": response.text}
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
