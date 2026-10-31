"""Billing day: turns due subscriptions into invoices (with taxes and discounts)."""
import calendar
import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from backend.database import get_connection

MAX_CATCHUP_PERIODS = 24  # safety limit if a subscription was missed many times


def money(value):
    """Round to 2 decimals the way money is normally rounded."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def add_period(start, billing_period):
    """Date of the next billing, one period after 'start'."""
    if billing_period == "daily":
        return start + timedelta(days=1)
    if billing_period == "weekly":
        return start + timedelta(weeks=1)
    months = 12 if billing_period == "yearly" else 1
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def due_days(payment_terms):
    """'Net 15' -> 15. Defaults to 15 days if no number is found."""
    match = re.search(r"\d+", payment_terms or "")
    return int(match.group()) if match else 15


LINES_SQL = """
    SELECT sl.product_id, sl.quantity, sl.unit_price,
           COALESCE(sl.tax_id, p.tax_id) AS tax_id,
           t.rate AS tax_rate,
           p.name AS product_name, v.attribute, v.value AS variant_value
    FROM subscription_lines sl
    JOIN products p ON p.id = sl.product_id
    LEFT JOIN product_variants v ON v.id = sl.variant_id
    LEFT JOIN taxes t ON t.id = COALESCE(sl.tax_id, p.tax_id)
    WHERE sl.subscription_id = %s
    ORDER BY sl.id
"""

DISCOUNTS_SQL = """
    SELECT id, type, value, min_purchase, min_quantity, product_id
    FROM discounts
    WHERE start_date <= %s
      AND (end_date IS NULL OR end_date >= %s)
      AND (usage_limit IS NULL OR times_used < usage_limit)
      AND (product_id IS NOT NULL OR subscription_id IS NOT NULL)
      AND (subscription_id IS NULL OR subscription_id = %s)
    ORDER BY id
