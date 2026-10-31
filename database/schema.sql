-- Subscription Management System: PostgreSQL schema (draft v1)
-- Run in pgAdmin: create a database named "subscriptions", open Query Tool, paste and run.

-- ========== USERS & ACCESS ==========
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    email         VARCHAR(255) NOT NULL UNIQUE,          -- one account per email
    password_hash VARCHAR(255) NOT NULL,                 -- never store plain passwords
    role          VARCHAR(20)  NOT NULL CHECK (role IN ('admin', 'staff', 'customer')),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE password_reset_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(255) NOT NULL,
    expires_at  TIMESTAMP NOT NULL,
    used        BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE customers (
    id        SERIAL PRIMARY KEY,
    user_id   INT UNIQUE REFERENCES users(id) ON DELETE SET NULL,  -- link to portal login
    name      VARCHAR(150) NOT NULL,
    company   VARCHAR(150),
    email     VARCHAR(255),
    phone     VARCHAR(30),
    address   TEXT
);

-- ========== TAXES ==========
CREATE TABLE taxes (
    id        SERIAL PRIMARY KEY,
    name      VARCHAR(50) NOT NULL,                      -- e.g. GST 18%
    rate      NUMERIC(5,2) NOT NULL CHECK (rate >= 0),   -- percent
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- ========== PRODUCTS & VARIANTS ==========
CREATE TABLE products (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    type        VARCHAR(50)  NOT NULL,                   -- e.g. software, add-on
    sales_price NUMERIC(12,2) NOT NULL CHECK (sales_price >= 0),
    cost_price  NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (cost_price >= 0),
    notes       TEXT,
    tax_id      INT REFERENCES taxes(id),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE product_variants (
    id          SERIAL PRIMARY KEY,
    product_id  INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    attribute   VARCHAR(50) NOT NULL,                    -- e.g. Brand
    value       VARCHAR(100) NOT NULL,                   -- e.g. Odoo
    extra_price NUMERIC(12,2) NOT NULL DEFAULT 0         -- e.g. 560
);

-- ========== PLANS ==========
CREATE TABLE plans (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(150) NOT NULL,
    price          NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    billing_period VARCHAR(10) NOT NULL CHECK (billing_period IN ('daily','weekly','monthly','yearly')),
    min_quantity   INT NOT NULL DEFAULT 1 CHECK (min_quantity >= 1),
    start_date     DATE NOT NULL,
    end_date       DATE,
    auto_close     BOOLEAN NOT NULL DEFAULT FALSE,       -- closes itself at end_date
    closable       BOOLEAN NOT NULL DEFAULT FALSE,       -- can be closed early
    pausable       BOOLEAN NOT NULL DEFAULT FALSE,
    renewable      BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (end_date IS NULL OR end_date >= start_date)
);

-- ========== QUOTATION TEMPLATES ==========
CREATE TABLE quotation_templates (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(150) NOT NULL,
    validity_days INT NOT NULL CHECK (validity_days > 0),
    plan_id       INT REFERENCES plans(id)
);

CREATE TABLE quotation_template_lines (
    id          SERIAL PRIMARY KEY,
    template_id INT NOT NULL REFERENCES quotation_templates(id) ON DELETE CASCADE,
    product_id  INT NOT NULL REFERENCES products(id),
    variant_id  INT REFERENCES product_variants(id),
    quantity    INT NOT NULL DEFAULT 1 CHECK (quantity > 0)
);

-- ========== SUBSCRIPTIONS ==========
CREATE TABLE subscriptions (
    id                SERIAL PRIMARY KEY,
    number            VARCHAR(30) NOT NULL UNIQUE,       -- e.g. SUB-0001
    customer_id       INT NOT NULL REFERENCES customers(id),
    plan_id           INT NOT NULL REFERENCES plans(id),
    template_id       INT REFERENCES quotation_templates(id),
    start_date        DATE NOT NULL,
    expiry_date       DATE,
    payment_terms     VARCHAR(100),                      -- e.g. Net 15
    status            VARCHAR(20) NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft','quotation','confirmed','active','closed')),
    next_billing_date DATE,
    created_by        INT REFERENCES users(id),
    created_at        TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE subscription_lines (
    id              SERIAL PRIMARY KEY,
    subscription_id INT NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    product_id      INT NOT NULL REFERENCES products(id),
    variant_id      INT REFERENCES product_variants(id),
    quantity        INT NOT NULL CHECK (quantity > 0),
    unit_price      NUMERIC(12,2) NOT NULL,              -- price incl. variant extra
    tax_id          INT REFERENCES taxes(id),
    amount          NUMERIC(12,2) NOT NULL               -- quantity * unit_price
);

-- ========== DISCOUNTS ==========
CREATE TABLE discounts (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    type            VARCHAR(10) NOT NULL CHECK (type IN ('fixed','percent')),
    value           NUMERIC(12,2) NOT NULL CHECK (value > 0),
    min_purchase    NUMERIC(12,2) NOT NULL DEFAULT 0,
    min_quantity    INT NOT NULL DEFAULT 0,
    start_date      DATE NOT NULL,
    end_date        DATE,
    usage_limit     INT,                                 -- NULL = unlimited
    times_used      INT NOT NULL DEFAULT 0,
    product_id      INT REFERENCES products(id),         -- set for product discount
    subscription_id INT REFERENCES subscriptions(id),    -- set for subscription discount
    created_by      INT REFERENCES users(id)
);

-- ========== INVOICES ==========
CREATE TABLE invoices (
    id                   SERIAL PRIMARY KEY,
    number               VARCHAR(30) NOT NULL UNIQUE,    -- e.g. INV-0001
    subscription_id      INT NOT NULL REFERENCES subscriptions(id),
    customer_id          INT NOT NULL REFERENCES customers(id),
    billing_period_start DATE NOT NULL,
    billing_period_end   DATE NOT NULL,
    issue_date           DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date             DATE NOT NULL,
    status               VARCHAR(20) NOT NULL DEFAULT 'draft'
                         CHECK (status IN ('draft','confirmed','paid','cancelled')),
    subtotal             NUMERIC(12,2) NOT NULL DEFAULT 0,
    discount_total       NUMERIC(12,2) NOT NULL DEFAULT 0,
    tax_total            NUMERIC(12,2) NOT NULL DEFAULT 0,
    total                NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    -- nothing billed twice: one invoice per subscription per period
    UNIQUE (subscription_id, billing_period_start)
);

CREATE TABLE invoice_lines (
    id          SERIAL PRIMARY KEY,
    invoice_id  INT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    product_id  INT REFERENCES products(id),
    description VARCHAR(255) NOT NULL,
    quantity    INT NOT NULL CHECK (quantity > 0),
    unit_price  NUMERIC(12,2) NOT NULL,
    tax_id      INT REFERENCES taxes(id),
    tax_amount  NUMERIC(12,2) NOT NULL DEFAULT 0,
    amount      NUMERIC(12,2) NOT NULL
);

CREATE TABLE invoice_discounts (
    id          SERIAL PRIMARY KEY,
    invoice_id  INT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    discount_id INT NOT NULL REFERENCES discounts(id),
    amount      NUMERIC(12,2) NOT NULL
);

-- ========== PAYMENTS ==========
CREATE TABLE payments (
    id           SERIAL PRIMARY KEY,
    invoice_id   INT NOT NULL REFERENCES invoices(id),
    method       VARCHAR(30) NOT NULL CHECK (method IN ('cash','card','upi','bank_transfer','cheque')),
    amount       NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    payment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    note         TEXT,
    recorded_by  INT REFERENCES users(id)
);

-- ========== INDEXES (keep pages under 2 seconds) ==========
CREATE INDEX idx_subscriptions_status        ON subscriptions(status);
CREATE INDEX idx_subscriptions_customer      ON subscriptions(customer_id);
CREATE INDEX idx_subscriptions_next_billing  ON subscriptions(next_billing_date);
CREATE INDEX idx_invoices_status_due         ON invoices(status, due_date);
CREATE INDEX idx_invoices_customer           ON invoices(customer_id);
CREATE INDEX idx_payments_invoice            ON payments(invoice_id);
CREATE INDEX idx_payments_date               ON payments(payment_date);
CREATE INDEX idx_discounts_dates             ON discounts(start_date, end_date);