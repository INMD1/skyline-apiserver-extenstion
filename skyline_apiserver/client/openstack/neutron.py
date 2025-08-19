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

from typing import Any, Dict

from fastapi import status
from fastapi.exceptions import HTTPException
from keystoneauth1.exceptions.http import Unauthorized
from keystoneauth1.session import Session
from neutronclient.v2_0.client import _GeneratorWithMeta

from skyline_apiserver import schemas
from skyline_apiserver.client import utils
    
import httpx
from skyline_apiserver.schemas.portforward import PortForwardRequest
from skyline_apiserver.config import setting


# This function is used by the /portforward endpoint and should be kept.
async def create_port_forwarding(req: PortForwardRequest, profile: schemas.Profile):
    try:
        session = utils.generate_session(profile)
        region = profile.region
        nc = utils.neutron_client(session=session, region=region)

        body = {
            "port_forwarding": {
                "protocol": req.protocol,
                "internal_ip_address": req.internal_ip,
                "internal_port": req.internal_port,
                "external_port": req.external_port,
            }
        }
        pf = nc.create_port_forwarding(floatingip_id=req.floating_ip_id, body=body)

        fip = nc.show_floatingip(req.floating_ip_id)

        result = {
            "success": True,
            "port_forwarding": {
                "floating_ip_address": fip["floatingip"]["floating_ip_address"],
                "internal_ip_address": pf["port_forwarding"]["internal_ip_address"],
                "internal_port": pf["port_forwarding"]["internal_port"],
                "external_port": pf["port_forwarding"]["external_port"],
                "protocol": pf["port_forwarding"]["protocol"],
                "status": "ACTIVE",
                "assigned_port": pf["port_forwarding"]["external_port"],
                "public_ip": fip["floatingip"]["floating_ip_address"],
            },
        }
        return result

    except Exception as e:
        return {"success": False, "error": str(e)}


def get_floating_ip(session: Session, region: str, floating_ip_id: str) -> Dict[str, Any]:
    nc = utils.neutron_client(session=session, region=region)
    return nc.show_floatingip(floating_ip_id)


def find_floating_ip_for_ssh(session: Session, region: str) -> Dict[str, Any]:
    ssh_fip_id = CONF.openstack.ssh_floating_ip_id
    if not ssh_fip_id:
        raise Exception("SSH Floating IP ID is not configured in skyline.yaml.")
    nc = utils.neutron_client(session=session, region=region)
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


def create_port_forwarding_rule(
    session: Session,
    region: str,
    floatingip_id: str,
    internal_ip_address: str,
    internal_port: int,
    external_port: int,
    protocol: str = "tcp",
) -> Dict[str, Any]:
    nc = utils.neutron_client(session=session, region=region)
    body = {
        "port_forwarding": {
            "protocol": protocol,
            "internal_ip_address": internal_ip_address,
            "internal_port": internal_port,
            "external_port": external_port,
        }
    }
    return nc.create_port_forwarding(floatingip_id=floatingip_id, body=body)["port_forwarding"]


def delete_port_forwarding_rule(session: Session, region: str, floatingip_id: str, pf_id: str):
    nc = utils.neutron_client(session=session, region=region)
    nc.delete_port_forwarding(floatingip_id=floatingip_id, port_forwarding_id=pf_id)


def get_port_forwarding_rules(session: Session, region: str, floatingip_id: str) -> list:
    nc = utils.neutron_client(session=session, region=region)
    return nc.list_port_forwardings(floatingip_id=floatingip_id).get("port_forwardings", [])


def create_security_group_rule(
    session: Session,
    region: str,
    sg_id: str,
    direction: str,
    remote_group_id: str,
    protocol: str = "tcp",
    port_range_min: int = 1,
    port_range_max: int = 65535,
):
    nc = utils.neutron_client(session=session, region=region)
    body = {
        "security_group_rule": {
            "security_group_id": sg_id,
            "direction": direction,
            "remote_group_id": remote_group_id,
            "protocol": protocol,
            "port_range_min": port_range_min,
            "port_range_max": port_range_max,
        }
    }
    return nc.create_security_group_rule(body)


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