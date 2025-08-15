from fastapi import APIRouter, Depends, HTTPException
from schemas.user import SignupRequest
from client.openstack.keystone import create_user

router = APIRouter()

@router.post("/signup", tags=["User"])
async def signup(user: SignupRequest):
    success, msg = await create_user(user)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}