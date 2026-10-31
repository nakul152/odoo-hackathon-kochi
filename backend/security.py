import os
import datetime
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.database import get_connection

load_dotenv()

SECRET = os.getenv("JWT_SECRET")
if not SECRET:
    raise RuntimeError("JWT_SECRET is missing in the .env file")

bearer = HTTPBearer(auto_error=False)


def create_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8),
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if creds is None:
        raise HTTPException(status_code=401, detail=["Please log in first"])
    try:
        payload = jwt.decode(creds.credentials, SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail=["Session expired, please log in again"])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail=["Invalid login token"])

    with get_connection() as conn:
        user = conn.execute(
            "SELECT id, name, email, role, is_active FROM users WHERE id = %s",
            (int(payload["sub"]),),
        ).fetchone()
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail=["Account not found or disabled"])
    return user


def require_roles(*allowed):
    def checker(user=Depends(get_current_user)):
        if user["role"] not in allowed:
            raise HTTPException(
                status_code=403,
                detail=["You do not have permission to do this"],
            )
        return user
    return checker