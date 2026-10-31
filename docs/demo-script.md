# Demo script (about 10 minutes)

Before you start: `python -m scripts.seed`, then
`python -m uvicorn app.main:app --reload`, and open http://localhost:8000.
Keep the server terminal visible, because emails (reset links, sent invoices) appear there.

## 1. Sign up and password rules (customer), 1 minute

1. Go to **/signup**. Type a password slowly, e.g. `abc` → `abcdefgh` → `Abcdefgh` → `Abcdefgh!`.
   The checklist ticks off each rule, and **Sign up** stays disabled until all four pass.
2. Submit with a new email. You land on **My subscriptions**, and the account is a CUSTOMER.
3. Sign up again with the same email: "Email is already registered".
4. Log out. Open **Forgot password?** and enter `priya@example.com`. Copy the reset link from the
   server console, open it, and set a new password.

## 2. Admin configuration, 3 minutes

Log in as `admin@brightloop.local` / `Admin@1234`.

1. **Dashboard:** stat cards for active subscriptions, revenue, outstanding and overdue, plus counts
   by status.
2. **Products:** ERP Suite has **Brand: Odoo +560 → 1,560.00**. Add a variant to any product inline.
3. **Plans:** "Yearly Pro" is not pausable, so it has no Pause button (the API returns 400). Pause
   "Weekly Flex", then **Renew** it; the end date moves out by one week.
4. **Taxes:** GST 18% (percent) and Service Levy 25 per unit (fixed).
5. **Discounts:** "Welcome 10%" is a subscription-level discount with min purchase 500. Note its
   **Used** count.
6. **Quotation templates:** "ERP Starter Pack" uses Monthly Standard, is valid 30 days, and contains
   ERP (Odoo) plus Support Desk.
7. **Staff:** create a staff user and watch the same live password checklist.

## 3. Subscription lifecycle (staff), 2 minutes

Log in as `staff@brightloop.local` / `Staff@1234`. The admin pages aren't in the sidebar, and
opening `/admin` sends you back with "You do not have access to that page".

1. **Subscriptions → Create a quotation from a template:** pick ERP Starter Pack and Rahul. It opens
   as **QUOTATION** with the lines copied and the expiry 30 days out.
2. Click **Edit** and add GST to the ERP line. Unit prices are filled in by the server.
3. Click **Confirm**, then **Activate**. The lifecycle bar moves each time, and *Next billing* is set
   to the start date.
4. Show an invalid move through the API (`/docs`, or PowerShell):
   `PATCH /api/subscriptions/{id}/status {"status":"DRAFT"}` → `400` "Invalid status change
   ACTIVE -> DRAFT. Allowed next status: CLOSED".

## 4. Billing, discounts and taxes, 2 minutes

1. **Invoices → Generate due invoices.** The message says *1 invoice(s) created*.
2. Click it again: *0 invoice(s) created*. The run is idempotent.
3. Open the new DRAFT invoice. Each line shows the unit price, the **Welcome 10%** discount, tax on
   the discounted amount, and totals. The plan's base fee is its own line.
4. **Confirm** it, then **Send to customer**. The email shows up in the server console.
5. Record a **partial payment** (e.g. 1000, UPI). The status stays CONFIRMED and the balance drops.
   Then record the remaining balance and the status becomes **PAID**.
6. Click **Print** to get a clean, print-friendly invoice.

## 5. Overdue and reports, 1 minute

1. **Reports:** the summary cards, then the overdue table. INV-0002 (Priya, partly paid, due about
   two weeks ago) is listed with its days overdue.
2. Filter by customer = Priya and a date range. The cards and tables update, and pagination appears
   once there is more than one page.
3. **Invoices → Overdue only** shows the same invoice, with an OVERDUE badge.

## 6. Customer portal, 1 minute

Log in as `priya@example.com` / `Customer@1` (or the new password from step 1).

1. **My subscriptions:** Priya's subscriptions only, including the quotation and its expiry date.
2. **My invoices:** confirmed, paid and cancelled invoices only (drafts are hidden). Open one and
   print it.
3. Change the URL to another customer's invoice, e.g. `/portal/invoices/4` (Rahul's): **404**.

## 7. Under the hood (optional)

- `python -m pytest`: 38 tests covering password rules, duplicate signup, running generate-due
  twice, catch-up billing, discount limits and expiry, staff 403s, and customer isolation.
- The schema has `UNIQUE(subscription_id, billing_period_start)` on `invoices`, so the database
  itself refuses double billing.
