# odoo-hackathon-kochi
# Subscription Management System

One platform to run plans, subscriptions and recurring billing: products and plans, quotations, subscriptions, automatic invoices, taxes, discounts, payments and a finance dashboard. Built for the **Odoo x Make-A-Ton 9.0 Kochi Hackathon 2026** (Brightloop Software problem statement).

> Items marked **[UPDATE]** must be confirmed by the teammate who built that part before submission. Delete this line when done.

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

**Billing** **[UPDATE]**
- Invoices generated from subscriptions with customer details, lines, taxes and totals
- One invoice per subscription per billing period, enforced by a database unique constraint (nothing billed twice)
- Tax rules set by the admin; admin-only discount rules (fixed or percentage, minimums, dates, usage limit) applied automatically
- Invoice status flow Draft, Confirmed, Paid; payments recorded by method, amount, date and note

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
  billing/           invoices, taxes, discounts, payments       [UPDATE]
  seed_admin.py      creates the first admin from .env
  seed_demo.py       optional demo data
frontend/
  css/style.css      shared design
  js/api.js          API helper, friendly error messages
  js/layout.js       shared sidebar menu (role aware)
  *.html             pages
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
- `UNIQUE (subscription_id, billing_period_start)` on `invoices` prevents double billing even if generation runs twice
- Status columns use `CHECK` constraints so invalid states cannot be stored
- Payments are stored as rows; an invoice balance is `total - SUM(payments)`, so partial payments work
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
   ADMIN_EMAIL=admin@example.com
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
- All SQL uses parameterised queries
- Reset tokens are random, stored as hashes, single use, and expire in 30 minutes; the forgot-password reply is identical whether or not the email exists
- Secrets live in `.env`, which is git-ignored
- Text from the database is escaped before it is shown in pages

## Performance

Indexes cover the common filters, lists are paginated on the server, and totals are computed in SQL. Tested with 3000 subscriptions: **[UPDATE with measured load times]**.

## Team

| Member | Area |
|---|---|
| [A M Nakul] (team leader) | Database design, accounts, roles, staff, password reset, dashboard, customer portal |
| [Adwaith Narayan M] | Products, variants, plans, quotation templates, subscriptions |
| [Sreerag C R] | Invoices, taxes, discounts, payments **[UPDATE]** |

## Possible next steps

- Online payments and payment reminders by email
- Scheduled automatic invoice generation
- Audit log and CSV export of reports
- Forms for variants and quotation templates, and behaviour for pause, renew and auto-close