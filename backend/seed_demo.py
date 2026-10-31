import random
import sys
from datetime import date, timedelta
from backend.database import get_connection

COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 300
random.seed(7)
today = date.today()
METHODS = ["cash", "card", "upi", "bank_transfer", "cheque"]

with get_connection() as conn:
    if conn.execute(
        "SELECT 1 FROM customers WHERE email LIKE 'demo%' LIMIT 1"
    ).fetchone():
        raise SystemExit("Demo data already exists. Nothing added.")

    tax_id = conn.execute(
        "INSERT INTO taxes (name, rate) VALUES ('GST 18 percent', 18) RETURNING id"
    ).fetchone()["id"]

    products = []
    for name, price in [("CRM Suite", 2000), ("Accounting Add-on", 800), ("Inventory Module", 1500)]:
        pid = conn.execute(
            "INSERT INTO products (name, type, sales_price, cost_price, tax_id) "
            "VALUES (%s, 'software', %s, %s, %s) RETURNING id",
            (name, price, price * 0.4, tax_id),
        ).fetchone()["id"]
        products.append((pid, price))

    monthly = conn.execute(
        "INSERT INTO plans (name, price, billing_period, start_date, closable, pausable, renewable) "
        "VALUES ('Monthly Standard', 2000, 'monthly', %s, TRUE, TRUE, TRUE) RETURNING id",
        (today - timedelta(days=500),),
    ).fetchone()["id"]
    yearly = conn.execute(
        "INSERT INTO plans (name, price, billing_period, start_date, closable, pausable, renewable) "
        "VALUES ('Yearly Business', 20000, 'yearly', %s, TRUE, FALSE, TRUE) RETURNING id",
        (today - timedelta(days=500),),
    ).fetchone()["id"]

    customer_ids = []
    for c in range(max(20, COUNT // 5)):
        customer_ids.append(
            conn.execute(
                "INSERT INTO customers (name, company, email, phone) "
                "VALUES (%s, %s, %s, '9999999999') RETURNING id",
                (f"Demo Customer {c + 1}", f"Demo Company {c + 1}", f"demo{c + 1}@example.com"),
            ).fetchone()["id"]
        )

    invoice_count = 0
    for i in range(COUNT):
        status = random.choices(
            ["active", "confirmed", "quotation", "draft", "closed"],
            weights=[60, 8, 8, 8, 16],
        )[0]
        plan_id, step = random.choice([(monthly, 30), (yearly, 365)])
        product_id, price = random.choice(products)
        qty = random.randint(1, 10)
        start = today - timedelta(days=random.randint(30, 400))
        customer_id = random.choice(customer_ids)
        next_billing = today + timedelta(days=random.randint(1, 30)) if status == "active" else None

        sub_id = conn.execute(
            "INSERT INTO subscriptions (number, customer_id, plan_id, start_date, expiry_date, "
            "payment_terms, status, next_billing_date) "
            "VALUES (%s, %s, %s, %s, %s, 'Net 15', %s, %s) RETURNING id",
            (f"DEMO-SUB-{i + 1:05d}", customer_id, plan_id, start,
             start + timedelta(days=730), status, next_billing),
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO subscription_lines (subscription_id, product_id, quantity, unit_price, tax_id, amount) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (sub_id, product_id, qty, price, tax_id, qty * price),
        )

        if status not in ("active", "closed"):
            continue

        periods = []
        k = 0
        while start + timedelta(days=step * k) <= today:
            periods.append(k)
            k += 1

        for k in periods[-3:]:
            p_start = start + timedelta(days=step * k)
            p_end = p_start + timedelta(days=step - 1)
            due = p_start + timedelta(days=15)
            subtotal = qty * price
            tax = round(subtotal * 0.18, 2)
            total = subtotal + tax

            if k == periods[-1]:
                inv_status = random.choices(["draft", "confirmed", "paid"], weights=[15, 35, 50])[0]
            else:
                inv_status = random.choices(["paid", "confirmed"], weights=[80, 20])[0]

            invoice_count += 1
            inv_id = conn.execute(
                "INSERT INTO invoices (number, subscription_id, customer_id, billing_period_start, "
                "billing_period_end, issue_date, due_date, status, subtotal, discount_total, tax_total, total) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s) RETURNING id",
                (f"DEMO-INV-{invoice_count:06d}", sub_id, customer_id, p_start, p_end,
                 p_start, due, inv_status, subtotal, tax, total),
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO invoice_lines (invoice_id, product_id, description, quantity, unit_price, tax_id, tax_amount, amount) "
                "VALUES (%s, %s, 'Subscription charge', %s, %s, %s, %s, %s)",
                (inv_id, product_id, qty, price, tax_id, tax, subtotal),
            )

            pay_amount = None
            if inv_status == "paid":
                pay_amount = total
            elif inv_status == "confirmed" and random.random() < 0.15:
                pay_amount = round(total / 2, 2)  # partial payment
            if pay_amount:
                conn.execute(
                    "INSERT INTO payments (invoice_id, method, amount, payment_date, note) "
                    "VALUES (%s, %s, %s, %s, 'Demo payment')",
                    (inv_id, random.choice(METHODS), pay_amount,
                     min(today, p_start + timedelta(days=random.randint(0, 14)))),
                )

print(f"Added {COUNT} demo subscriptions and {invoice_count} invoices")