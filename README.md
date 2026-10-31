# odoo-hackathon-kochi
# Subscription Management System

One platform to run plans, subscriptions and recurring billing: products and plans, quotations, subscriptions, automatic invoices, taxes, discounts, payments and a finance dashboard. Built for the **Odoo x Make-A-Ton 9.0 Kochi Hackathon 2026** (Brightloop Software problem statement).

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python, FastAPI | Clear, fast REST APIs with automatic validation and docs at `/docs` |
| Database | PostgreSQL (local) | Relational data with constraints; no third-party backend-as-a-service |
| Frontend | HTML, CSS, vanilla JavaScript | No build step, small dependency surface |
| Auth | bcrypt password hashing, JWT access tokens | Standard, simple, role-aware |

## Features

**Accounts and access**
- Sign up with a unique email; password must be more than 8 characters with an uppercase letter, a lowercase letter and a special character
- Login with role-based access: **admin**, **staff**, **customer**
- Only the admin can add staff members
- Forgot password: one-time reset link (valid 30 minutes, stored hashed)

**Catalogue and subscriptions**
- Products with sales price, cost price, notes and variants (for example Brand: Odoo adds 560); products are deactivated instead of deleted, so old subscriptions keep their history
- Plans with billing period (daily, weekly, monthly, yearly), minimum quantity, start and end dates, and flags for auto-close, early close, pause and renew. The early-close flag is enforced; pause, renew and auto-close are stored and planned for a later version
- Quotation templates (name, validity days, optional plan, product lines). A subscription created from a template copies its lines and sets its expiry to start date plus validity days
- Subscriptions numbered SUB-0001, with each line priced as product price plus variant extra. Status flow Draft, Quotation, Confirmed, Active, Closed: only valid next steps are allowed, and invalid jumps return a clear error. An active subscription can be closed only if its plan allows it. Becoming active sets the next billing date
- All catalogue endpoints require an admin or staff login, and the creating user is recorded
- Pages: Products & Plans and Subscriptions (variants and quotation templates are managed through the API)
- Catalogue API: `/products`, `/products/{id}/variants`, `/plans`, `/quotation-templates`, `/subscriptions`, `PATCH /subscriptions/{id}/status`

**Billing day and invoices**
- One click (or `POST /billing/run`) creates an invoice for every active subscription whose next billing date has arrived; nobody types an invoice by hand
- Each invoice is built from its subscription: customer, product lines (with the chosen variant in the description), quantities, unit prices, taxes and totals, numbered INV-00001
- The due date comes from the subscription's payment terms (for example "Net 15" gives 15 days)
- **Nothing billed twice:** one invoice per subscription per billing period, enforced by a database unique constraint, so running billing twice creates nothing new
- **Nothing skipped:** if a subscription was missed, billing catches up one period at a time (with a safety limit), then moves the next billing date forward by the plan's period
- One failing subscription never stops the rest: each is billed in its own transaction and problems are listed in the result
- Invoice status flow Draft, Confirmed, Paid, with Cancel allowed from Draft or Confirmed. An invoice becomes Paid automatically when its balance reaches zero
- Invoice detail shows lines, tax, discounts applied, totals, payments and balance

