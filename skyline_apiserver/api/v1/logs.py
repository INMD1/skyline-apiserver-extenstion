from fastapi import APIRouter, Depends
from skyline_apiserver import schemas
from skyline_apiserver.api import deps
from skyline_apiserver.db import api as db_api

router = APIRouter()


@router.get("/projectlogs")
def get_project_logs(
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """
    현재 프로젝트의 활동 로그를 조회합니다.
    """
    project_logs = db_api.get_activity_records_by_project(profile.project.id)
    return {"project_logs": [dict(log._mapping) for log in project_logs]}


@router.get("/userlogs")
def get_user_logs(
    profile: schemas.Profile = Depends(deps.get_profile_from_header),
):
    """
    현재 사용자의 활동 로그를 조회합니다.
    """
    user_logs = db_api.get_activity_records_by_user(profile.user.id)
    return {"user_logs": [dict(log._mapping) for log in user_logs]}
