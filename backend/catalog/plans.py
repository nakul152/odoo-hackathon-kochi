from datetime import date
from decimal import Decimal
from typing import Literal, Optional

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.database import get_connection

router = APIRouter(prefix="/plans", tags=["Plans"])


class PlanIn(BaseModel):
    name: str = Field(max_length=150)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    billing_period: Literal["daily", "weekly", "monthly", "yearly"]
    min_quantity: int = Field(default=1, ge=1)
    start_date: date
    end_date: Optional[date] = None
    auto_close: bool = False
    closable: bool = False
    pausable: bool = False
    renewable: bool = False

    @field_validator("name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        if self.auto_close and not self.end_date:
            raise ValueError("auto_close needs an end_date")
        return self


COLUMNS = ("name, price, billing_period, min_quantity, start_date, end_date, "
           "auto_close, closable, pausable, renewable")


def values(d: PlanIn):
    return (d.name, d.price, d.billing_period, d.min_quantity, d.start_date,
            d.end_date, d.auto_close, d.closable, d.pausable, d.renewable)


@router.post("", status_code=201)
def create_plan(data: PlanIn):
    with get_connection() as conn:
        return conn.execute(
            f"INSERT INTO plans ({COLUMNS}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            values(data),
        ).fetchone()


@router.get("")
def list_plans():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM plans ORDER BY id").fetchall()


@router.get("/{plan_id}")
def get_plan(plan_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM plans WHERE id=%s", (plan_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return row


@router.put("/{plan_id}")
def update_plan(plan_id: int, data: PlanIn):
    with get_connection() as conn:
        row = conn.execute(
            """UPDATE plans SET name=%s, price=%s, billing_period=%s, min_quantity=%s,
               start_date=%s, end_date=%s, auto_close=%s, closable=%s, pausable=%s,
               renewable=%s WHERE id=%s RETURNING *""",
            values(data) + (plan_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return row


@router.delete("/{plan_id}")
def delete_plan(plan_id: int):
    try:
        with get_connection() as conn:
            row = conn.execute(
                "DELETE FROM plans WHERE id=%s RETURNING id", (plan_id,)
            ).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(
            status_code=400,
            detail="This plan is used by a subscription or template and cannot be deleted",
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"message": "Plan deleted"}