# 사용자가 활동한 기록을 저장하고 추후 활동 내역에서 조회를 할수
# 있도록 하는 OpenStack 클라이언트 기능을 제공하는 파일입니다.
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
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from keystoneauth1.exceptions.http import Unauthorized
from keystoneauth1.session import Session

from skyline_apiserver.db import api as db_api


def create_activity(
    session: Session,
    category: str,  # e.g., 'login', 'instance_create', 'volume_delete'
    message: str,  # 활동에 대한 설명 메시지
    status_result: str,  # success or failure 2개로 구분됨
) -> Any:
    try:
        token = session.get_token()
        user_id = session.get_user_id()
        project_id = session.get_project_id()

        # DB에 활동 기록 저장
        activity_record = db_api.create_activity_record(
            user_id=user_id,
            project_id=project_id,
            category=category,
            message=message,
            status=status_result,
            token=token,
        )
        return activity_record
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


def get_activities_by_user(user_id: str) -> Any:
    try:
        return db_api.get_activity_records_by_user(user_id=user_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

 