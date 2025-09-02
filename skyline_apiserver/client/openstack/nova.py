# Nova(컴퓨트) API와 상호 작용하기 위한 클라이언트 함수들을 제공하는 파일입니다.
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

from typing import Any, Dict, List, Optional

from fastapi import status
from fastapi.exceptions import HTTPException
from keystoneauth1.exceptions.http import Unauthorized
from keystoneauth1.session import Session
from novaclient.exceptions import BadRequest, Forbidden

from skyline_apiserver import schemas
from skyline_apiserver.client import utils
from skyline_apiserver.config import CONF


def list_servers(
    profile: schemas.Profile,
    session: Session,
    global_request_id: str,
    search_opts: Optional[Dict[str, Any]] = None,
    marker: Optional[str] = None,
    limit: Optional[int] = None,
    sort_keys: Optional[List[str]] = None,
    sort_dirs: Optional[List[str]] = None,
) -> Any:
    try:
        nc = utils.nova_client(
            region=profile.region,
            session=session,
            global_request_id=global_request_id,
        )
        return nc.servers.list(
            search_opts=search_opts,
            marker=marker,
            limit=limit,
            sort_keys=sort_keys,
            sort_dirs=sort_dirs,
        )
    except BadRequest as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Unauthorized as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except Forbidden as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


def list_services(
    profile: schemas.Profile,
    session: Session,
    global_request_id: str,
    **kwargs: Any,
) -> Any:
    try:
        nc = utils.nova_client(
            region=profile.region,
            session=session,
            global_request_id=global_request_id,
        )
        return nc.services.list(**kwargs)
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


def create_instance_with_network(
    session: Session,
    profile: schemas.Profile,
    name: str,
    image_id: str,
    flavor_id: str,
    net_id: str,
    key_name: str,
):
    nc = utils.nova_client(session=session, region=profile.region)
    server = nc.servers.create(
        name=name,
        image=image_id,
        flavor=flavor_id,
        nics=[{"net-id": net_id}],
        key_name=key_name,
    )
    # TODO: Wait for server to be active
    return server


def get_server_internal_ip(
    session: Session, profile: schemas.Profile, server_id: str
) -> str:
    nc = utils.nova_client(session=session, region=profile.region)
    server = nc.servers.get(server_id)
    for network in server.addresses:
        for ip in server.addresses[network]:
            if ip["OS-EXT-IPS:type"] == "fixed":
                return ip["addr"]
    raise Exception(f"No internal IP found for server {server_id}")


def get_quotas(
    session: Session, profile: schemas.Profile, global_request_id: Optional[str] = None
):
    try:
        nc = utils.nova_client(
            region=profile.region,
            session=session,
            global_request_id=global_request_id,
        )
        return nc.quotas.get(profile.project.id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


def update_quotas(session: Session, project_id: str, **kwargs: Any) -> Any:
    try:
        nc = utils.nova_client(
            region=CONF.openstack.default_region,
            session=session,
        )
        return nc.quotas.update(project_id, **kwargs)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


def get_console_url(
    session: Session, profile: schemas.Profile, server_id: str, console_type: str
):
    nc = utils.nova_client(session=session, region=profile.region)
    if console_type == "novnc":
        console = nc.servers.get_vnc_console(server_id, "novnc")
    elif console_type == "spice-html5":
        console = nc.servers.get_spice_console(server_id, "spice-html5")
    elif console_type == "rdp-html5":
        console = nc.servers.get_rdp_console(server_id, "rdp-html5")
    elif console_type == "serial":
        console = nc.servers.get_serial_console(server_id, "serial")
    else:
        raise HTTPException(status_code=400, detail="Unsupported console type")
    return console["console"]
