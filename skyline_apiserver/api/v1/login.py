# 사용자 로그인, 로그아웃, 프로필 관리, 프로젝트 전환, SSO 등 인증 및 세션 관련 API 엔드포인트를 제공하는 파일입니다.
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

import os
from pathlib import PurePath
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import status
from fastapi.exceptions import HTTPException
from fastapi.param_functions import Depends, Form, Header
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRouter
from keystoneauth1.identity.v3 import Password, Token
from keystoneauth1.session import Session
from keystoneclient.client import Client as KeystoneClient
import httpx
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response

from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.client import utils
from skyline_apiserver.client.openstack import activity as activity_client
from skyline_apiserver.client.openstack.keystone import get_token_data, get_user, revoke_token
from skyline_apiserver.client.openstack.system import (
    get_endpoints,
    get_project_scope_token,
    get_projects,
)
from skyline_apiserver.client.utils import generate_session, get_system_session
from skyline_apiserver.config import CONF
from skyline_apiserver.core.security import (
    generate_profile,
    generate_profile_by_token,
    parse_access_token,
)
from skyline_apiserver.db import api as db_api
from skyline_apiserver.log import LOG
from skyline_apiserver.types import constants

router = APIRouter()


class LogoutBody(BaseModel):
    keystone_token: Optional[str] = None
    region: Optional[str] = None


def _get_default_project_id(
    session: Session, region: str, user_id: Optional[str] = None
) -> Union[str, None]:
    system_session = get_system_session()
    system_token = system_session.get_token()
    
    # Base URL for direct API calls - remove trailing slash if present
    base_url = CONF.openstack.keystone_url.rstrip('/')
    
    headers = {"X-Auth-Token": system_token}
    
    if not user_id:
        # Get user_id from the session token
        token = session.get_token()
        # Use direct HTTP API to get token data
        with httpx.Client(verify=CONF.default.cafile or False, follow_redirects=True) as client:
            resp = client.get(f"{base_url}/auth/tokens", headers={"X-Auth-Token": system_token, "X-Subject-Token": token})
            if resp.status_code == 200:
                token_data = resp.json()
                _user_id = token_data["token"]["user"]["id"]
            else:
                return None
    else:
        _user_id = user_id
    
    # Get user details directly via API
    with httpx.Client(verify=CONF.default.cafile or False, follow_redirects=True) as client:
        resp = client.get(f"{base_url}/users/{_user_id}", headers=headers)
        if resp.status_code == 200:
            user_data = resp.json()
            return user_data.get("user", {}).get("default_project_id")
    
    return None


def _get_projects_and_unscope_token(
    region: str,
    domain: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    token: Optional[str] = None,
    project_enabled: bool = False,
) -> Tuple[List[Any], str, Union[str, None]]:
    auth_url = CONF.openstack.keystone_url

    if token:
        unscope_auth = Token(
            auth_url=auth_url,
            token=token,
            reauthenticate=False,
        )
    else:
        unscope_auth = Password(  # type: ignore
            auth_url=auth_url,
            user_domain_name=domain,
            username=username,
            password=password,  # type: ignore
            reauthenticate=False,
        )

    session = Session(
        auth=unscope_auth, verify=CONF.default.cafile, timeout=constants.DEFAULT_TIMEOUT
    )

    # Get unscoped token
    unscope_token = token if token else session.get_token()

    # Get projects list directly via API to avoid service catalog issues
    # Remove trailing slash from auth_url if present to avoid double slashes
    # auth_url is CONF.openstack.keystone_url which ends with /v3/
    base_url = auth_url.rstrip('/')
    headers = {"X-Auth-Token": unscope_token}
    
    with httpx.Client(verify=CONF.default.cafile or False, follow_redirects=True) as client:
        # We need to call /auth/projects (which is relative to /v3)
        # base_url ends with /v3, so base_url + '/auth/projects' is correct
        resp = client.get(f"{base_url}/auth/projects", headers=headers)
        if resp.status_code != 200:
             # If /auth/projects fails, try /projects just in case (though /auth/projects is standard for Keystone v3)
             resp = client.get(f"{base_url}/projects", headers=headers)
             if resp.status_code != 200:
                raise Exception(f"Failed to get projects: {resp.status_code} {resp.text}")
        projects_data = resp.json().get("projects", [])

    # Convert to objects similar to what KeystoneClient returns
    from types import SimpleNamespace
    project_scope = [
        SimpleNamespace(
            id=p["id"],
            name=p["name"],
            enabled=p.get("enabled", True),
            domain_id=p.get("domain_id"),
            description=p.get("description", ""),
        )
        for p in projects_data
    ]
    unscope_token = token if token else session.get_token()

    if project_enabled:
        project_scope = [scope for scope in project_scope if scope.enabled]

    if not project_scope:
        raise Exception("You are not authorized for any projects or domains.")

    default_project_id = _get_default_project_id(session, region)

    return project_scope, unscope_token, default_project_id  # type: ignore