"""


def create_invoice(conn, sub, today):
    """Create ONE invoice for the subscription's current billing period.
    Returns {'id','number','total'}, or None if that period was already billed."""
    period_start = sub["next_billing_date"]
    period_end = add_period(period_start, sub["billing_period"]) - timedelta(days=1)

    lines = conn.execute(LINES_SQL, (sub["id"],)).fetchall()
    if not lines:
        raise ValueError("subscription has no lines to bill")

    # Reserve the invoice id first so the number (INV-00001) can be built from it.
    invoice_id = conn.execute(
        "SELECT nextval(pg_get_serial_sequence('invoices', 'id')) AS id"
    ).fetchone()["id"]
    number = f"INV-{invoice_id:05d}"

    # ON CONFLICT DO NOTHING + the UNIQUE rule in the database = never billed twice,
    # even if two people click "Run billing" at the same moment.
    inserted = conn.execute(
        """INSERT INTO invoices (id, number, subscription_id, customer_id,
                                 billing_period_start, billing_period_end,
                                 issue_date, due_date)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (subscription_id, billing_period_start) DO NOTHING
           RETURNING id""",
        (invoice_id, number, sub["id"], sub["customer_id"], period_start,
         period_end, today, today + timedelta(days=due_days(sub["payment_terms"]))),
    ).fetchone()
    if inserted is None:
        return None  # this period already has an invoice

    for line in lines:
        line["amount"] = money(line["quantity"] * line["unit_price"])
        line["discount"] = Decimal("0")

    # ---- Discounts: applied automatically, stop when expired or used up ----
    applied = []
    for d in conn.execute(DISCOUNTS_SQL, (today, today, sub["id"])).fetchall():
        eligible = [l for l in lines
                    if d["product_id"] is None or l["product_id"] == d["product_id"]]
        base = sum((l["amount"] for l in eligible), Decimal("0"))
        qty = sum(l["quantity"] for l in eligible)
        if base <= 0 or base < d["min_purchase"] or qty < d["min_quantity"]:
            continue

        if d["type"] == "percent":
            amount = money(base * d["value"] / 100)
        else:
            amount = money(d["value"])
        amount = min(amount, base)

        # Use up one "use" safely. If the limit was just reached, skip this discount.
        claimed = conn.execute(
            """UPDATE discounts SET times_used = times_used + 1
               WHERE id = %s AND (usage_limit IS NULL OR times_used < usage_limit)
               RETURNING id""",
            (d["id"],),
        ).fetchone()
        if claimed is None:
            continue

        applied.append((invoice_id, d["id"], amount))
        for l in eligible:  # share the discount across the lines it covers
            l["discount"] += money(amount * l["amount"] / base)

    # ---- Taxes: calculated on each line AFTER its discount ----
    subtotal = discount_total = tax_total = Decimal("0")
    line_rows = []
    for l in lines:
        l["discount"] = min(l["discount"], l["amount"])
        net = l["amount"] - l["discount"]
        l["tax_amount"] = money(net * (l["tax_rate"] or 0) / 100)
        subtotal += l["amount"]
        discount_total += l["discount"]
        tax_total += l["tax_amount"]

        description = l["product_name"]
        if l["variant_value"]:
            description += f" ({l['attribute']}: {l['variant_value']})"
        line_rows.append((invoice_id, l["product_id"], description, l["quantity"],
                          l["unit_price"], l["tax_id"], l["tax_amount"], l["amount"]))

    total = subtotal - discount_total + tax_total

    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO invoice_lines (invoice_id, product_id, description, quantity,
                                          unit_price, tax_id, tax_amount, amount)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", line_rows)
        if applied:
            cur.executemany(
                "INSERT INTO invoice_discounts (invoice_id, discount_id, amount) "
                "VALUES (%s, %s, %s)", applied)
    conn.execute(
        "UPDATE invoices SET subtotal=%s, discount_total=%s, tax_total=%s, total=%s "
        "WHERE id=%s",
        (subtotal, discount_total, tax_total, total, invoice_id))
    return {"id": invoice_id, "number": number, "total": total}


def bill_subscription(conn, subscription_id, today):
    """Bill every period of one subscription that is due up to 'today'."""
    sub = conn.execute(
        """SELECT s.id, s.number, s.customer_id, s.status, s.next_billing_date,
                  s.expiry_date, s.payment_terms, p.billing_period
           FROM subscriptions s JOIN plans p ON p.id = s.plan_id
           WHERE s.id = %s FOR UPDATE OF s""",   # lock the row while we work on it
        (subscription_id,),
    ).fetchone()
    created, skipped, periods = [], 0, 0
    if sub is None or sub["status"] != "active":
        return created, skipped

    while (sub["next_billing_date"] and sub["next_billing_date"] <= today
           and periods < MAX_CATCHUP_PERIODS):
        if sub["expiry_date"] and sub["next_billing_date"] > sub["expiry_date"]:
            break
        invoice = create_invoice(conn, sub, today)
        if invoice:
            created.append(invoice)
        else:
            skipped += 1
        sub["next_billing_date"] = add_period(sub["next_billing_date"],
                                              sub["billing_period"])
        periods += 1

    conn.execute("UPDATE subscriptions SET next_billing_date = %s WHERE id = %s",
                 (sub["next_billing_date"], sub["id"]))
    return created, skipped


def run_billing_day(today=None):
    """Create invoices for ALL due subscriptions. One bad subscription never
    stops the others: each is its own mini-transaction."""
    today = today or date.today()
    created, skipped, errors = [], 0, []
    with get_connection() as conn:
        due = conn.execute(
            "SELECT id, number FROM subscriptions "
            "WHERE status = 'active' AND next_billing_date <= %s ORDER BY id",
            (today,),
        ).fetchall()
        for row in due:
            try:
                with conn.transaction():
                    new, skip = bill_subscription(conn, row["id"], today)
                created.extend(new)
                skipped += skip
            except Exception as exc:
                errors.append({"subscription": row["number"], "error": str(exc)})
    return {"run_date": today, "subscriptions_due": len(due),
            "invoices_created": len(created), "already_billed": skipped,
            "errors": errors, "invoices": created}