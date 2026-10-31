# Brightloop Subscription Management (Level 1)

A full-stack subscription management system: products with variants, recurring plans, quotation
templates, a subscription lifecycle, automatic invoicing with taxes and discounts, partial payments,
overdue tracking, a customer portal and reports.

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL
- **Auth:** JWT (PyJWT) + bcrypt; Bearer header for the API, HttpOnly cookie for the web UI
- **UI:** server-rendered Jinja2 templates + Tailwind (CDN) + a little vanilla JS
- **Scheduler:** APScheduler (daily billing and plan auto-close)
- **Tests:** pytest + FastAPI TestClient

## Quick start

> On Windows, run commands through the venv's interpreter (`.venv\Scripts\python.exe -m ...`).
> Some machines block the venv's `.exe` launchers (e.g. `alembic.exe`), and `python -m` always works.

```powershell
# 1. Database (pick one)
docker compose up -d                       # Postgres 17 on localhost:5432, creates brightloop + brightloop_test
# or use a local PostgreSQL and create the two databases yourself:
#   CREATE DATABASE brightloop;  CREATE DATABASE brightloop_test;

# 2. Python environment
py -3.11 -m venv .venv                     # macOS/Linux: python3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. Configuration
Copy-Item .env.example .env                # macOS/Linux: cp .env.example .env
# then set JWT_SECRET to a random string of 32+ characters

# 4. Schema and demo data
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.seed      # WARNING: wipes all tables first

# 5. Run
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000**. The interactive API docs are at **http://localhost:8000/docs**: use
**Authorize** and paste a token from `POST /api/auth/login`.

On macOS/Linux replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.

### Run the tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Tests use the `brightloop_test` database (`TEST_DATABASE_URL`). They recreate its tables and
truncate them before every test, so never point it at real data.

## Seed credentials

| Role     | Email                    | Password     |
|----------|--------------------------|--------------|
| Admin    | admin@brightloop.local   | `Admin@1234` |
| Staff    | staff@brightloop.local   | `Staff@1234` |
| Customer | priya@example.com        | `Customer@1` |
| Customer | rahul@example.com        | `Customer@2` |

The seed creates 3 products with variants (including **Brand: Odoo +560**), monthly, yearly and
weekly plans, 2 taxes, an active 10% discount and a quotation template. It also creates 6
subscriptions covering every status, and 8 invoices (draft, confirmed, paid, cancelled and one
**overdue**) with payments. Dates are relative to the day you run it.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/brightloop` | App database |
| `TEST_DATABASE_URL` | `.../brightloop_test` | Database used by pytest |
| `JWT_SECRET` | dev placeholder | Signing key for tokens. **Set this.** 32+ characters |
| `JWT_EXPIRES_MINUTES` | `720` | Login lifetime |
| `RESET_TOKEN_EXPIRES_MINUTES` | `60` | Password reset link lifetime |
| `APP_URL` | `http://localhost:8000` | Used to build reset links |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | empty | Optional SMTP. When `SMTP_HOST` is empty, emails (reset links, sent invoices) are printed to the server console |
| `ENABLE_SCHEDULER` | `true` | Run the daily jobs inside the web process |

## Roles

| | Admin | Staff | Customer |
|---|---|---|---|
| Products, plans, taxes, discounts, quotation templates, staff users | ✅ manage | read products/plans/taxes/templates (needed to build subscriptions) | ❌ |
| Customers, subscriptions, invoices, payments, reports | ✅ | ✅ | ❌ |
| Portal (own subscriptions and non-draft invoices only) | | | ✅ |

Public signup always creates a **CUSTOMER**. Staff are created by an admin. Customers can also be
created by staff.

## Business rules (how they are implemented)

- **Passwords:** more than 8 characters, with at least one uppercase letter, one lowercase letter and
  one special character. Enforced in `app/validators/password.py`, and in the browser by a live
  checklist (`app/static/app.js`) that mirrors it.
- **Forgot password:** a random token is emailed (or printed). Only its SHA-256 hash is stored, with
  an expiry, and it can be used once.
- **Variant pricing:** unit price = product sales price + variant extra price. It is fixed on the
  subscription line when the line is created.
- **Plans:** close, pause and renew are each allowed only if the plan's flag permits it. Renew
  reactivates the plan and extends `end_date` by one period. The daily job closes `auto_close` plans
  whose end date has passed. Subscriptions on a **paused** plan are not billed until the plan is
  renewed.
