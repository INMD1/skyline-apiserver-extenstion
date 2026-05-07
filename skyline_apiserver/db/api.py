# 데이터베이스 모델과 상호 작용하기 위한 고수준의 데이터베이스 API를 정의하는 파일입니다.
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
from functools import wraps
from typing import Any, Union

from sqlalchemy import Insert, Update, delete, func, insert, select, update

from skyline_apiserver.types import Fn

from .base import DB, inject_db
from .models import InstanceLifecycle, RevokedToken, Settings, UserActivity


def check_db_connected(fn: Fn) -> Any:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        inject_db()
        db = DB.get()
        assert db is not None, "Database is not connected."
        return fn(*args, **kwargs)

    return wrapper


@check_db_connected
def check_token(token_id: str) -> bool:
    count_label = "revoked_count"
    query = (
        select(func.count(RevokedToken.c.uuid).label(count_label))
        .select_from(RevokedToken)
        .where(RevokedToken.c.uuid == token_id)
    )
    db = DB.get()
    with db.transaction():
        result = db.fetch_one(query)
    count = getattr(result, count_label, 0)
    return count > 0


@check_db_connected
def revoke_token(token_id: str, expire: int) -> Any:
    query = insert(RevokedToken)
    db = DB.get()
    with db.transaction():
        result = db.execute(query, {"uuid": token_id, "expire": expire})
    return result


@check_db_connected
def purge_revoked_token() -> Any:
    now = int(time.time()) - 1
    query = delete(RevokedToken).where(RevokedToken.c.expire < now)
    db = DB.get()
    with db.transaction():
        result = db.execute(query)
    return result


@check_db_connected
def list_settings() -> Any:
    query = select(Settings)
    db = DB.get()
    with db.transaction():
        result = db.fetch_all(query)
    return result


@check_db_connected
def get_setting(key: str) -> Any:
    query = select(Settings).where(Settings.c.key == key)
    db = DB.get()
    with db.transaction():
        result = db.fetch_one(query)
    return result


@check_db_connected
def update_setting(key: str, value: Any) -> Any:
    get_query = (
        select(Settings.c.key, Settings.c.value)
        .where(Settings.c.key == key)
        .with_for_update()
    )
    db = DB.get()
    with db.transaction():
        is_exist = db.fetch_one(get_query)
        stmt: Union[Insert, Update]
        if is_exist is None:
            stmt = insert(Settings).values(key=key, value=value)
        else:
            stmt = update(Settings).where(Settings.c.key == key).values(value=value)
        db.execute(stmt)
        result = db.fetch_one(get_query)
    return result


@check_db_connected
def delete_setting(key: str) -> Any:
    query = delete(Settings).where(Settings.c.key == key)
    db = DB.get()
    with db.transaction():
        result = db.execute(query)
    return result


@check_db_connected
def create_activity_record(
    user_id: str,
    project_id: str,
    category: str,
    message: str,
    status: str,
    token: str,
) -> Any:
    query = insert(UserActivity).values(
        user_id=user_id,
        project_id=project_id,
        category=category,
        message=message,
        status=status,
        token=token,
        timestamp=int(time.time()),
    )
    db = DB.get()
    with db.transaction():
        result = db.execute(query)
    return result


@check_db_connected
def get_activity_records_by_user(user_id: str) -> Any:
    query = select(UserActivity).where(UserActivity.c.user_id == user_id).order_by(UserActivity.c.timestamp.desc())
    db = DB.get()
    with db.transaction():
        result = db.fetch_all(query)
    return result


@check_db_connected
def get_activity_records_by_project(project_id: str) -> Any:
    query = select(UserActivity).where(UserActivity.c.project_id == project_id).order_by(UserActivity.c.timestamp.desc())
    db = DB.get()
    with db.transaction():
        result = db.fetch_all(query)
    return result


# ──────────────────────────────────────────────
#  인스턴스 라이프사이클 관련 DB API
# ──────────────────────────────────────────────

