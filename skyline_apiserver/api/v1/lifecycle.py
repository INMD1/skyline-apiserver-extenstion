# 인스턴스 라이프사이클(수명 연장) 관련 API 엔드포인트입니다.
from __future__ import annotations

import time

from fastapi import Depends, HTTPException, status
from fastapi.routing import APIRouter
from pydantic import BaseModel

from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.db import api as db_api

router = APIRouter()


class LifecycleStatusResponse(BaseModel):
    instance_id: str
    instance_name: str | None
    created_at: int
    expires_at: int
    email_status: str
    email_sent_at: int | None
    extended: bool
    # 남은 시간(초), 음수이면 이미 만료
    remaining_seconds: int


class ExtendResponse(BaseModel):
    instance_id: str
    new_expires_at: int
    message: str


@router.get(
    "/instances/{instance_id}/lifecycle",
    description="인스턴스의 라이프사이클(만료) 상태를 조회합니다.",
    response_model=LifecycleStatusResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": schemas.UnauthorizedMessage},
        404: {"model": schemas.NotFoundMessage},
    },
)
def get_lifecycle_status(
    instance_id: str,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
) -> LifecycleStatusResponse:
    row = db_api.get_instance_lifecycle(instance_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 인스턴스의 라이프사이클 정보가 없습니다.",
        )

    now = int(time.time())
    return LifecycleStatusResponse(
        instance_id=row.instance_id,
        instance_name=row.instance_name,
        created_at=row.created_at,
        expires_at=row.expires_at,
        email_status=row.email_status,
        email_sent_at=row.email_sent_at,
        extended=row.extended,
        remaining_seconds=row.expires_at - now,
    )


@router.post(
    "/instances/{instance_id}/extend",
    description="인스턴스 사용 기간을 1개월(30일) 연장합니다.",
    response_model=ExtendResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": schemas.UnauthorizedMessage},
        404: {"model": schemas.NotFoundMessage},
        409: {"model": schemas.ConflictMessage},
    },
)
def extend_instance_lifecycle(
    instance_id: str,
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
) -> ExtendResponse:
    row = db_api.get_instance_lifecycle(instance_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 인스턴스의 라이프사이클 정보가 없습니다.",
        )

    if row.email_status == "deleted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 삭제된 인스턴스입니다.",
        )

    now = int(time.time())
    # 현재 expires_at 기준으로 30일 연장 (이미 만료된 경우 현재 시각 기준)
    base = max(row.expires_at, now)
    new_expires_at = base + 30 * 86400

    db_api.update_instance_lifecycle_extended(instance_id, new_expires_at)

    return ExtendResponse(
        instance_id=instance_id,
        new_expires_at=new_expires_at,
        message="인스턴스 사용 기간이 30일 연장되었습니다.",
    )
