# 사용자 관련 API(회원가입 등)의 데이터 스키마를 정의하는 파일입니다.
import re
from pydantic import BaseModel, Field, field_validator


class SignupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=128)
    email: str = Field(..., max_length=254)

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username may only contain letters, digits, underscores, and hyphens")
        return v

    @field_validator("email")
    @classmethod
    def email_format(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("Invalid email format")
        return v


class ChangePasswordBody(BaseModel):
    original_password: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    user: ChangePasswordBody