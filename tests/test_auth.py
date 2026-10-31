from datetime import date

import pytest
from sqlalchemy import select

from app.models import Invoice
from app.services import billing_service, invoice_service
from app.utils.constants import Role
from app.validators.password import is_valid_password, password_errors
from tests.conftest import PASSWORD, auth


# ---------- Password rules ----------
@pytest.mark.parametrize(
    "password",
    [
        "",
        "Ab#defgh",  # exactly 8 characters: must be MORE than 8
        "abcdefgh#1",  # no uppercase
        "ABCDEFGH#1",  # no lowercase
        "Abcdefghi1",  # no special character
        "Short#1",
    ],
)
def test_weak_passwords_are_rejected(password):
    assert not is_valid_password(password)
    assert password_errors(password)


def test_valid_password_is_accepted():
    assert is_valid_password("Abcdefgh#")  # 9 chars, upper, lower, special
    assert password_errors(PASSWORD) == []


def test_signup_rejects_weak_password(client):
    r = client.post("/api/auth/signup", json={"name": "A", "email": "a@test.local", "password": "weakpass"})
    assert r.status_code == 400
    assert "error" in r.json()
    assert "uppercase" in r.json()["error"]


def test_signup_always_creates_customer(client):
    r = client.post(
        "/api/auth/signup",
        json={"name": "A", "email": "a@test.local", "password": PASSWORD, "role": "ADMIN"},
    )
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "CUSTOMER"
    assert r.json()["token"]


# ---------- Duplicate email ----------
def test_duplicate_email_signup_is_rejected(client):
    body = {"name": "A", "email": "dup@test.local", "password": PASSWORD}
    assert client.post("/api/auth/signup", json=body).status_code == 201
    r = client.post("/api/auth/signup", json={**body, "email": "DUP@test.local"})
    assert r.status_code == 409
    assert r.json() == {"error": "Email is already registered"}


def test_login_and_me(client, make_user):
    user = make_user(Role.STAFF)
    r = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert r.status_code == 200
    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert me.json()["role"] == "STAFF"
    assert client.post("/api/auth/login", json={"email": user.email, "password": "Wrong#Pass1"}).status_code == 401


def test_password_reset_flow(client, make_user, db, capsys):
    user = make_user(Role.CUSTOMER)
    assert client.post("/api/auth/forgot-password", json={"email": user.email}).status_code == 200
    link = [line for line in capsys.readouterr().out.splitlines() if "/reset-password/" in line][0]
    token = link.rsplit("/", 1)[1].strip()
    assert client.post(f"/api/auth/reset-password/{token}", json={"password": "weak"}).status_code == 400
    assert client.post(f"/api/auth/reset-password/{token}", json={"password": "New#Password9"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": user.email, "password": "New#Password9"}).status_code == 200
    # Token is single use
    assert client.post(f"/api/auth/reset-password/{token}", json={"password": "Other#Pass99"}).status_code == 400


# ---------- Role guards ----------
ADMIN_ONLY_REQUESTS = [
    ("post", "/api/users/staff", {"name": "S", "email": "s2@test.local", "password": PASSWORD}),
    ("post", "/api/products", {"name": "P", "sales_price": "10"}),
    ("post", "/api/plans", {"name": "P", "billing_period": "MONTHLY", "start_date": "2026-01-01"}),
    ("post", "/api/taxes", {"name": "T", "type": "PERCENT", "rate": "5"}),
    ("get", "/api/discounts", None),
    ("post", "/api/discounts", {"name": "D", "type": "FIXED", "value": "5", "start_date": "2026-01-01",
                                "end_date": "2026-12-31", "usage_limit": 1, "applies_to": "SUBSCRIPTION"}),
    ("post", "/api/quotation-templates", {"name": "T", "validity_days": 5, "plan_id": 1,
                                          "lines": [{"product_id": 1, "quantity": 1}]}),
    ("patch", "/api/plans/1/close", None),
]


@pytest.mark.parametrize("method,url,body", ADMIN_ONLY_REQUESTS)
def test_staff_gets_403_on_admin_only_routes(client, make_user, method, url, body):
    staff = make_user(Role.STAFF)
    kwargs = {"headers": auth(staff)}
    if body is not None:
        kwargs["json"] = body
    r = getattr(client, method)(url, **kwargs)
    assert r.status_code == 403
    assert r.json() == {"error": "You do not have permission to do this"}


def test_admin_can_use_admin_routes(client, make_user):
    admin = make_user(Role.ADMIN)
    r = client.post("/api/taxes", headers=auth(admin), json={"name": "T", "type": "PERCENT", "rate": "5"})
    assert r.status_code == 201


def test_unauthenticated_requests_get_401(client):
    r = client.get("/api/subscriptions")
    assert r.status_code == 401
    assert r.json() == {"error": "Authentication required"}


def test_staff_admin_pages_redirect_in_web_ui(client, make_user):
    staff = make_user(Role.STAFF)
    client.post("/login", data={"email": staff.email, "password": PASSWORD})
    r = client.get("/admin/products", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/subscriptions")


# ---------- Customer isolation ----------
def test_customer_cannot_see_another_customers_invoices(client, db, make_user, active_subscription):
    alice = make_user(Role.CUSTOMER)
    bob = make_user(Role.CUSTOMER)
    active_subscription(alice, date.today())
    active_subscription(bob, date.today())
    billing_service.generate_due_invoices(db)
    for invoice_id in db.scalars(select(Invoice.id)).all():
        invoice_service.confirm_invoice(db, invoice_id)
    bob_invoice = db.scalars(select(Invoice).where(Invoice.customer_id == bob.id)).one()

    r = client.get("/api/portal/invoices", headers=auth(alice))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert all(i["customer"]["id"] == alice.id for i in items)

    assert client.get(f"/api/portal/invoices/{bob_invoice.id}", headers=auth(alice)).status_code == 404
    # Customers cannot use the staff endpoints either, even with a customer_id filter
    assert client.get(f"/api/invoices?customer_id={bob.id}", headers=auth(alice)).status_code == 403
    assert client.get(f"/api/invoices/{bob_invoice.id}", headers=auth(alice)).status_code == 403
