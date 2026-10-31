from fastapi import FastAPI
from backend.database import get_connection

app = FastAPI(title="Subscription Management System")


@app.get("/")
def home():
    return {"message": "Server is running"}


@app.get("/health/db")
def db_health():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS tables FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        ).fetchone()
    return {"database": "connected", "tables": row["tables"]}