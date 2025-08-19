from pydantic import BaseModel

class SignupRequest(BaseModel):
    username: str
    password: str
    name: str
    email: str
    student_id: str