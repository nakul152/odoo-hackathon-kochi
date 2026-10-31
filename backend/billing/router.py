from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from backend.billing import invoicing
from backend.billing.access import own_customer_id
from backend.billing.admin import router as admin_router
from backend.billing.payments import router as payments_router
from backend.database import get_connection
from backend.security import get_current_user, require_roles

router = APIRouter(prefix="/billing", tags=["Billing"])
router.include_router(payments_router)
router.include_router(admin_router)

UI_DIR = Path(__file__).resolve().parents[2] / "frontend" / "billing"
VALID_STATUSES = ("draft", "confirmed", "paid", "cancelled")
STAFF_ONLY = [Depends(require_roles("admin", "staff"))]


@router.get("/ping")
def ping():
    return {"module": "billing", "status": "ok"}


# ---- the billing page itself (the data behind it is protected) ----
@router.get("/ui", include_in_schema=False)
def ui_page():
    return FileResponse(UI_DIR / "index.html")


@router.get("/ui/style.css", include_in_schema=False)
def ui_css():
    return FileResponse(UI_DIR / "style.css", media_type="text/css")


@router.get("/ui/app.js", include_in_schema=False)
def ui_js():
    return FileResponse(UI_DIR / "app.js", media_type="application/javascript")


# ---- billing day ----
@router.post("/run", dependencies=STAFF_ONLY)
def run_billing(today: Optional[date] = Query(
        None, description="Leave empty for today. Set a date (YYYY-MM-DD) to test.")):
    """Billing day: create invoices for every subscription that is due."""
    return invoicing.run_billing_day(today)


# ---- invoices ----
@router.get("/invoices")
def list_invoices(status: Optional[str] = None,
                  customer_id: Optional[int] = None,
                  limit: int = Query(50, ge=1, le=200),
                  offset: int = Query(0, ge=0),
                  user=Depends(get_current_user)):
    if status and status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {', '.join(VALID_STATUSES)}")
    conditions, params = [], []
    with get_connection() as conn:
        own = own_customer_id(conn, user)
        if own is not None:               # a customer: only their own, no drafts
            customer_id = own
            conditions.append("i.status <> 'draft'")
        if status:
            conditions.append("i.status = %s")
            params.append(status)
        if customer_id:
            conditions.append("i.customer_id = %s")
            params.append(customer_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return conn.execute(
            f"""SELECT i.id, i.number, i.status, i.issue_date, i.due_date, i.total,
                       c.name AS customer
                FROM invoices i JOIN customers c ON c.id = i.customer_id
                {where} ORDER BY i.id DESC LIMIT %s OFFSET %s""",
            params + [limit, offset],
        ).fetchall()


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, user=Depends(get_current_user)):
    with get_connection() as conn:
        own = own_customer_id(conn, user)
        invoice = conn.execute(
            """SELECT i.*, c.name AS customer, s.number AS subscription_number
               FROM invoices i
               JOIN customers c ON c.id = i.customer_id
               JOIN subscriptions s ON s.id = i.subscription_id
               WHERE i.id = %s""", (invoice_id,)).fetchone()
        # A customer asking for someone else's invoice gets "not found".
        if invoice is None or (own is not None and invoice["customer_id"] != own):
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


@router.post("/invoices/{invoice_id}/confirm", dependencies=STAFF_ONLY)
def confirm_invoice(invoice_id: int):
    return change_status(invoice_id, ["draft"], "confirmed")


@router.post("/invoices/{invoice_id}/cancel", dependencies=STAFF_ONLY)
def cancel_invoice(invoice_id: int):
    return change_status(invoice_id, ["draft", "confirmed"], "cancelled")