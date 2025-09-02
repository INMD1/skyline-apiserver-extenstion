# FastAPI 의존성 주입(Dependency Injection)을 정의하는 파일입니다. 요청(request)으로부터 사용자 프로필과 JWT 페이로드를 가져오는 함수들을 포함합니다.
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

from typing import Optional

from fastapi import Header, status
from fastapi.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from skyline_apiserver import schemas
from skyline_apiserver.core.security import generate_profile


def getJWTPayload(request: Request) -> Optional[str]:
    """Get JWT payload from request state (set by middleware)."""
    if hasattr(request.state, "profile"):
        return request.state.profile.toJWTPayload()
    return None


def get_profile(request: Request) -> schemas.Profile:
    """Get profile from request state (set by middleware)."""
    if not hasattr(request.state, "profile"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Profile not found in request state",
        )
    return request.state.profile


def get_profile_update_jwt(request: Request, response: Response) -> schemas.Profile:
    """Get profile from request state and handle token renewal."""
    profile = get_profile(request)

    # Token renewal is handled in the middleware
    # This function is kept for backward compatibility
    return profile


def get_profile_from_header(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> schemas.Profile:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )

    token = authorization
    if token.lower().startswith("bearer "):
        token = token[7:]

    try:
        profile = generate_profile(
            keystone_token=token,
            region="RegionOne",
        )
        return profile
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )