import os
import secrets
import hashlib
import smtplib
from email.message import EmailMessage

import bcrypt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from backend.database import get_connection
from backend.auth import password_problems

router = APIRouter(prefix="/auth", tags=["Auth"])

FRONTEND_URL = os.getenv(
    "FRONTEND_URL", "http://127.0.0.1:8000/static/reset-password.html"
)


class ForgotRequest(BaseModel):
    email: EmailStr


class ResetRequest(BaseModel):
    token: str
    new_password: str


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def send_reset_email(to_email: str, link: str):
    host = os.getenv("SMTP_HOST")
    if not host:
        # No email server configured: show the link in the terminal instead
        print(f"\nPASSWORD RESET LINK for {to_email}:\n{link}\n")
        return
    msg = EmailMessage()
    msg["Subject"] = "Reset your password"
    msg["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", ""))
    msg["To"] = to_email
    msg.set_content(
        f"Click this link to reset your password (valid for 30 minutes):\n{link}"
    )
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as server:
        server.starttls()
        server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
        server.send_message(msg)


@router.post("/forgot-password")
def forgot_password(data: ForgotRequest):
    email = data.email.lower()
    token = None

    with get_connection() as conn:
        user = conn.execute(
            "SELECT id FROM users WHERE email = %s AND is_active", (email,)
        ).fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            conn.execute(
                "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) "
                "VALUES (%s, %s, NOW() + INTERVAL '30 minutes')",
                (user["id"], hash_token(token)),
            )

    if token:
        send_reset_email(email, f"{FRONTEND_URL}?token={token}")

    # Same answer whether or not the email exists, so nobody can probe for accounts
    return {"message": "If this email is registered, a reset link has been sent"}


@router.post("/reset-password")
def reset_password(data: ResetRequest):
    problems = password_problems(data.new_password)
    if problems:
        raise HTTPException(status_code=422, detail=problems)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, user_id FROM password_reset_tokens "
            "WHERE token_hash = %s AND used = FALSE AND expires_at > NOW()",
            (hash_token(data.token),),
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=400, detail=["Reset link is invalid or has expired"]
            )

        new_hash = bcrypt.hashpw(
            data.new_password.encode(), bcrypt.gensalt()
        ).decode()
        conn.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (new_hash, row["user_id"]),
        )
        conn.execute(
            "UPDATE password_reset_tokens SET used = TRUE WHERE id = %s", (row["id"],)
        )

    return {"message": "Password updated. You can now log in"}