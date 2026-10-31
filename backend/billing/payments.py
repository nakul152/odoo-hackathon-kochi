"""Payments: record money received, and show what is paid, outstanding or overdue."""
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.database import get_connection

router = APIRouter(tags=["Payments"])


class PaymentIn(BaseModel):
    method: Literal["cash", "card", "upi", "bank_transfer", "cheque"]
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    payment_date: Optional[date] = None      # empty = today
    note: Optional[str] = Field(None, max_length=500)


@router.post("/invoices/{invoice_id}/payments", status_code=201)
def record_payment(invoice_id: int, data: PaymentIn):
    """Record a payment. When the invoice is fully paid it becomes 'paid'."""
    pay_date = data.payment_date or date.today()
    if pay_date > date.today():
        raise HTTPException(400, "Payment date cannot be in the future")

    with get_connection() as conn:
        with conn.transaction():
            # FOR UPDATE locks the invoice, so two payments at the same moment
            # cannot both slip past the balance check.
            invoice = conn.execute(
                "SELECT id, number, status, total FROM invoices "
                "WHERE id = %s FOR UPDATE", (invoice_id,)).fetchone()
            if invoice is None:
                raise HTTPException(404, "Invoice not found")
            if invoice["status"] != "confirmed":
                raise HTTPException(
                    400, f"Payments can only be recorded on confirmed invoices "
                         f"(this one is '{invoice['status']}')")

            paid = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS paid FROM payments "
                "WHERE invoice_id = %s", (invoice_id,)).fetchone()["paid"]
            balance = invoice["total"] - paid
            if data.amount > balance:
                raise HTTPException(
                    400, f"Payment of {data.amount} is more than the outstanding "
                         f"balance of {balance}")

            payment = conn.execute(
                """INSERT INTO payments (invoice_id, method, amount, payment_date, note)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING id, method, amount, payment_date, note""",
                (invoice_id, data.method, data.amount, pay_date, data.note)).fetchone()

            new_balance = balance - data.amount
            status = invoice["status"]
            if new_balance == 0:
                conn.execute("UPDATE invoices SET status = 'paid' WHERE id = %s",
                             (invoice_id,))
                status = "paid"

    return {"payment": payment, "invoice_number": invoice["number"],
            "invoice_status": status, "balance_remaining": new_balance}


@router.get("/invoices/{invoice_id}/payments")
def list_payments(invoice_id: int):
    with get_connection() as conn:
        invoice = conn.execute(
            "SELECT id, number, status, total FROM invoices WHERE id = %s",
            (invoice_id,)).fetchone()
        if invoice is None:
            raise HTTPException(404, "Invoice not found")
        payments = conn.execute(
            "SELECT id, method, amount, payment_date, note FROM payments "
            "WHERE invoice_id = %s ORDER BY payment_date, id", (invoice_id,)).fetchall()
    paid = sum((p["amount"] for p in payments), Decimal("0"))
    return {"invoice": invoice, "paid": paid, "balance": invoice["total"] - paid,
            "payments": payments}


UNPAID_SQL = """
    SELECT i.id, i.number, c.name AS customer, i.due_date, i.total,
           COALESCE(p.paid, 0) AS paid,
           i.total - COALESCE(p.paid, 0) AS balance,
           GREATEST(CURRENT_DATE - i.due_date, 0) AS days_overdue
    FROM invoices i
    JOIN customers c ON c.id = i.customer_id
    LEFT JOIN LATERAL (SELECT SUM(amount) AS paid FROM payments
                       WHERE invoice_id = i.id) p ON TRUE
    WHERE i.status = 'confirmed' {extra}
    ORDER BY i.due_date, i.id
    LIMIT %s OFFSET %s
"""


@router.get("/outstanding")
def outstanding_invoices(limit: int = Query(50, ge=1, le=200),
                         offset: int = Query(0, ge=0)):
    """Confirmed invoices that are not fully paid yet."""
    with get_connection() as conn:
        return conn.execute(UNPAID_SQL.format(extra=""), (limit, offset)).fetchall()


@router.get("/overdue")
def overdue_invoices(limit: int = Query(50, ge=1, le=200),
                     offset: int = Query(0, ge=0)):
    """Unpaid invoices whose due date has passed, so they can be chased."""
    with get_connection() as conn:
        return conn.execute(
            UNPAID_SQL.format(extra="AND i.due_date < CURRENT_DATE"),
            (limit, offset)).fetchall()