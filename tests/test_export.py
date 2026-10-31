from datetime import date

from app.services import billing_service
from app.utils.constants import Role
from tests.conftest import PASSWORD


def test_staff_can_export_filtered_invoices_csv(client, db, make_user, active_subscription):
    staff = make_user(Role.STAFF)
    customer = make_user(Role.CUSTOMER)
    active_subscription(customer, date.today())
    billing_service.generate_due_invoices(db)

    client.post("/login", data={"email": staff.email, "password": PASSWORD})
    r = client.get("/invoices/export.csv?status=DRAFT")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("Number,Customer")
    assert len(lines) == 2 and "INV-0001" in lines[1]


def test_customer_cannot_export_invoices(client, make_user):
    customer = make_user(Role.CUSTOMER)
    client.post("/login", data={"email": customer.email, "password": PASSWORD})
    r = client.get("/invoices/export.csv", follow_redirects=False)
    assert r.status_code == 303  # redirected to their portal
