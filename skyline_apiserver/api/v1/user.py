# 사용자 회원가입을 처리하는 API 엔드포인트를 제공하는 파일입니다.
from fastapi import APIRouter, Depends, HTTPException
from skyline_apiserver.schemas.user import SignupRequest
from skyline_apiserver.client.openstack.keystone import create_user

router = APIRouter()

@router.post("/signup", tags=["User"])
async def signup(user: SignupRequest):
    success, msg = await create_user(user)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}