**Taxes and discounts**
- The admin sets up taxes (name and percentage). Tax is calculated automatically on each invoice line, after that line's discount. Taxes are switched off, not deleted, because old invoices still use them
- Only the admin can create discount rules: fixed amount or percentage, minimum purchase, minimum quantity, start and end dates, and a usage limit
- A discount applies to one product or to a whole subscription. Once it applies, it appears on the next invoice by itself (as its own line in the invoice's discount list) and stops when it expires or runs out
- A discount that was already used on an invoice cannot be deleted; the admin sets an end date instead

**Payments**
- Each payment records its method (cash, card, UPI, bank transfer or cheque), amount, date, a note and who recorded it, against the right invoice
- Payments are accepted only on confirmed invoices, never for more than the outstanding balance, and never dated in the future. Part payments are supported
- **Outstanding** and **Overdue** lists show total, paid, balance and days late, so overdue invoices can be chased before they turn into lost revenue
- Customers see only their own invoices and payments (not drafts)

**Billing pages and API**
- Pages: Invoices (billing day, status filter, paging, confirm, cancel, invoice detail), Payments (record a payment, outstanding and overdue lists) and Discounts & Taxes (admin only)
- A standalone billing screen is also available at `/billing/ui`
- Forms check input before sending and show plain-language errors (for example "A percentage cannot be more than 100"); the server checks everything again

| Endpoint | Who | Purpose |
|---|---|---|
| `POST /billing/run` | admin, staff | Billing day (optional `?today=YYYY-MM-DD` for testing) |
| `GET /billing/invoices`, `GET /billing/invoices/{id}` | logged in (customers see only their own) | List with filters and paging, invoice detail |
| `POST /billing/invoices/{id}/confirm`, `/cancel` | admin, staff | Change invoice status |
| `POST /billing/invoices/{id}/payments`, `GET .../payments` | admin, staff record; logged in view | Record and list payments |
| `GET /billing/outstanding`, `GET /billing/overdue` | admin, staff | Unpaid and late invoices |
| `POST/GET/PUT/DELETE /billing/taxes` | admin writes; admin, staff read | Tax setup |
| `POST/GET/PUT/DELETE /billing/discounts` | admin writes; admin, staff read | Discount rules |

**Finance dashboard**
- Active subscriptions, revenue collected, outstanding and overdue amounts, revenue by month
- Invoice list with status filter, search, date range and pagination

**Customer portal**
- Customers see only their own subscriptions and invoices, with invoice detail and payments
- Customers can close a subscription early when its plan allows it

## Project structure

```
backend/
  main.py            app setup and routers
  database.py        PostgreSQL connection
  security.py        JWT creation, current user, role checks
  auth.py            signup, login, staff management
  password_reset.py  forgot and reset password
  dashboard.py       finance summary and invoice list
  portal.py          customer-facing endpoints
  catalog/           products, variants, plans, quotation templates, subscriptions
  billing/
    invoicing.py     billing day: invoices, taxes and discounts
    payments.py      payments, outstanding and overdue lists
    admin.py         tax and discount setup (with validation)
    access.py        customers see only their own invoices
    router.py        billing endpoints and invoice status changes
  seed_admin.py      creates the first admin from .env
  seed_demo.py       optional demo data
frontend/
  css/style.css      shared design
  css/billing.css    extra styles for the billing pages
  js/api.js          API helper, friendly error messages
  js/layout.js       shared sidebar menu (role aware)
  js/billing-common.js  shared billing helpers (money format, messages)
  invoices.html      invoices and billing day
  payments.html      payments, outstanding and overdue
  discounts.html     discounts and taxes (admin)
  billing/           standalone billing screen at /billing/ui
  *.html             other pages
database/
  schema.sql         full database schema
```

## Database design

16 tables, normalised, with constraints that protect the business rules:

- `users` (unique email, role check), `customers` (linked to a login), `password_reset_tokens`
- `products`, `product_variants` (extra price per variant), `taxes`
- `plans` (billing period check, flags for auto-close, closable, pausable, renewable)
- `quotation_templates`, `quotation_template_lines`
- `subscriptions` (unique number, status check) and `subscription_lines`
- `invoices`, `invoice_lines`, `invoice_discounts`, `discounts`, `payments`

Key design decisions:
- `UNIQUE (subscription_id, billing_period_start)` on `invoices` prevents double billing even if generation runs twice or two people click billing at the same moment (the insert uses `ON CONFLICT DO NOTHING`)
- Status columns use `CHECK` constraints so invalid states cannot be stored
- Payments are stored as rows; an invoice balance is `total - SUM(payments)`, so partial payments work
- Money is calculated with exact decimals, never floating point, rounded half-up to 2 places
- Discount usage is claimed with a guarded update (`times_used < usage_limit`), so a limit can never be exceeded; each applied discount is saved in `invoice_discounts`
- A payment locks its invoice row while checking the balance, so two payments at the same moment cannot overpay an invoice
- Indexes on subscription status, next billing date, invoice status and due date, payment date and invoice keep list and dashboard queries fast with thousands of rows

## Setup

1. Install Python 3.13+ and PostgreSQL.
2. Create a database named `subscriptions` and run `database/schema.sql` in it (pgAdmin Query Tool, or `psql`).
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the project root (never commit it):
   ```
   DB_PASSWORD=postgres123
   JWT_SECRET=i-am-inevitable
   ADMIN_EMAIL=admin@test.com
   ADMIN_PASSWORD=Admin@12345
   ```
   Optional, for real reset emails: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`. Without them the reset link is printed in the server terminal.
5. Create the first admin: `python -m backend.seed_admin`
6. Optional demo data: `python -m backend.seed_demo` (or `python -m backend.seed_demo 3000` to test speed)
7. Start the server: `uvicorn backend.main:app --reload`
8. Open http://127.0.0.1:8000 (API docs at http://127.0.0.1:8000/docs)

## Security notes

- Passwords hashed with bcrypt; never stored or logged in plain text
- JWT tokens expire after 8 hours; every protected endpoint checks the role on the server
- Billing endpoints are role-checked: only the admin sets up taxes and discounts; admin and staff run billing, change invoice status and record payments; a customer can only open their own invoices (another customer's invoice returns "not found")
- All SQL uses parameterised queries
- Reset tokens are random, stored as hashes, single use, and expire in 30 minutes; the forgot-password reply is identical whether or not the email exists
- Secrets live in `.env`, which is git-ignored
- Text from the database is escaped before it is shown in pages

## Performance

Indexes cover the common filters, lists are paginated on the server, and totals are computed in SQL. Billing lists (invoices, outstanding, overdue) are paginated and use the indexes on invoice status and due date. Tested with 300 subscriptions: 241 ms for login, 110 ms for portal/subscriptions.

## Team

| Member | Area |
|---|---|
| A M Nakul (team leader) | Database design, accounts, roles, staff, password reset, dashboard, customer portal |
| Adwaith Narayan M | Products, variants, plans, quotation templates, subscriptions |
| Sreerag C R | Billing day and invoices, taxes, discounts, payments, billing pages |

## Possible next steps

- Online payments and payment reminders by email
- Scheduled automatic invoice generation (today billing day is started with one click)
- Send and print invoices (email and PDF)
- Audit log and CSV export of reports
- Forms for variants and quotation templates, and behaviour for pause, renew and auto-close
