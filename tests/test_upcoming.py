from datetime import date, timedelta

from app.services import report_service
from app.utils.constants import Role
from tests.conftest import PASSWORD


def test_upcoming_billing_only_lists_next_7_days(db, make_user, active_subscription):
    customer = make_user(Role.CUSTOMER)
    soon = active_subscription(customer, date.today() + timedelta(days=3))
    active_subscription(customer, date.today() + timedelta(days=30))  # too far out

    assert [s.id for s in report_service.upcoming_billing(db)] == [soon.id]


def test_admin_dashboard_shows_upcoming_billing(client, make_user, active_subscription):
    admin = make_user(Role.ADMIN)
    customer = make_user(Role.CUSTOMER)
    sub = active_subscription(customer, date.today() + timedelta(days=2))

    client.post("/login", data={"email": admin.email, "password": PASSWORD})
    page = client.get("/admin").text

    assert "Billing in the next 7 days" in page
    assert sub.number in page
