from decimal import Decimal
from typing import Optional

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.database import get_connection

router = APIRouter(prefix="/products", tags=["Products"])


class ProductIn(BaseModel):
    """What the user must send. Pydantic checks it automatically."""
    name: str = Field(max_length=150)
    type: str = Field(max_length=50)
    sales_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    cost_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    notes: Optional[str] = None
    tax_id: Optional[int] = None

    @field_validator("name", "type")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


@router.post("", status_code=201)
def create_product(data: ProductIn):
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO products (name, type, sales_price, cost_price, notes, tax_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (data.name, data.type, data.sales_price, data.cost_price,
                 data.notes, data.tax_id),
            ).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(status_code=400, detail="The selected tax does not exist")
    return row


@router.get("")
def list_products(active_only: bool = True):
    query = "SELECT * FROM products"
    if active_only:
        query += " WHERE is_active = TRUE"
    query += " ORDER BY id"
    with get_connection() as conn:
        return conn.execute(query).fetchall()


@router.get("/{product_id}")
def get_product(product_id: int):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE id = %s", (product_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return row


@router.put("/{product_id}")
def update_product(product_id: int, data: ProductIn):
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                UPDATE products
                SET name=%s, type=%s, sales_price=%s, cost_price=%s, notes=%s, tax_id=%s
                WHERE id=%s
                RETURNING *
                """,
                (data.name, data.type, data.sales_price, data.cost_price,
                 data.notes, data.tax_id, product_id),
            ).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(status_code=400, detail="The selected tax does not exist")
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return row


@router.delete("/{product_id}")
def deactivate_product(product_id: int):
    """Soft delete: old subscriptions still refer to this product, so we hide it instead."""
    with get_connection() as conn:
        row = conn.execute(
            "UPDATE products SET is_active = FALSE WHERE id = %s RETURNING id",
            (product_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"message": "Product deactivated"}

from backend.catalog.variants import router as variants_router  # noqa: E402

router.include_router(variants_router)