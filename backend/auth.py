import re
import bcrypt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from psycopg.errors import UniqueViolation
from backend.database import get_connection

router = APIRouter(prefix="/auth", tags=["Auth"])


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def password_problems(password: str) -> list[str]:
    """Return a list of rules the password breaks (empty list = valid)."""
    problems = []
    if len(password) <= 8:
        problems.append("Password must be more than 8 characters")
    if not re.search(r"[A-Z]", password):
        problems.append("Password must contain an uppercase letter")
    if not re.search(r"[a-z]", password):
        problems.append("Password must contain a lowercase letter")
    if not re.search(r"[^A-Za-z0-9]", password):
        problems.append("Password must contain a special character")
    return problems


@router.post("/signup", status_code=201)
def signup(data: SignupRequest):
    name = data.name.strip()
    email = data.email.lower()

    if not name:
        raise HTTPException(status_code=422, detail=["Name is required"])

    problems = password_problems(data.password)
    if problems:
        raise HTTPException(status_code=422, detail=problems)

    password_hash = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()

    try:
        with get_connection() as conn:
            user = conn.execute(
                "INSERT INTO users (name, email, password_hash, role) "
                "VALUES (%s, %s, %s, 'customer') RETURNING id",
                (name, email, password_hash),
            ).fetchone()
            conn.execute(
                "INSERT INTO customers (user_id, name, email) VALUES (%s, %s, %s)",
                (user["id"], name, email),
            )
    except UniqueViolation:
        raise HTTPException(
            status_code=409, detail=["An account with this email already exists"]
        )

    return {"message": "Account created successfully"}


@router.post("/login")
def login(data: LoginRequest):
    with get_connection() as conn:
        user = conn.execute(
            "SELECT id, name, email, password_hash, role, is_active "
            "FROM users WHERE email = %s",
            (data.email.lower(),),
        ).fetchone()

    if (
        not user
        or not user["is_active"]
        or not bcrypt.checkpw(data.password.encode(), user["password_hash"].encode())
    ):
        raise HTTPException(status_code=401, detail=["Invalid email or password"])

    return {
        "message": "Login successful",
        "user": {"id": user["id"], "name": user["name"], "role": user["role"]},
    }