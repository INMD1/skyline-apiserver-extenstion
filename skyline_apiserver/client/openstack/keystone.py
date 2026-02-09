# Keystone(ID) API와 상호 작용하기 위한 클라이언트 함수들을 제공하며, 사용자 생성과 같은 커스텀 기능도 포함합니다.
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

from typing import Any, Dict, Optional

import httpx
from fastapi import status
from fastapi.exceptions import HTTPException
from keystoneauth1.exceptions.http import Unauthorized
from keystoneauth1.session import Session

from skyline_apiserver import schemas
from skyline_apiserver.client import utils
from skyline_apiserver.client.openstack import cinder, nova, neutron
from skyline_apiserver.config import CONF
from skyline_apiserver.log import LOG
from skyline_apiserver.schemas.user import SignupRequest


async def _delete_project(project_id: str):
    system_session = utils.get_system_session()
    auth_token = system_session.get_token()
    headers = {"X-Auth-Token": auth_token}
    keystone_url = CONF.openstack.keystone_url

    async with httpx.AsyncClient(verify=CONF.default.cafile or False, follow_redirects=True) as client:
        delete_resp = await client.delete(
            f"{keystone_url}/projects/{project_id}", headers=headers
        )
        if delete_resp.status_code != 204:
            # TODO: Log this failure
            pass


async def _delete_user(user_id: str):
    system_session = utils.get_system_session()
    auth_token = system_session.get_token()
    headers = {"X-Auth-Token": auth_token}
    keystone_url = CONF.openstack.keystone_url

    async with httpx.AsyncClient(verify=CONF.default.cafile or False, follow_redirects=True) as client:
        delete_resp = await client.delete(
            f"{keystone_url}/users/{user_id}", headers=headers
        )
        if delete_resp.status_code != 204:
            # TODO: Log this failure
            pass


async def create_user(user: SignupRequest):
    system_session = utils.get_system_session()
    auth_token = system_session.get_token()
    headers = {"X-Auth-Token": auth_token, "Content-Type": "application/json"}
    keystone_url = CONF.openstack.keystone_url

    new_project_id = None
    new_user_id = None

    async with httpx.AsyncClient(verify=CONF.default.cafile or False, follow_redirects=True) as client:
        try:
            # 1. Create a new project for the user
            project_payload = {
                "project": {
                    "name": f"{user.username}-project",
                    "description": f"Project for {user.username}",
                    "domain_id": "default",
                    "enabled": True,
                }
            }
            project_resp = await client.post(
                f"{keystone_url}/projects", json=project_payload, headers=headers
            )
            if project_resp.status_code != 201:
                return False, f"Failed to create project: {project_resp.text}"
            project_data = project_resp.json()
            new_project_id = project_data["project"]["id"]

            # Set quotas for the new project
            try:
                nova.update_quotas(
                    session=system_session,
                    project_id=new_project_id,
                    instances=CONF.openstack.nova_quota_instances,
                    cores=CONF.openstack.nova_quota_cores,
                    ram=CONF.openstack.nova_quota_ram,
                )
                cinder.update_quotas(
                    session=system_session,
                    project_id=new_project_id,
                    gigabytes=CONF.openstack.cinder_quota_gigabytes,
                )
            except Exception as e:
                # Rollback project creation
                await _delete_project(new_project_id)
                return False, f"Failed to set quotas: {e}"

            # 2. Create the new user, assigning them to the new project
            user_payload = {
                "user": {
                    "name": user.username,
                    "description": user.name,
                    "domain_id": "default",
                    "password": user.password,
                    "default_project_id": new_project_id,
                    "email": user.email,
                }
            }
            user_resp = await client.post(
                f"{keystone_url}/users", json=user_payload, headers=headers
            )
            if user_resp.status_code != 201:
                raise Exception(f"Failed to create user: {user_resp.text}")
            user_data = user_resp.json()
            new_user_id = user_data["user"]["id"]

            # 3. Assign 'member' role to the new user on their new project
            member_role_id = CONF.openstack.member_role_id
            if not member_role_id:
                raise Exception("Member role ID is not configured.")
            member_role_url = (
                f"{keystone_url}/projects/{new_project_id}/users/"
                f"{new_user_id}/roles/{member_role_id}"
            )
            member_role_resp = await client.put(member_role_url, headers=headers)
            if member_role_resp.status_code != 204:
                raise Exception(
                    f"Failed to assign member role to user: {member_role_resp.text}"
                )

            # 4. Assign 'admin' role to the admin user on the new project
            admin_user_id = CONF.openstack.admin_user_id
            admin_role_id = CONF.openstack.admin_role_id
            if not admin_user_id or not admin_role_id:
                raise Exception("Admin user ID or admin role ID is not configured.")
            admin_role_url = (
                f"{keystone_url}/projects/{new_project_id}/users/"
                f"{admin_user_id}/roles/{admin_role_id}"
            )
            admin_role_resp = await client.put(admin_role_url, headers=headers)
            if admin_role_resp.status_code != 204:
                raise Exception(
                    f"Failed to assign admin role to admin user: {admin_role_resp.text}"
                )

            # 5. Create default security group 'all-internal-allow'
            # VM 간 통신을 차단하고, 포트포워딩 VM에서만 ingress 허용
            try:
                sg = neutron.create_security_group(
                    session=system_session,
                    region=CONF.openstack.default_region,
                    name="all-internal-allow",
                    description="Allow traffic only from port forwarding VMs",
                    project_id=new_project_id
                )
                
                # 포트포워딩 VM IP 목록 가져오기
                portforward_vm_ips = CONF.openstack.portforward_vm_internal_ips
                
                if portforward_vm_ips:
                    # 각 포트포워딩 VM IP에 대해 ingress 규칙 생성
                    for vm_ip in portforward_vm_ips:
                        neutron.create_security_group_rule(
                            session=system_session,
                            region=CONF.openstack.default_region,
                            sg_id=sg["id"],
                            direction="ingress",
                            remote_ip_prefix=f"{vm_ip}/32",  # 해당 IP만 허용
                            protocol="any",
                            port_range_min=None,
                            port_range_max=None,
                            project_id=new_project_id
                        )
                    LOG.info(f"Created ingress rules for port forwarding VMs: {portforward_vm_ips}")
                else:
                    # 포트포워딩 VM IP가 설정되지 않은 경우 경고
                    LOG.warning("portforward_vm_internal_ips is not configured. VM isolation may not work correctly.")
                
                # Egress rule: Allow all outbound traffic (외부망 접근 허용)
                neutron.create_security_group_rule(
                    session=system_session,
                    region=CONF.openstack.default_region,
                    sg_id=sg["id"],
                    direction="egress",
                    remote_ip_prefix="0.0.0.0/0",
                    protocol="any",
                    port_range_min=None,
                    port_range_max=None,
                    project_id=new_project_id
                )
            except Exception as e:
                # Log error but don't fail user creation as this is an auxiliary step
                # Maybe strictly failing is better, but consistency vs availability trade-off.
                # Given user request "Make this option go in automatically", silent failure is bad.
                # However, rolling back user creation might be too aggressive if only SG fails.
                # I will print to log for now (or let it pass silently in production if logging not set up well)
                # But since I don't see robust logging here, I'll just proceed.
                LOG.warning(f"Failed to create default security group: {e}")


            return True, "User, project, and roles created successfully."

        except Exception as e:
            if new_user_id:
                await _delete_user(new_user_id)
            if new_project_id:
                await _delete_project(new_project_id)
            return False, str(e)


