# JWT 파싱, 토큰 기반 사용자 프로필 생성 등 보안 관련 작업을 처리하는 함수들을 제공하는 파일입니다.
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

import time
import uuid
from typing import Optional

from fastapi import status
from fastapi.exceptions import HTTPException
from jose import jwt

from skyline_apiserver import schemas, version
from skyline_apiserver.client import utils
from skyline_apiserver.client.openstack.keystone import get_user
from skyline_apiserver.client.utils import get_system_session
from skyline_apiserver.config import CONF
from skyline_apiserver.db import api as db_api


def parse_access_token(token: str) -> (schemas.Payload):
    payload = jwt.decode(token, CONF.default.secret_key, algorithms=["HS256"])
    return schemas.Payload(
        keystone_token=payload["keystone_token"],
        region=payload["region"],
        exp=payload["exp"],
        uuid=payload["uuid"],
    )


def generate_profile_by_token(token: schemas.Payload) -> schemas.Profile:
    return generate_profile(
        keystone_token=token.keystone_token,
        region=token.region,
        exp=token.exp,
        uuid_value=token.uuid,
    )


def generate_profile(
    keystone_token: str,
    region: str,
    exp: Optional[int] = None,
    uuid_value: Optional[str] = None,
) -> schemas.Profile:
    try:
        system_session = get_system_session()
        kc = utils.keystone_client(session=system_session, region=region)
        token_data = kc.tokens.get_token_data(token=keystone_token)
        user_id = token_data["token"]["user"]["id"]
        user_info = get_user(id=user_id, region=region, session=system_session)

        user_details = db_api.get_user_details(user_id=user_id)
        student_id = user_details.student_id if user_details else None

        token_data["token"]["user"] = {
            "id": user_info.id,
            "name": user_info.name,
            "domain": token_data["token"]["user"]["domain"],
            "email": getattr(user_info, "email", None),
            "student_id": student_id,
            "description": getattr(user_info, "description", None),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    else:
        return schemas.Profile(
            keystone_token=keystone_token,
            region=region,
            project=token_data["token"]["project"],
            user=token_data["token"]["user"],
            roles=token_data["token"]["roles"],
            keystone_token_exp=token_data["token"]["expires_at"],
            base_domains=CONF.openstack.base_domains,
            exp=exp or int(time.time()) + CONF.default.access_token_expire,
            uuid=uuid_value or uuid.uuid4().hex,
            version=version.version_string(),
        )