def _patch_profile(profile: schemas.Profile, global_request_id: str) -> schemas.Profile:
    try:
        profile.endpoints = get_endpoints(region=profile.region)

        projects = get_projects(
            global_request_id=global_request_id,
            region=profile.region,
            user=profile.user.id,
        )

        if not projects:
            projects, _, default_project_id = _get_projects_and_unscope_token(
                region=profile.region, token=profile.keystone_token
            )
        else:
            default_project_id = _get_default_project_id(
                get_system_session(), profile.region, user_id=profile.user.id
            )

        profile.projects = {
            i.id: {
                "name": i.name,
                "enabled": i.enabled,
                "domain_id": i.domain_id,
                "description": i.description,
            }
            for i in projects
        }

        profile.default_project_id = default_project_id

    except Exception as e:
        LOG.debug(f"Profile patch failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        )
    return profile


@router.post(
    "/login",
    description="Login & get user profile.",
    responses={
        200: {"model": schemas.Profile},
        401: {"model": schemas.UnauthorizedMessage},
    },
    response_model=schemas.Profile,
    status_code=status.HTTP_200_OK,
    response_description="OK",
)
def login(
    request: Request,
    response: Response,
    credential: schemas.Credential,
    x_openstack_request_id: Optional[str] = Header(
        None,
        alias=constants.INBOUND_HEADER,
        regex=constants.INBOUND_HEADER_REGEX,
    ),
) -> schemas.Profile:
    region = credential.region or CONF.openstack.default_region
    try:
        project_scope, unscope_token, default_project_id = _get_projects_and_unscope_token(
            region=region,
            domain=credential.domain,
            username=credential.username,
            password=credential.password,
            project_enabled=True,
        )

        if default_project_id not in [i.id for i in project_scope]:
            default_project_id = None
        project_scope_token = get_project_scope_token(
            keystone_token=unscope_token,
            region=region,
            project_id=default_project_id or project_scope[0].id,
        )

        profile = generate_profile(
            keystone_token=project_scope_token,
            region=region,
        )

        profile = _patch_profile(profile, x_openstack_request_id)
    except Exception as e:
        LOG.debug(f"Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or unauthorized",
        )
    else:
        session = generate_session(profile)
        activity_client.create_activity(
            session=session,
            category="login",
            message=f"User {profile.user.name} logged in successfully.",
            status_result="success",
        )
        response.set_cookie(
            CONF.default.session_name,
            profile.toJWTPayload(),
            httponly=True,
            secure=CONF.default.ssl_enabled,
            samesite="strict",
        )
        response.set_cookie(
            constants.TIME_EXPIRED_KEY,
            str(profile.exp),
            httponly=False,
            secure=CONF.default.ssl_enabled,
            samesite="strict",
        )
        return profile


@router.get(
    "/sso",
    description="SSO configuration.",
    responses={
        200: {"model": schemas.SSO},
    },
    response_model=schemas.SSO,
    status_code=status.HTTP_200_OK,
    response_description="OK",
)
def get_sso(request: Request) -> schemas.SSO:
    sso: Dict = {
        "enable_sso": False,
        "protocols": [],
    }
    if CONF.openstack.sso_enabled:
        protocols: List = []

        ks_url = CONF.openstack.keystone_url.rstrip("/")
        url_scheme = "https" if CONF.default.ssl_enabled else "http"
        port = f":{request.url.port}" if request.url.port else ""
        base_url = f"{url_scheme}://{request.url.hostname}{port}"
        base_path = str(PurePath("/").joinpath(CONF.openstack.nginx_prefix, "skyline"))

        for protocol in CONF.openstack.sso_protocols:

            url = (
                f"{ks_url}/auth/OS-FEDERATION/websso/{protocol}"
                f"?origin={base_url}{base_path}{constants.API_PREFIX}/websso"
            )

            protocols.append(
                {
                    "protocol": protocol,
                    "url": url,
                }
            )

        sso = {
            "enable_sso": CONF.openstack.sso_enabled,
            "protocols": protocols,
        }

    return schemas.SSO(**sso)


@router.post(
    "/websso",
    description="Websso",
    responses={
        302: {"description": "Redirect to SSO provider"},
        401: {"model": schemas.common.UnauthorizedMessage},
    },
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    response_description="Redirect",
)
def websso(
    token: str = Form(...),
    x_openstack_request_id: Optional[str] = Header(
        None,
        alias=constants.INBOUND_HEADER,
        regex=constants.INBOUND_HEADER_REGEX,
    ),
) -> RedirectResponse:
    try:
        project_scope, _, default_project_id = _get_projects_and_unscope_token(
            region=CONF.openstack.sso_region,
            token=token,
            project_enabled=True,
        )

        if default_project_id not in [i.id for i in project_scope]:
            default_project_id = None
        project_scope_token = get_project_scope_token(
            keystone_token=token,
            region=CONF.openstack.sso_region,
            project_id=default_project_id or project_scope[0].id,
        )

        profile = generate_profile(
            keystone_token=project_scope_token,
            region=CONF.openstack.sso_region,
        )

        profile = _patch_profile(profile, x_openstack_request_id)
    except Exception as e:
        LOG.debug(f"SSO login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="SSO authentication failed",
        )
    else:
        nextjs_url = os.environ.get("NEXTJS_URL", "http://localhost:3000")
        redirect_url = f"{nextjs_url}/auth/sso-callback"
        response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            CONF.default.session_name,
            profile.toJWTPayload(),
            httponly=True,
            secure=CONF.default.ssl_enabled,
            samesite="lax",
        )
        response.set_cookie(
            constants.TIME_EXPIRED_KEY,
            str(profile.exp),
            httponly=False,
            secure=CONF.default.ssl_enabled,
            samesite="lax",
        )
        return response


