import re
import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from psycopg.errors import UniqueViolation
from backend.database import get_connection
from backend.security import create_token, get_current_user, require_roles

router = APIRouter(prefix="/auth", tags=["Auth"])


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def password_problems(password: str) -> list[str]:
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


def create_user(data: SignupRequest, role: str):
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
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (name, email, password_hash, role),
            ).fetchone()
            if role == "customer":
                conn.execute(
                    "INSERT INTO customers (user_id, name, email) VALUES (%s, %s, %s)",
                    (user["id"], name, email),
                )
    except UniqueViolation:
        raise HTTPException(
            status_code=409, detail=["An account with this email already exists"]
        )


@router.post("/signup", status_code=201)
def signup(data: SignupRequest):
    create_user(data, "customer")
    return {"message": "Account created successfully"}


@router.post("/staff", status_code=201)
def create_staff(data: SignupRequest, admin=Depends(require_roles("admin"))):
    create_user(data, "staff")
    return {"message": "Staff account created successfully"}


@router.post("/login")
def login(data: LoginRequest):
    with get_connection() as conn:
        user = conn.execute(
            "SELECT id, name, password_hash, role, is_active FROM users WHERE email = %s",
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
        "access_token": create_token(user["id"], user["role"]),
        "user": {"id": user["id"], "name": user["name"], "role": user["role"]},
    }


@router.get("/me")
def me(user=Depends(get_current_user)):
    return user