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