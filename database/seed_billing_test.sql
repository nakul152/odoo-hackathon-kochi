-- ========== BILLING TEST DATA (safe to run more than once) ==========

-- ---- Step 1: remove earlier test rows (this one and the previous version) ----
DELETE FROM invoice_discounts WHERE invoice_id IN (
    SELECT id FROM invoices WHERE subscription_id IN (
        SELECT id FROM subscriptions WHERE number LIKE 'TST-%' OR number IN ('SUB-0001','SUB-0002','SUB-0003')));
DELETE FROM invoice_lines WHERE invoice_id IN (
    SELECT id FROM invoices WHERE subscription_id IN (
        SELECT id FROM subscriptions WHERE number LIKE 'TST-%' OR number IN ('SUB-0001','SUB-0002','SUB-0003')));
DELETE FROM payments WHERE invoice_id IN (
    SELECT id FROM invoices WHERE subscription_id IN (
        SELECT id FROM subscriptions WHERE number LIKE 'TST-%' OR number IN ('SUB-0001','SUB-0002','SUB-0003')));
DELETE FROM invoices WHERE subscription_id IN (
    SELECT id FROM subscriptions WHERE number LIKE 'TST-%' OR number IN ('SUB-0001','SUB-0002','SUB-0003'));
DELETE FROM discounts WHERE name LIKE 'TEST %' OR name IN ('Seat bulk 10%', 'Loyalty 500 off');
DELETE FROM subscription_lines WHERE subscription_id IN (
    SELECT id FROM subscriptions WHERE number LIKE 'TST-%' OR number IN ('SUB-0001','SUB-0002','SUB-0003'));
DELETE FROM subscriptions WHERE number LIKE 'TST-%' OR number IN ('SUB-0001','SUB-0002','SUB-0003');
DELETE FROM customers WHERE name LIKE 'TEST %' OR name IN ('Asha Traders', 'Bright Corp');
DELETE FROM product_variants WHERE product_id IN (SELECT id FROM products WHERE name LIKE 'TEST %');
DELETE FROM products WHERE name LIKE 'TEST %';
DELETE FROM plans WHERE name LIKE 'TEST %';
DELETE FROM taxes WHERE name LIKE 'TEST %';

-- ---- Step 2: create fresh test data with unique names ----
INSERT INTO taxes (name, rate) VALUES ('TEST GST 18%', 18.00), ('TEST GST 5%', 5.00);

INSERT INTO customers (name, company, email) VALUES
  ('TEST Asha Traders', 'Asha Traders', 'asha@example.com'),
  ('TEST Bright Corp', 'Bright Corp Pvt Ltd', 'accounts@brightcorp.example');

INSERT INTO products (name, type, sales_price, cost_price, tax_id) VALUES
  ('TEST Odoo ERP Suite', 'software', 2000, 1200, (SELECT id FROM taxes WHERE name = 'TEST GST 18%')),
  ('TEST Extra User Seat', 'add-on', 300, 100, (SELECT id FROM taxes WHERE name = 'TEST GST 18%'));

INSERT INTO product_variants (product_id, attribute, value, extra_price) VALUES
  ((SELECT id FROM products WHERE name = 'TEST Odoo ERP Suite'), 'Brand', 'Odoo', 560);

INSERT INTO plans (name, price, billing_period, start_date) VALUES
  ('TEST Monthly Business', 2000, 'monthly', CURRENT_DATE - 90),
  ('TEST Yearly Enterprise', 20000, 'yearly', CURRENT_DATE - 400);

INSERT INTO subscriptions (number, customer_id, plan_id, start_date, payment_terms, status, next_billing_date) VALUES
  ('TST-0001', (SELECT id FROM customers WHERE name = 'TEST Asha Traders'),
   (SELECT id FROM plans WHERE name = 'TEST Monthly Business'),
   CURRENT_DATE - 30, 'Net 15', 'active', CURRENT_DATE),
  ('TST-0002', (SELECT id FROM customers WHERE name = 'TEST Bright Corp'),
   (SELECT id FROM plans WHERE name = 'TEST Yearly Enterprise'),
   CURRENT_DATE - 365, 'Net 30', 'active', CURRENT_DATE - 1),
  ('TST-0003', (SELECT id FROM customers WHERE name = 'TEST Asha Traders'),
   (SELECT id FROM plans WHERE name = 'TEST Monthly Business'),
   CURRENT_DATE, 'Net 15', 'active', CURRENT_DATE + 20);

-- Lines (the Odoo brand variant makes the price 2000 + 560 = 2560)
INSERT INTO subscription_lines (subscription_id, product_id, variant_id, quantity, unit_price, tax_id, amount) VALUES
  ((SELECT id FROM subscriptions WHERE number = 'TST-0001'),
   (SELECT id FROM products WHERE name = 'TEST Odoo ERP Suite'),
   (SELECT id FROM product_variants WHERE value = 'Odoo'
      AND product_id = (SELECT id FROM products WHERE name = 'TEST Odoo ERP Suite')),
   1, 2560, (SELECT id FROM taxes WHERE name = 'TEST GST 18%'), 2560),
  ((SELECT id FROM subscriptions WHERE number = 'TST-0001'),
   (SELECT id FROM products WHERE name = 'TEST Extra User Seat'), NULL,
   5, 300, (SELECT id FROM taxes WHERE name = 'TEST GST 18%'), 1500),
  ((SELECT id FROM subscriptions WHERE number = 'TST-0002'),
   (SELECT id FROM products WHERE name = 'TEST Odoo ERP Suite'),
   (SELECT id FROM product_variants WHERE value = 'Odoo'
      AND product_id = (SELECT id FROM products WHERE name = 'TEST Odoo ERP Suite')),
   2, 2560, (SELECT id FROM taxes WHERE name = 'TEST GST 18%'), 5120),
  ((SELECT id FROM subscriptions WHERE number = 'TST-0003'),
   (SELECT id FROM products WHERE name = 'TEST Extra User Seat'), NULL,
   1, 300, (SELECT id FROM taxes WHERE name = 'TEST GST 18%'), 300);

-- Discount 1: 10% on the Extra User Seat when buying 5 or more
INSERT INTO discounts (name, type, value, min_quantity, start_date, end_date, product_id)
VALUES ('TEST Seat bulk 10%', 'percent', 10, 5, CURRENT_DATE - 30, CURRENT_DATE + 365,
        (SELECT id FROM products WHERE name = 'TEST Extra User Seat'));

-- Discount 2: fixed 500 off TST-0002, usable only once
INSERT INTO discounts (name, type, value, start_date, end_date, usage_limit, subscription_id)
VALUES ('TEST Loyalty 500 off', 'fixed', 500, CURRENT_DATE - 30, CURRENT_DATE + 365, 1,
        (SELECT id FROM subscriptions WHERE number = 'TST-0002'));