from passlib.context import CryptContext
from fastapi import Request

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(p: str) -> str:
    return pwd.hash(p)

def verify_password(p: str, h: str) -> bool:
    return pwd.verify(p, h)

def get_user_id(request: Request):
    return request.session.get("user_id")
