from decimal import Decimal

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.database import get_connection

router = APIRouter(prefix="/{product_id}/variants", tags=["Product Variants"])


class VariantIn(BaseModel):
    attribute: str = Field(max_length=50)
    value: str = Field(max_length=100)
    extra_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)

    @field_validator("attribute", "value")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v


@router.post("", status_code=201)
def add_variant(product_id: int, data: VariantIn):
    try:
        with get_connection() as conn:
            return conn.execute(
                """
                INSERT INTO product_variants (product_id, attribute, value, extra_price)
                VALUES (%s, %s, %s, %s) RETURNING *
                """,
                (product_id, data.attribute, data.value, data.extra_price),
            ).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(status_code=404, detail="Product not found")


@router.get("")
def list_variants(product_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM product_variants WHERE product_id = %s ORDER BY id",
            (product_id,),
        ).fetchall()


@router.put("/{variant_id}")
def update_variant(product_id: int, variant_id: int, data: VariantIn):
    with get_connection() as conn:
        row = conn.execute(
            """
            UPDATE product_variants SET attribute=%s, value=%s, extra_price=%s
            WHERE id=%s AND product_id=%s RETURNING *
            """,
            (data.attribute, data.value, data.extra_price, variant_id, product_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Variant not found")
    return row


@router.delete("/{variant_id}")
def delete_variant(product_id: int, variant_id: int):
    try:
        with get_connection() as conn:
            row = conn.execute(
                "DELETE FROM product_variants WHERE id=%s AND product_id=%s RETURNING id",
                (variant_id, product_id),
            ).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(
            status_code=400,
            detail="This variant is used in a template or subscription and cannot be deleted",
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Variant not found")
    return {"message": "Variant deleted"}