@router.get(
    "/profile",
    description="Get user profile.",
    
    responses={
        200: {"model": schemas.Profile},
        401: {"model": schemas.UnauthorizedMessage},
    },
    response_model=schemas.Profile,
    status_code=status.HTTP_200_OK,
    response_description="OK",
)
def get_profile(
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
    x_openstack_request_id: Optional[str] = Header(
        None,
        alias=constants.INBOUND_HEADER,
        regex=constants.INBOUND_HEADER_REGEX,
    ),
) -> schemas.Profile:
    return _patch_profile(profile, x_openstack_request_id)


@router.post(
    "/logout",
    description="Log out.",
    responses={
        200: {"model": schemas.Message},
    },
    response_model=schemas.Message,
    status_code=status.HTTP_200_OK,
    response_description="OK",
)
def logout(
    response: Response,
    body: Optional[LogoutBody] = None,
    payload: str = Depends(deps.getJWTPayload),
    x_openstack_request_id: Optional[str] = Header(
        None,
        alias=constants.INBOUND_HEADER,
        regex=constants.INBOUND_HEADER_REGEX,
    ),
) -> schemas.Message:
    if payload:
        try:
            token = parse_access_token(payload)
            profile = generate_profile_by_token(token)
            session = generate_session(profile)
            revoke_token(profile, session, x_openstack_request_id, token.keystone_token)
            db_api.revoke_token(profile.uuid, profile.exp)
            activity_client.create_activity(
                session=session,
                category="logout",
                message=f"User {profile.user.name} logged out successfully.",
                status_result="success",
            )
        except Exception as e:
            LOG.debug(str(e))
    elif body and body.keystone_token:
        try:
            _region = body.region or CONF.openstack.default_region
            auth_url = utils.get_endpoint(
                region=_region,
                service="identity",
                session=get_system_session(),
            )
            auth = Token(auth_url=auth_url, token=body.keystone_token, reauthenticate=False)
            session = Session(auth=auth, verify=CONF.default.cafile, timeout=constants.DEFAULT_TIMEOUT)
            session.invalidate()
        except Exception as e:
            LOG.debug(str(e))
    response.delete_cookie(CONF.default.session_name)
    return schemas.Message(message="Logout OK")


@router.post(
    "/switch_project/{project_id}",
    description="Switch project.",
    responses={
        200: {"model": schemas.Profile},
        401: {"model": schemas.UnauthorizedMessage},
    },
    response_model=schemas.Profile,
    status_code=status.HTTP_200_OK,
    response_description="OK",
)
def switch_project(
    project_id: str,
    response: Response,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
    x_openstack_request_id: Optional[str] = Header(
        None,
        alias=constants.INBOUND_HEADER,
        regex=constants.INBOUND_HEADER_REGEX,
    ),
) -> schemas.Profile:
    region = profile.region
    try:
        project_scope_token = get_project_scope_token(
            keystone_token=profile.keystone_token,
            region=region,
            project_id=project_id,
        )
        new_profile = generate_profile(
            keystone_token=project_scope_token,
            region=region,
        )
        new_profile = _patch_profile(new_profile, x_openstack_request_id)
    except Exception as e:
        LOG.debug(f"Switch project failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Project switch failed",
        )
    else:
        response.set_cookie(
            CONF.default.session_name,
            new_profile.toJWTPayload(),
            httponly=True,
            secure=CONF.default.ssl_enabled,
            samesite="strict",
        )
        response.set_cookie(
            constants.TIME_EXPIRED_KEY,
            str(new_profile.exp),
            httponly=False,
            secure=CONF.default.ssl_enabled,
            samesite="strict",
        )
        return new_profile