- **Subscription lifecycle:** `DRAFT → QUOTATION → CONFIRMED → ACTIVE → CLOSED`, one step at a time.
  Any other move returns `400` with the allowed next status. Confirming checks that there are lines,
  the plan's minimum quantity is met, the quotation hasn't expired and the plan is active.
  Activating sets `next_billing_date = start_date`. Closing requires a closable plan. Only DRAFT and
  QUOTATION subscriptions can be edited or deleted. Creating from a template copies the plan and
  lines, sets `expiry_date = today + validity_days`, and starts at **QUOTATION**.
- **Billing** (`app/services/billing_service.py`): `POST /api/invoices/generate-due` and the daily
  job both call `generate_due_invoices`. For each ACTIVE subscription due today it locks the row
  (`SELECT … FOR UPDATE`) and bills **every** missed period. Each period gets its own DRAFT invoice
  in the same transaction, then `next_billing_date` advances. Monthly and yearly periods are anchored
  on the start date (Jan 31 → Feb 28 → Mar 31), so they never drift. Duplicates are prevented three
  ways: the row lock, an existence check, and `UNIQUE(subscription_id, billing_period_start)`.
- **Invoice lines:** a plan base-fee line (when the plan price is above 0), plus one line per
  subscription line.
- **Tax:** per line, from the line's tax. PERCENT applies to the line's net amount after discounts;
  FIXED is the rate per unit. Inactive taxes add nothing.
- **Discounts:** applied automatically when today is between the start and end dates, `used_count` is
  below `usage_limit`, and `min_purchase` and `min_quantity` are met.
  - PRODUCT discounts apply to matching lines. Each line gets the best eligible one, and line
    gross/quantity are checked against the minimums.
  - SUBSCRIPTION discounts: the single best eligible one is spread across lines in proportion to
    their amounts, so tax is charged on the discounted amounts.
  - `used_count` goes up by one for each invoice that uses the discount. Discount rows are locked
    during billing, so the limit holds under concurrency.
- **Invoice lifecycle:** `DRAFT → CONFIRMED → PAID`. Staff can confirm, cancel (DRAFT or CONFIRMED
  with no payments) and send (CONFIRMED or PAID: emailed, or printed to the console). There is no PDF;
  the invoice page is print-friendly and has a Print button (`window.print()`).
- **Payments:** CASH, CARD, BANK_TRANSFER or UPI, with partial payments allowed. Paying a DRAFT,
  PAID or CANCELLED invoice, or paying more than the balance, is rejected. Once payments add up to
  the total, the invoice becomes **PAID**.
- **Overdue:** status CONFIRMED, `amount_paid < total` and `due_date < today`, where `due_date` is the
  period start plus the subscription's payment terms in days.
- **Reports:** SQL aggregates only (`COUNT`, `SUM`, `GROUP BY`), backed by indexes on invoice
  status, due date, customer, the `(status, due_date)` pair, subscription status, next billing date
  and payment invoice. With 100k invoices, 20k subscriptions and 50k payments, every list and report
  endpoint answers in under 120 ms and the heaviest page (`/reports`) renders in about 0.3 s.

## Project layout

```
app/
  main.py            app factory, error handlers ({ "error": "..." } for /api, HTML pages otherwise)
  config.py db.py    settings from .env, engine/session
  models.py          SQLAlchemy models (tables, constraints, indexes)
  schemas/           Pydantic request/response models
  deps/auth.py       JWT from Bearer header or cookie; role guards for the API
  api/               REST routers, one per area (mounted under /api)
  services/          business logic: auth, subscription, plan, billing, invoice, tax, discount, payment, report
  jobs/              scheduler + billing_job + renewal_job
  validators/        password rules
  utils/             constants, dates, money, numbering (SUB-0001/INV-0001), pagination, errors
  web/               HTML page routers (auth, admin, staff, portal) and page guards
  templates/         Jinja2 pages and shared components (sidebar, table, badges, filters, pagination, modal)
  static/app.js      confirm modal, live password checklist, subscription line editor
alembic/             migrations
scripts/seed.py      demo data
tests/               pytest suite
docs/                api-spec.md, demo-script.md
```

## Out of scope for Level 1

PDF generation, payment gateways, refunds, multi-currency, rich email templates, dark mode, i18n.
The Tailwind Play CDN is fine for Level 1 but should be swapped for a compiled stylesheet in production.
