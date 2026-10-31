from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.database import get_connection
from backend.billing import invoicing

router = APIRouter(prefix="/billing", tags=["Billing"])

VALID_STATUSES = ("draft", "confirmed", "paid", "cancelled")


@router.get("/ping")
def ping():
    return {"module": "billing", "status": "ok"}


@router.post("/run")
def run_billing(today: Optional[date] = Query(
        None, description="Leave empty for today. Set a date (YYYY-MM-DD) to test.")):
    """Billing day: create invoices for every subscription that is due."""
    return invoicing.run_billing_day(today)


@router.get("/invoices")
def list_invoices(status: Optional[str] = None,
                  customer_id: Optional[int] = None,
                  limit: int = Query(50, ge=1, le=200),
                  offset: int = Query(0, ge=0)):
    if status and status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {', '.join(VALID_STATUSES)}")
    conditions, params = [], []
    if status:
        conditions.append("i.status = %s")
        params.append(status)
    if customer_id:
        conditions.append("i.customer_id = %s")
        params.append(customer_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with get_connection() as conn:
        return conn.execute(
            f"""SELECT i.id, i.number, i.status, i.issue_date, i.due_date, i.total,
                       c.name AS customer
                FROM invoices i JOIN customers c ON c.id = i.customer_id
                {where} ORDER BY i.id DESC LIMIT %s OFFSET %s""",
            params + [limit, offset],
        ).fetchall()


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int):
    with get_connection() as conn:
        invoice = conn.execute(
            """SELECT i.*, c.name AS customer, s.number AS subscription_number
               FROM invoices i
               JOIN customers c ON c.id = i.customer_id
               JOIN subscriptions s ON s.id = i.subscription_id
               WHERE i.id = %s""", (invoice_id,)).fetchone()
        if invoice is None:
            raise HTTPException(404, "Invoice not found")
        invoice["lines"] = conn.execute(
            "SELECT * FROM invoice_lines WHERE invoice_id = %s ORDER BY id",
            (invoice_id,)).fetchall()
        invoice["discounts"] = conn.execute(
            """SELECT d.name, idc.amount FROM invoice_discounts idc
               JOIN discounts d ON d.id = idc.discount_id
               WHERE idc.invoice_id = %s""", (invoice_id,)).fetchall()
        return invoice


def change_status(invoice_id: int, allowed_from: list, new_status: str):
    with get_connection() as conn:
        row = conn.execute(
            """UPDATE invoices SET status = %s
               WHERE id = %s AND status = ANY(%s)
               RETURNING id, number, status""",
            (new_status, invoice_id, allowed_from)).fetchone()
        if row is None:
            current = conn.execute("SELECT status FROM invoices WHERE id = %s",
                                   (invoice_id,)).fetchone()
            if current is None:
                raise HTTPException(404, "Invoice not found")
            raise HTTPException(
                400, f"Cannot change an invoice from '{current['status']}' "
                     f"to '{new_status}'")
        return row


@router.post("/invoices/{invoice_id}/confirm")
def confirm_invoice(invoice_id: int):
    return change_status(invoice_id, ["draft"], "confirmed")


@router.post("/invoices/{invoice_id}/cancel")
def cancel_invoice(invoice_id: int):
    return change_status(invoice_id, ["draft", "confirmed"], "cancelled")