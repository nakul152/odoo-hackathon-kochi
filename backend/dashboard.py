from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.database import get_connection
from backend.security import require_roles

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
staff_or_admin = require_roles("admin", "staff")

PAID_SUBQUERY = (
    "LEFT JOIN (SELECT invoice_id, SUM(amount) AS paid FROM payments GROUP BY invoice_id) p "
    "ON p.invoice_id = i.id"
)


@router.get("/summary")
def summary(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    user=Depends(staff_or_admin),
):
    with get_connection() as conn:
        subs = conn.execute(
            "SELECT status, COUNT(*) AS count FROM subscriptions GROUP BY status"
        ).fetchall()

        revenue = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count FROM payments "
            "WHERE (%(f)s::date IS NULL OR payment_date >= %(f)s::date) "
            "AND (%(t)s::date IS NULL OR payment_date <= %(t)s::date)",
            {"f": date_from, "t": date_to},
        ).fetchone()

        owed = conn.execute(
            "SELECT COUNT(*) AS invoices, "
            "COALESCE(SUM(i.total - COALESCE(p.paid, 0)), 0) AS amount, "
            "COUNT(*) FILTER (WHERE i.due_date < CURRENT_DATE) AS overdue_invoices, "
            "COALESCE(SUM(i.total - COALESCE(p.paid, 0)) "
            "         FILTER (WHERE i.due_date < CURRENT_DATE), 0) AS overdue_amount "
            f"FROM invoices i {PAID_SUBQUERY} WHERE i.status = 'confirmed'"
        ).fetchone()

        monthly = conn.execute(
            "SELECT to_char(date_trunc('month', payment_date), 'YYYY-MM') AS month, "
            "SUM(amount) AS total FROM payments "
            "WHERE payment_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '11 months' "
            "GROUP BY 1 ORDER BY 1"
        ).fetchall()

    by_status = {row["status"]: row["count"] for row in subs}
    return {
        "active_subscriptions": by_status.get("active", 0),
        "subscriptions_by_status": by_status,
        "revenue_collected": revenue["total"],
        "payments_count": revenue["count"],
        "outstanding_amount": owed["amount"],
        "outstanding_invoices": owed["invoices"],
        "overdue_amount": owed["overdue_amount"],
        "overdue_invoices": owed["overdue_invoices"],
        "revenue_by_month": monthly,
    }


@router.get("/invoices")
def invoice_list(
    status: str = "all",
    search: str = "",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(staff_or_admin),
):
    where = ["1 = 1"]
    params = {}

    if status == "paid":
        where.append("i.status = 'paid'")
    elif status == "outstanding":
        where.append("i.status = 'confirmed'")
    elif status == "overdue":
        where.append("i.status = 'confirmed' AND i.due_date < CURRENT_DATE")
    elif status == "draft":
        where.append("i.status = 'draft'")
    elif status != "all":
        raise HTTPException(status_code=422, detail=["Invalid status filter"])

    if search.strip():
        where.append("(c.name ILIKE %(s)s OR i.number ILIKE %(s)s)")
        params["s"] = f"%{search.strip()}%"
    if date_from:
        where.append("i.issue_date >= %(f)s")
        params["f"] = date_from
    if date_to:
        where.append("i.issue_date <= %(t)s")
        params["t"] = date_to

    where_sql = " AND ".join(where)
    base = f"FROM invoices i JOIN customers c ON c.id = i.customer_id {PAID_SUBQUERY} WHERE {where_sql}"

    with get_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS n {base}", params).fetchone()["n"]
        rows = conn.execute(
            "SELECT i.id, i.number, c.name AS customer, i.status, i.issue_date, i.due_date, "
            "i.total, COALESCE(p.paid, 0) AS paid, i.total - COALESCE(p.paid, 0) AS balance, "
            "(i.status = 'confirmed' AND i.due_date < CURRENT_DATE) AS overdue "
            f"{base} ORDER BY i.issue_date DESC, i.id DESC LIMIT %(limit)s OFFSET %(offset)s",
            {**params, "limit": page_size, "offset": (page - 1) * page_size},
        ).fetchall()

    return {"total": total, "page": page, "page_size": page_size, "items": rows}