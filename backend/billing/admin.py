"""Admin setup: taxes and discount rules (with validation)."""
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.database import get_connection

router = APIRouter(tags=["Taxes & Discounts"])


# ===================== TAXES =====================
class TaxIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=50)
    rate: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)


@router.post("/taxes", status_code=201)
def create_tax(data: TaxIn):
    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM taxes WHERE lower(name) = lower(%s) AND is_active",
            (data.name,)).fetchone()
        if exists:
            raise HTTPException(400, f"A tax named '{data.name}' already exists")
        return conn.execute(
            "INSERT INTO taxes (name, rate) VALUES (%s, %s) RETURNING *",
            (data.name, data.rate)).fetchone()


@router.get("/taxes")
def list_taxes(include_inactive: bool = False):
    where = "" if include_inactive else "WHERE is_active"
    with get_connection() as conn:
        return conn.execute(f"SELECT * FROM taxes {where} ORDER BY id").fetchall()


@router.put("/taxes/{tax_id}")
def update_tax(tax_id: int, data: TaxIn):
    with get_connection() as conn:
        row = conn.execute(
            "UPDATE taxes SET name = %s, rate = %s WHERE id = %s RETURNING *",
            (data.name, data.rate, tax_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Tax not found")
    return row


@router.delete("/taxes/{tax_id}")
def deactivate_tax(tax_id: int):
    """Taxes are switched off, not deleted, because old invoices still use them."""
    with get_connection() as conn:
        row = conn.execute(
            "UPDATE taxes SET is_active = FALSE WHERE id = %s RETURNING id, name, is_active",
            (tax_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Tax not found")
    return row


# ===================== DISCOUNTS =====================
class DiscountIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    type: Literal["fixed", "percent"]
    value: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    min_purchase: Decimal = Field(0, ge=0, max_digits=12, decimal_places=2)
    min_quantity: int = Field(0, ge=0)
    start_date: date
    end_date: Optional[date] = None
    usage_limit: Optional[int] = Field(None, ge=1)
    product_id: Optional[int] = None          # discount on one product...
    subscription_id: Optional[int] = None     # ...or on a whole subscription

    @model_validator(mode="after")
    def check_rules(self):
        if self.type == "percent" and self.value > 100:
            raise ValueError("A percentage discount cannot be more than 100")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before the start date")
        if self.product_id is None and self.subscription_id is None:
            raise ValueError("Choose a product_id or a subscription_id for this discount")
        return self


def check_targets(conn, data: DiscountIn):
    """Give a friendly error instead of a database crash for unknown ids."""
    if data.product_id is not None and not conn.execute(
            "SELECT 1 FROM products WHERE id = %s", (data.product_id,)).fetchone():
        raise HTTPException(400, f"Product {data.product_id} does not exist")
    if data.subscription_id is not None and not conn.execute(
            "SELECT 1 FROM subscriptions WHERE id = %s", (data.subscription_id,)).fetchone():
        raise HTTPException(400, f"Subscription {data.subscription_id} does not exist")


COLUMNS = ("name, type, value, min_purchase, min_quantity, start_date, end_date, "
           "usage_limit, product_id, subscription_id")


@router.post("/discounts", status_code=201)
def create_discount(data: DiscountIn):
    with get_connection() as conn:
        check_targets(conn, data)
        return conn.execute(
            f"INSERT INTO discounts ({COLUMNS}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "RETURNING *",
            (data.name, data.type, data.value, data.min_purchase, data.min_quantity,
             data.start_date, data.end_date, data.usage_limit, data.product_id,
             data.subscription_id)).fetchone()


@router.get("/discounts")
def list_discounts(active_only: bool = False,
                   limit: int = Query(50, ge=1, le=200),
                   offset: int = Query(0, ge=0)):
    """'is_active_now' is true while the discount is in its dates and not used up."""
    active = ("(d.start_date <= CURRENT_DATE AND (d.end_date IS NULL OR d.end_date >= CURRENT_DATE) "
              "AND (d.usage_limit IS NULL OR d.times_used < d.usage_limit))")
    where = f"WHERE {active}" if active_only else ""
    with get_connection() as conn:
        return conn.execute(
            f"SELECT d.*, {active} AS is_active_now FROM discounts d {where} "
            "ORDER BY d.id DESC LIMIT %s OFFSET %s", (limit, offset)).fetchall()


@router.put("/discounts/{discount_id}")
def update_discount(discount_id: int, data: DiscountIn):
    with get_connection() as conn:
        current = conn.execute("SELECT times_used FROM discounts WHERE id = %s",
                               (discount_id,)).fetchone()
        if current is None:
            raise HTTPException(404, "Discount not found")
        if data.usage_limit is not None and data.usage_limit < current["times_used"]:
            raise HTTPException(
                400, f"Usage limit cannot be below the {current['times_used']} "
                     f"times it has already been used")
        check_targets(conn, data)
        return conn.execute(
            "UPDATE discounts SET name=%s, type=%s, value=%s, min_purchase=%s, "
            "min_quantity=%s, start_date=%s, end_date=%s, usage_limit=%s, "
            "product_id=%s, subscription_id=%s WHERE id=%s RETURNING *",
            (data.name, data.type, data.value, data.min_purchase, data.min_quantity,
             data.start_date, data.end_date, data.usage_limit, data.product_id,
             data.subscription_id, discount_id)).fetchone()


@router.delete("/discounts/{discount_id}")
def delete_discount(discount_id: int):
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM discounts WHERE id = %s",
                            (discount_id,)).fetchone():
            raise HTTPException(404, "Discount not found")
        if conn.execute("SELECT 1 FROM invoice_discounts WHERE discount_id = %s LIMIT 1",
                        (discount_id,)).fetchone():
            raise HTTPException(
                400, "This discount was already used on invoices. "
                     "Set an end date instead of deleting it.")
        conn.execute("DELETE FROM discounts WHERE id = %s", (discount_id,))
    return {"deleted": discount_id}