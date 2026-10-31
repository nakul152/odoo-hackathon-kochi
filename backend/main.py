from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from backend.database import get_connection
from backend.auth import router as auth_router
from backend.catalog.routes import router as catalog_router
from backend.billing.router import router as billing_router
from backend.password_reset import router as reset_router

app = FastAPI(title="Subscription Management System")

app.include_router(auth_router)
app.include_router(reset_router)
app.include_router(catalog_router)
app.include_router(billing_router)


@app.exception_handler(RequestValidationError)
async def friendly_validation_errors(request: Request, exc: RequestValidationError):
    messages = [f"{err['loc'][-1]}: {err['msg']}" for err in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": messages})


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