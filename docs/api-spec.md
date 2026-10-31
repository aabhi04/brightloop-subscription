# Brightloop API (Level 1)

Base URL: `/api`. Interactive docs: `/docs` (OpenAPI at `/openapi.json`).

## Conventions

- **Auth:** `Authorization: Bearer <token>`, using the token from `POST /api/auth/login` or `/signup`.
  The web UI's `access_token` cookie is accepted too.
- **Errors:** always `{ "error": "message" }`, with status `400` (business rule), `401`
  (not logged in), `403` (wrong role), `404`, `409` (duplicate or record in use) or `422`
  (invalid input).
- **Money:** decimal strings with 2 places, e.g. `"1560.00"`. Dates are `YYYY-MM-DD`.
- **Lists:** `?page=1&limit=20` (limit ≤ 100). The response is
  `{ "items": [...], "page": 1, "limit": 20, "total": 123, "pages": 7 }`.
- **Roles:** A = admin, S = staff, C = customer.

## Auth

| Method | Path | Who | Body / notes |
|---|---|---|---|
| POST | `/auth/signup` | public | `{name, email, password}`. Always creates a CUSTOMER. Returns `{token, user}`. 409 if the email exists |
| POST | `/auth/login` | public | `{email, password}` → `{token, user}` |
| POST | `/auth/forgot-password` | public | `{email}`. Same response whether or not the email exists |
| POST | `/auth/reset-password/{token}` | public | `{password}`. The token is single-use and expires |

## Users

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/users/me` | any | Current user |
| POST | `/users/staff` | A | `{name, email, password}` |
| POST | `/users/customers` | A, S | `{name, email, password}` |
| GET | `/users` | A, S | Filters: `role`, `q` (name/email). Staff only see customers |

## Catalog

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/products` | A, S | Filter `q`. Includes `variants` |
| GET | `/products/{id}` | A, S | |
| POST / PUT / DELETE | `/products`, `/products/{id}` | A | `{name, type, sales_price, cost_price, notes, variants?: [{attribute, value, extra_price}]}`. Variants are only read on create |
| GET / POST | `/products/{id}/variants` | GET A, S · POST A | `{attribute, value, extra_price}` |
| PUT / DELETE | `/products/{id}/variants/{variantId}` | A | |
| GET | `/plans` | A, S | Filters: `status`, `billing_period` |
| GET / POST / PUT / DELETE | `/plans`, `/plans/{id}` | write A | `{name, price, billing_period: DAILY\|WEEKLY\|MONTHLY\|YEARLY, min_quantity, start_date, end_date?, auto_close, closable, pausable, renewable}` |
| PATCH | `/plans/{id}/close` · `/pause` · `/renew` | A | 400 when the plan's flag forbids it |
| GET | `/taxes` | A, S | Filter `active` |
| POST / PUT / DELETE | `/taxes`, `/taxes/{id}` | A | `{name, type: PERCENT\|FIXED, rate, is_active}`. FIXED = rate per unit |
| GET / POST / PUT / DELETE | `/discounts`, `/discounts/{id}` | A | `{name, type: PERCENT\|FIXED, value, min_purchase, min_quantity, start_date, end_date, usage_limit, applies_to: PRODUCT\|SUBSCRIPTION, product_ids: []}`. Filter `active_on` |
| GET | `/quotation-templates` | A, S | |
| POST / PUT / DELETE | `/quotation-templates`, `/{id}` | A | `{name, validity_days, plan_id, lines: [{product_id, variant_id?, quantity}]}` |

## Subscriptions (A, S)

| Method | Path | Notes |
|---|---|---|
| GET | `/subscriptions` | Filters: `status`, `customer_id`, `plan_id`, `q` (number), `start_from`, `start_to` |
| GET | `/subscriptions/{id}` | Includes `lines` (with `unit_price` = sales + extra price) |
| POST | `/subscriptions` | `{customer_id, plan_id, start_date, expiry_date?, payment_terms (days), lines: [{product_id, variant_id?, quantity, tax_id?}]}` → DRAFT |
| POST | `/subscriptions/from-template/{templateId}` | `{customer_id, start_date?, payment_terms?}` → QUOTATION with expiry = today + validity_days |
| PUT / DELETE | `/subscriptions/{id}` | Only while DRAFT or QUOTATION |
| PATCH | `/subscriptions/{id}/status` | `{status}`. One step along DRAFT → QUOTATION → CONFIRMED → ACTIVE → CLOSED. Invalid moves return `400 {"error": "Invalid status change DRAFT -> ACTIVE. Allowed next status: QUOTATION"}` |

## Invoices and payments (A, S)

| Method | Path | Notes |
|---|---|---|
| GET | `/invoices` | Filters: `status`, `customer_id`, `subscription_id`, `overdue=true`, `date_from`/`date_to` (billing period start), `q`. Each item includes `balance` and `overdue` |
| GET | `/invoices/{id}` | Includes `lines` and `payments` |
| POST | `/invoices/generate-due` | Optional body `{on_date}`. Bills every due period of every ACTIVE subscription. Idempotent. Returns `{date, subscriptions_checked, invoices_created, invoice_numbers, failed_subscription_ids}` |
| PATCH | `/invoices/{id}/confirm` | DRAFT → CONFIRMED (or PAID if the total is 0) |
| PATCH | `/invoices/{id}/cancel` | DRAFT or CONFIRMED with no payments |
| PATCH | `/invoices/{id}/send` | CONFIRMED or PAID. Emails the customer (or prints to the console) and sets `sent_at` |
| POST | `/payments` | `{invoice_id, method: CASH\|CARD\|BANK_TRANSFER\|UPI, amount, payment_date?, note?}`. Partial payments are allowed; when payments reach the total the invoice becomes PAID |
| GET | `/payments` | Filters: `invoice_id`, `method`, `date_from`, `date_to` |

## Portal (C, always scoped to the logged-in customer)

| Method | Path | Notes |
|---|---|---|
| GET | `/portal/subscriptions` · `/portal/subscriptions/{id}` | Filter `status` |
| GET | `/portal/invoices` · `/portal/invoices/{id}` | DRAFT invoices are hidden. Another customer's id returns 404 |

## Reports (A, S)

| Method | Path | Notes |
|---|---|---|
| GET | `/reports/summary` | `{active_subscriptions, revenue_received, outstanding_amount, open_invoices, overdue_amount, overdue_invoices}`. Filters: `date_from`, `date_to`, `customer_id` (dates filter payment date for revenue, billing period start for outstanding/overdue) |
| GET | `/reports/active-subscriptions` | Filters: `status` (default ACTIVE), `customer_id`, `plan_id`, `date_from`, `date_to` (start date) |
| GET | `/reports/revenue` | Payments per month: `[{month: "2026-10", amount, payments}]`. Filters: `date_from`, `date_to`, `customer_id`, `method` |
| GET | `/reports/overdue` | Overdue invoices, oldest first, with `days_overdue`. Filters: `date_from`, `date_to` (due date), `customer_id` |

## Example

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"staff@brightloop.local","password":"Staff@1234"}' | python -c 'import sys,json;print(json.load(sys.stdin)["token"])')

curl -s -X POST localhost:8000/api/invoices/generate-due -H "Authorization: Bearer $TOKEN"
curl -s "localhost:8000/api/reports/overdue?page=1&limit=10" -H "Authorization: Bearer $TOKEN"
```
