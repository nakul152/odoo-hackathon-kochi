import uuid
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from backend.database import get_connection
from backend.security import require_roles

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

# current status -> statuses it may move to
TRANSITIONS = {
    "draft": ["quotation", "closed"],
    "quotation": ["confirmed", "draft", "closed"],
    "confirmed": ["active", "closed"],
    "active": ["closed"],
    "closed": [],
}


class LineIn(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: int = Field(default=1, gt=0)


class SubscriptionIn(BaseModel):
    customer_id: int
    plan_id: int
    template_id: Optional[int] = None
    start_date: date
    expiry_date: Optional[date] = None
    payment_terms: Optional[str] = Field(default=None, max_length=100)
    lines: list[LineIn] = []

    @model_validator(mode="after")
    def check_dates(self):
        if self.expiry_date and self.expiry_date < self.start_date:
            raise ValueError("expiry_date cannot be before start_date")
        return self


class StatusIn(BaseModel):
    status: Literal["draft", "quotation", "confirmed", "active", "closed"]


def bad(message: str):
    return HTTPException(status_code=400, detail=message)


def build_line(conn, line: LineIn):
    product = conn.execute(
        "SELECT sales_price, tax_id, is_active FROM products WHERE id=%s",
        (line.product_id,),
    ).fetchone()
    if product is None or not product["is_active"]:
        raise bad(f"Product {line.product_id} does not exist or is inactive")
    extra = 0
    if line.variant_id is not None:
        variant = conn.execute(
            "SELECT extra_price FROM product_variants WHERE id=%s AND product_id=%s",
            (line.variant_id, line.product_id),
        ).fetchone()
        if variant is None:
            raise bad(f"Variant {line.variant_id} does not belong to product {line.product_id}")
        extra = variant["extra_price"]
    unit_price = product["sales_price"] + extra
    return (line.product_id, line.variant_id, line.quantity, unit_price,
            product["tax_id"], unit_price * line.quantity)


def load_subscription(conn, subscription_id: int):
    sub = conn.execute(
        """SELECT s.*, c.name AS customer_name, p.name AS plan_name
           FROM subscriptions s
           JOIN customers c ON c.id = s.customer_id
           JOIN plans p ON p.id = s.plan_id
           WHERE s.id=%s""",
        (subscription_id,),
    ).fetchone()
    if sub is None:
        return None
    sub["lines"] = conn.execute(
        "SELECT * FROM subscription_lines WHERE subscription_id=%s ORDER BY id",
        (subscription_id,),
    ).fetchall()
    sub["total"] = sum(line["amount"] for line in sub["lines"])
    return sub


@router.post("", status_code=201)
def create_subscription(data: SubscriptionIn, user=Depends(require_roles("admin", "staff"))):
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM customers WHERE id=%s", (data.customer_id,)).fetchone() is None:
            raise bad("Customer does not exist")
        if conn.execute("SELECT 1 FROM plans WHERE id=%s", (data.plan_id,)).fetchone() is None:
            raise bad("Plan does not exist")

        lines = list(data.lines)
        expiry = data.expiry_date
        if data.template_id is not None:
            template = conn.execute(
                "SELECT validity_days FROM quotation_templates WHERE id=%s",
                (data.template_id,),
            ).fetchone()
            if template is None:
                raise bad("Template does not exist")
            if not lines:
                rows = conn.execute(
                    "SELECT product_id, variant_id, quantity FROM quotation_template_lines "
                    "WHERE template_id=%s ORDER BY id",
                    (data.template_id,),
                ).fetchall()
                lines = [LineIn(**r) for r in rows]
            if expiry is None:
                expiry = data.start_date + timedelta(days=template["validity_days"])
        if not lines:
            raise bad("A subscription needs at least one product line")

        built = [build_line(conn, line) for line in lines]

        # temporary unique number, replaced by SUB-000X once we know the id
        sub = conn.execute(
            """INSERT INTO subscriptions
               (number, customer_id, plan_id, template_id, start_date, expiry_date,
                payment_terms, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            ("TMP-" + uuid.uuid4().hex[:20], data.customer_id, data.plan_id,
             data.template_id, data.start_date, expiry, data.payment_terms, user["id"]),
        ).fetchone()
        for b in built:
            conn.execute(
                """INSERT INTO subscription_lines
                   (subscription_id, product_id, variant_id, quantity, unit_price, tax_id, amount)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (sub["id"],) + b,
            )
        conn.execute(
            "UPDATE subscriptions SET number = 'SUB-' || LPAD(id::text, 4, '0') WHERE id=%s",
            (sub["id"],),
        )
        return load_subscription(conn, sub["id"])


@router.get("")
def list_subscriptions(status: Optional[str] = None, customer_id: Optional[int] = None):
    query = ("SELECT s.*, c.name AS customer_name FROM subscriptions s "
             "JOIN customers c ON c.id = s.customer_id WHERE TRUE")
    params = []
    if status:
        query += " AND s.status = %s"
        params.append(status)
    if customer_id:
        query += " AND s.customer_id = %s"
        params.append(customer_id)
    query += " ORDER BY s.id DESC"
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


@router.get("/{subscription_id}")
def get_subscription(subscription_id: int):
    with get_connection() as conn:
        row = load_subscription(conn, subscription_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return row


@router.patch("/{subscription_id}/status")
def change_status(subscription_id: int, data: StatusIn):
    with get_connection() as conn:
        sub = conn.execute(
            """SELECT s.id, s.status, s.start_date, s.next_billing_date, p.closable
               FROM subscriptions s JOIN plans p ON p.id = s.plan_id
               WHERE s.id=%s FOR UPDATE OF s""",
            (subscription_id,),
        ).fetchone()
        if sub is None:
            raise HTTPException(status_code=404, detail="Subscription not found")

        current, new = sub["status"], data.status
        allowed = TRANSITIONS[current]
        if new not in allowed:
            raise bad(
                f"Cannot change status from '{current}' to '{new}'. "
                f"Allowed: {', '.join(allowed) if allowed else 'none (it is closed)'}"
            )
        if current == "active" and new == "closed" and not sub["closable"]:
            raise bad("This plan does not allow closing an active subscription")

        next_billing = sub["next_billing_date"]
        if new == "active" and next_billing is None:
            next_billing = sub["start_date"]  # first invoice is due on the start date

        conn.execute(
            "UPDATE subscriptions SET status=%s, next_billing_date=%s WHERE id=%s",
            (new, next_billing, subscription_id),
        )
        return load_subscription(conn, subscription_id)


@router.delete("/{subscription_id}")
def delete_subscription(subscription_id: int):
    with get_connection() as conn:
        sub = conn.execute(
            "SELECT status FROM subscriptions WHERE id=%s", (subscription_id,)
        ).fetchone()
        if sub is None:
            raise HTTPException(status_code=404, detail="Subscription not found")
        if sub["status"] != "draft":
            raise bad("Only draft subscriptions can be deleted. Close it instead.")
        conn.execute("DELETE FROM subscriptions WHERE id=%s", (subscription_id,))
    return {"message": "Subscription deleted"}