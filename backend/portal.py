from fastapi import APIRouter, Depends, HTTPException

from backend.database import get_connection
from backend.security import require_roles

router = APIRouter(prefix="/portal", tags=["Customer portal"])
customer_only = require_roles("customer")


def my_customer_id(conn, user) -> int:
    row = conn.execute(
        "SELECT id FROM customers WHERE user_id = %s", (user["id"],)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=["No customer profile found for this account"])
    return row["id"]


@router.get("/subscriptions")
def my_subscriptions(user=Depends(customer_only)):
    with get_connection() as conn:
        cid = my_customer_id(conn, user)
        return conn.execute(
            "SELECT s.id, s.number, s.status, s.start_date, s.expiry_date, s.next_billing_date, "
            "pl.name AS plan, pl.billing_period, pl.closable, "
            "COALESCE((SELECT SUM(l.amount) FROM subscription_lines l "
            "          WHERE l.subscription_id = s.id), 0) AS amount "
            "FROM subscriptions s JOIN plans pl ON pl.id = s.plan_id "
            "WHERE s.customer_id = %s ORDER BY s.id DESC",
            (cid,),
        ).fetchall()


@router.post("/subscriptions/{sub_id}/close")
def close_my_subscription(sub_id: int, user=Depends(customer_only)):
    with get_connection() as conn:
        cid = my_customer_id(conn, user)
        row = conn.execute(
            "SELECT s.status, pl.closable FROM subscriptions s "
            "JOIN plans pl ON pl.id = s.plan_id "
            "WHERE s.id = %s AND s.customer_id = %s",
            (sub_id, cid),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=["Subscription not found"])
        if row["status"] != "active":
            raise HTTPException(status_code=422, detail=["Only active subscriptions can be closed"])
        if not row["closable"]:
            raise HTTPException(status_code=422, detail=["This plan cannot be closed early"])
        conn.execute(
            "UPDATE subscriptions SET status = 'closed', next_billing_date = NULL WHERE id = %s",
            (sub_id,),
        )
    return {"message": "Subscription closed"}


@router.get("/invoices")
def my_invoices(user=Depends(customer_only)):
    with get_connection() as conn:
        cid = my_customer_id(conn, user)
        return conn.execute(
            "SELECT i.id, i.number, s.number AS subscription, i.status, i.issue_date, i.due_date, "
            "i.total, COALESCE(p.paid, 0) AS paid, i.total - COALESCE(p.paid, 0) AS balance, "
            "(i.status = 'confirmed' AND i.due_date < CURRENT_DATE) AS overdue "
            "FROM invoices i JOIN subscriptions s ON s.id = i.subscription_id "
            "LEFT JOIN (SELECT invoice_id, SUM(amount) AS paid FROM payments GROUP BY invoice_id) p "
            "ON p.invoice_id = i.id "
            "WHERE i.customer_id = %s AND i.status IN ('confirmed', 'paid') "
            "ORDER BY i.issue_date DESC, i.id DESC",
            (cid,),
        ).fetchall()


@router.get("/invoices/{invoice_id}")
def my_invoice_detail(invoice_id: int, user=Depends(customer_only)):
    with get_connection() as conn:
        cid = my_customer_id(conn, user)
        invoice = conn.execute(
            "SELECT id, number, status, issue_date, due_date, billing_period_start, "
            "billing_period_end, subtotal, discount_total, tax_total, total "
            "FROM invoices WHERE id = %s AND customer_id = %s AND status IN ('confirmed', 'paid')",
            (invoice_id, cid),
        ).fetchone()
        if not invoice:
            raise HTTPException(status_code=404, detail=["Invoice not found"])
        lines = conn.execute(
            "SELECT description, quantity, unit_price, tax_amount, amount "
            "FROM invoice_lines WHERE invoice_id = %s ORDER BY id",
            (invoice_id,),
        ).fetchall()
        payments = conn.execute(
            "SELECT method, amount, payment_date, note FROM payments "
            "WHERE invoice_id = %s ORDER BY payment_date, id",
            (invoice_id,),
        ).fetchall()
    return {"invoice": invoice, "lines": lines, "payments": payments}