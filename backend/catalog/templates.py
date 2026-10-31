from typing import Optional

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.database import get_connection

router = APIRouter(prefix="/quotation-templates", tags=["Quotation Templates"])


class LineIn(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: int = Field(default=1, gt=0)


class TemplateIn(BaseModel):
    name: str = Field(max_length=150)
    validity_days: int = Field(gt=0)
    plan_id: Optional[int] = None
    lines: list[LineIn] = []

    @field_validator("name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v


def load_template(conn, template_id: int):
    template = conn.execute(
        "SELECT * FROM quotation_templates WHERE id=%s", (template_id,)
    ).fetchone()
    if template is None:
        return None
    template["lines"] = conn.execute(
        "SELECT * FROM quotation_template_lines WHERE template_id=%s ORDER BY id",
        (template_id,),
    ).fetchall()
    return template


def save_lines(conn, template_id: int, lines: list[LineIn]):
    for line in lines:
        if line.variant_id is not None:
            ok = conn.execute(
                "SELECT 1 FROM product_variants WHERE id=%s AND product_id=%s",
                (line.variant_id, line.product_id),
            ).fetchone()
            if ok is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Variant {line.variant_id} does not belong to product {line.product_id}",
                )
        conn.execute(
            """INSERT INTO quotation_template_lines (template_id, product_id, variant_id, quantity)
               VALUES (%s,%s,%s,%s)""",
            (template_id, line.product_id, line.variant_id, line.quantity),
        )


@router.post("", status_code=201)
def create_template(data: TemplateIn):
    try:
        with get_connection() as conn:
            row = conn.execute(
                """INSERT INTO quotation_templates (name, validity_days, plan_id)
                   VALUES (%s,%s,%s) RETURNING id""",
                (data.name, data.validity_days, data.plan_id),
            ).fetchone()
            save_lines(conn, row["id"], data.lines)
            return load_template(conn, row["id"])
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(status_code=400, detail="The plan or a product does not exist")


@router.get("")
def list_templates():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM quotation_templates ORDER BY id").fetchall()


@router.get("/{template_id}")
def get_template(template_id: int):
    with get_connection() as conn:
        row = load_template(conn, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return row


@router.put("/{template_id}")
def update_template(template_id: int, data: TemplateIn):
    try:
        with get_connection() as conn:
            row = conn.execute(
                """UPDATE quotation_templates SET name=%s, validity_days=%s, plan_id=%s
                   WHERE id=%s RETURNING id""",
                (data.name, data.validity_days, data.plan_id, template_id),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Template not found")
            conn.execute(
                "DELETE FROM quotation_template_lines WHERE template_id=%s", (template_id,)
            )
            save_lines(conn, template_id, data.lines)
            return load_template(conn, template_id)
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(status_code=400, detail="The plan or a product does not exist")


@router.delete("/{template_id}")
def delete_template(template_id: int):
    try:
        with get_connection() as conn:
            row = conn.execute(
                "DELETE FROM quotation_templates WHERE id=%s RETURNING id", (template_id,)
            ).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        raise HTTPException(
            status_code=400, detail="This template is used by a subscription and cannot be deleted"
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"message": "Template deleted"}