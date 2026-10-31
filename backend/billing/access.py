"""Helper: which invoices may a logged-in user see?"""
from fastapi import HTTPException


def own_customer_id(conn, user):
    """Customers may only see their own invoices.
    Returns the customer's id for a customer login, or None for admin/staff."""
    if user["role"] != "customer":
        return None
    row = conn.execute("SELECT id FROM customers WHERE user_id = %s",
                       (user["id"],)).fetchone()
    if row is None:
        raise HTTPException(403, ["No customer profile is linked to this account"])
    return row["id"]