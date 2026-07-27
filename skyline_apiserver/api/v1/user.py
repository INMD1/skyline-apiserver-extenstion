# 사용자 회원가입을 처리하는 API 엔드포인트를 제공하는 파일입니다.
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
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException

from skyline_apiserver.api.deps import get_profile
from skyline_apiserver.client.openstack.keystone import change_password, create_user
from skyline_apiserver.config import CONF
from skyline_apiserver.schemas.user import ChangePasswordRequest, SignupRequest

router = APIRouter()


def _is_signup_authorized(internal_token: str | None) -> bool:
    if CONF.default.signup_enabled:
        return True

    configured_token = CONF.default.signup_token
    return bool(
        configured_token
        and internal_token
        and hmac.compare_digest(configured_token.encode(), internal_token.encode())
    )


@router.post("/signup", tags=["User"])
async def signup(
    user: SignupRequest,
    x_skyline_signup_token: str | None = Header(default=None),
):
    if not _is_signup_authorized(x_skyline_signup_token):
        raise HTTPException(status_code=403, detail="Public signup is disabled")
    success, msg = await create_user(user)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}


@router.post("/change-password", tags=["User"])
async def change_user_password(
    req: ChangePasswordRequest,
    profile=Depends(get_profile),
):
    success, msg = await change_password(
        user_id=profile.user.id,
        keystone_token=profile.keystone_token,
        req=req,
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}