@check_db_connected
def create_instance_lifecycle(
    instance_id: str,
    instance_name: str,
    user_id: str,
    project_id: str,
    user_email: str,
    created_at: int,
    expires_at: int,
) -> Any:
    """인스턴스 라이프사이클 레코드를 생성합니다."""
    query = insert(InstanceLifecycle).values(
        instance_id=instance_id,
        instance_name=instance_name,
        user_id=user_id,
        project_id=project_id,
        user_email=user_email,
        created_at=created_at,
        expires_at=expires_at,
        email_status="none",
        email_sent_at=None,
        extended=False,
    )
    db = DB.get()
    with db.transaction():
        result = db.execute(query)
    return result


@check_db_connected
def get_instance_lifecycle(instance_id: str) -> Any:
    """특정 인스턴스의 라이프사이클 레코드를 조회합니다."""
    query = select(InstanceLifecycle).where(InstanceLifecycle.c.instance_id == instance_id)
    db = DB.get()
    with db.transaction():
        result = db.fetch_one(query)
    return result


@check_db_connected
def list_instance_lifecycles_expiring_before(threshold: int) -> Any:
    """expires_at 이 threshold 이전이고 아직 처리 중인 레코드를 모두 반환합니다."""
    query = (
        select(InstanceLifecycle)
        .where(InstanceLifecycle.c.expires_at <= threshold)
        .where(InstanceLifecycle.c.email_status != "deleted")
    )
    db = DB.get()
    with db.transaction():
        result = db.fetch_all(query)
    return result


@check_db_connected
def list_instance_lifecycles_awaiting_reply(threshold: int) -> Any:
    """이메일을 보냈지만 threshold 이후까지 연장하지 않은 레코드를 반환합니다.

    threshold: 이메일 발송 후 유예 기간(Unix timestamp)이 지난 시점
    """
    query = (
        select(InstanceLifecycle)
        .where(InstanceLifecycle.c.email_status == "sent")
        .where(InstanceLifecycle.c.email_sent_at <= threshold)
        .where(InstanceLifecycle.c.extended == False)  # noqa: E712
    )
    db = DB.get()
    with db.transaction():
        result = db.fetch_all(query)
    return result


@check_db_connected
def update_instance_lifecycle_email_sent(instance_id: str, sent_at: int) -> Any:
    """이메일 발송 완료 상태로 업데이트합니다."""
    stmt = (
        update(InstanceLifecycle)
        .where(InstanceLifecycle.c.instance_id == instance_id)
        .values(email_status="sent", email_sent_at=sent_at)
    )
    db = DB.get()
    with db.transaction():
        result = db.execute(stmt)
    return result


@check_db_connected
def update_instance_lifecycle_extended(instance_id: str, new_expires_at: int) -> Any:
    """사용자가 연장을 확인했을 때 상태를 업데이트합니다."""
    stmt = (
        update(InstanceLifecycle)
        .where(InstanceLifecycle.c.instance_id == instance_id)
        .values(email_status="extended", extended=True, expires_at=new_expires_at)
    )
    db = DB.get()
    with db.transaction():
        result = db.execute(stmt)
    return result


@check_db_connected
def update_instance_lifecycle_deleted(instance_id: str) -> Any:
    """인스턴스 삭제 처리 상태로 업데이트합니다."""
    stmt = (
        update(InstanceLifecycle)
        .where(InstanceLifecycle.c.instance_id == instance_id)
        .values(email_status="deleted")
    )
    db = DB.get()
    with db.transaction():
        result = db.execute(stmt)
    return result


@check_db_connected
def delete_instance_lifecycle(instance_id: str) -> Any:
    """인스턴스 라이프사이클 레코드를 삭제합니다."""
    query = delete(InstanceLifecycle).where(InstanceLifecycle.c.instance_id == instance_id)
    db = DB.get()
    with db.transaction():
        result = db.execute(query)
    return result