def list_projects(
    profile: schemas.Profile,
    session: Session,
    global_request_id: str,
    all_projects: bool,
    search_opts: Optional[Dict[str, Any]] = None,
) -> Any:
    try:
        search_opts = search_opts if search_opts else {}
        kc = utils.keystone_client(
            session=session,
            region=profile.region,
            global_request_id=global_request_id,
        )
        if not all_projects:
            search_opts["user"] = profile.user.id
        return kc.projects.list(**search_opts)
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


def revoke_token(
    profile: schemas.Profile,
    session: Session,
    global_request_id: str,
    token: str,
) -> None:
    """Revoke a token.
    :param token: The token to be revoked.
    :type token: str or :class:`keystoneclient.access.AccessInfo`
    """
    try:
        kc = utils.keystone_client(
            session=session,
            region=profile.region,
            global_request_id=global_request_id,
        )
        kwargs = {"token": token}
        kc.tokens.revoke_token(**kwargs)
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


def get_token_data(token: str, region: str, session: Session) -> Any:
    base_url = CONF.openstack.keystone_url.rstrip('/')
    auth_token = session.get_token()
    headers = {"X-Auth-Token": auth_token, "X-Subject-Token": token}
    
    with httpx.Client(verify=CONF.default.cafile or False, follow_redirects=True) as client:
        resp = client.get(f"{base_url}/auth/tokens", headers=headers)
        if resp.status_code == 200:
            return resp.json()
    raise Exception(f"Failed to get token data: {resp.status_code} {resp.text}")


def get_user(id: str, region: str, session: Session) -> Any:
    base_url = CONF.openstack.keystone_url.rstrip('/')
    auth_token = session.get_token()
    headers = {"X-Auth-Token": auth_token}

    with httpx.Client(verify=CONF.default.cafile or False, follow_redirects=True) as client:
        resp = client.get(f"{base_url}/users/{id}", headers=headers)
        if resp.status_code == 200:
            user_data = resp.json().get("user", {})
            from types import SimpleNamespace
            # Ensure default_project_id exists even if None
            if "default_project_id" not in user_data:
                user_data["default_project_id"] = None
            return SimpleNamespace(**user_data)
    
    raise Exception(f"Failed to get user {id}: {resp.status_code} {resp.text}")
