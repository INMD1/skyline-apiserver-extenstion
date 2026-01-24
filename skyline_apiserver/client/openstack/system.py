# 엔드포인트 및 프로젝트 정보 조회 등 시스템 수준의 OpenStack 클라이언트 기능을 제공하는 파일입니다.
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

from pathlib import PurePath
from typing import Any, Dict, List

import httpx

from keystoneauth1.identity.v3 import Token
from keystoneauth1.session import Session

from skyline_apiserver.client import utils
from skyline_apiserver.client.utils import get_system_session
from skyline_apiserver.config import CONF
from skyline_apiserver.log import LOG
from skyline_apiserver.types import constants


def get_project_scope_token(
    keystone_token: str,
    region: str,
    project_id: str,
) -> str:
    auth_url = CONF.openstack.keystone_url
    kwargs = {"project_id": project_id}
    scope_auth = Token(auth_url=auth_url, token=keystone_token, **kwargs)  # type: ignore

    session = Session(
        auth=scope_auth, verify=CONF.default.cafile, timeout=constants.DEFAULT_TIMEOUT
    )
    keystone_token = session.get_token()  # type: ignore

    return keystone_token


def get_endpoints(region: str) -> Dict[str, Any]:
    access = utils.get_access(session=get_system_session())
    catalogs = access.service_catalog.get_endpoints(
        region_name=region,
        interface=CONF.openstack.interface_type,
    )
    endpoints = {}
    for service_type, endpoint in catalogs.items():
        if not endpoint:
            continue
        # TODO(wu.wenxiang): Need refactor
        # - different region may have different service_type for a service
        # - suppose "cinder -> ['volumev3', 'block-storage']" maybe better
        # - import os_service_types.service_types.BUILTIN_DATA
        # - hardcode exclude cinderv2 / volumev2
        # - also check generate_nginux::get_proxy_endpoints()
        service = CONF.openstack.service_mapping.get(service_type)
        if not service:
            continue

        path = PurePath("/").joinpath(CONF.openstack.nginx_prefix, region.lower(), service)
        endpoints[service] = str(path)
    nc = utils.neutron_client(session=get_system_session(), region=region)
    neutron_extentions = nc.list_extensions()
    ext_list = (
        neutron_extentions["extensions"]
        if isinstance(neutron_extentions, dict) and "extensions" in neutron_extentions
        else []
    )
    extentions_set = {i["alias"] for i in ext_list}
    for alias, mapping_name in CONF.openstack.extension_mapping.items():
        if alias in extentions_set:
            endpoints[mapping_name] = endpoints["neutron"]
        else:
            LOG.info(f"The {alias} resource could not be found.")
    return endpoints


def get_projects(global_request_id: str, region: str, user: str) -> List[Any]:
    base_url = CONF.openstack.keystone_url.rstrip('/')
    system_session = get_system_session()
    auth_token = system_session.get_token()
    headers = {"X-Auth-Token": auth_token}
    
    with httpx.Client(verify=CONF.default.cafile or False, follow_redirects=True) as client:
        resp = client.get(f"{base_url}/users/{user}/projects", headers=headers)
        if resp.status_code == 200:
             projects_data = resp.json().get("projects", [])
             # Convert to objects
             from types import SimpleNamespace
             return [
                SimpleNamespace(
                    id=p["id"],
                    name=p["name"],
                    enabled=p.get("enabled", True),
                    domain_id=p.get("domain_id"),
                    description=p.get("description", ""),
                )
                for p in projects_data
             ]
    return []


def get_domains(global_request_id: str, region: str) -> Any:
    base_url = CONF.openstack.keystone_url.rstrip('/')
    system_session = get_system_session()
    auth_token = system_session.get_token()
    headers = {"X-Auth-Token": auth_token}
    
    with httpx.Client(verify=CONF.default.cafile or False, follow_redirects=True) as client:
        resp = client.get(f"{base_url}/domains?enabled=true", headers=headers)
        if resp.status_code == 200:
            domains = resp.json().get("domains", [])
            return [d["name"] for d in domains]
    return []


def get_regions() -> Any:
    access = utils.get_access(session=get_system_session())
    catalogs = access.service_catalog.get_endpoints(interface=CONF.openstack.interface_type)
    regions = list(set(j["region_id"] for i in catalogs for j in catalogs[i]))  # type: ignore
    return regions
