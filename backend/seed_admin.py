import os
import bcrypt
from dotenv import load_dotenv
from backend.database import get_connection

load_dotenv()

email = os.getenv("ADMIN_EMAIL")
password = os.getenv("ADMIN_PASSWORD")
if not email or not password:
    raise SystemExit("Set ADMIN_EMAIL and ADMIN_PASSWORD in .env first")

password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

with get_connection() as conn:
    conn.execute(
        "INSERT INTO users (name, email, password_hash, role) "
        "VALUES ('Admin', %s, %s, 'admin') ON CONFLICT (email) DO NOTHING",
        (email.lower(), password_hash),
    )
print("Admin ready:", email)