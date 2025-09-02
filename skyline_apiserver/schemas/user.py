# 사용자 관련 API(회원가입 등)의 데이터 스키마를 정의하는 파일입니다.
from pydantic import BaseModel

class SignupRequest(BaseModel):
    username: str
    password: str
    name: str
    email: str
    student_id: str