import itertools
import os

# Point the app at the test database before anything imports app.config.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/brightloop_test"
)
os.environ["ENABLE_SCHEDULER"] = "false"

from datetime import date  # noqa: E402
from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Plan, Product, ProductVariant, Tax  # noqa: E402
from app.services import subscription_service  # noqa: E402
from app.services.auth_service import create_token, create_user  # noqa: E402
from app.utils.constants import BillingPeriod, Role, SubscriptionStatus, TaxType  # noqa: E402

PASSWORD = "Valid#Pass1"


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def make_user(db):
    counter = itertools.count(1)

    def _make(role: Role, email: str | None = None):
        email = email or f"{role.value.lower()}{next(counter)}@test.local"
        user = create_user(db, role.value.title(), email, PASSWORD, role)
        db.commit()
        return user

    return _make


def auth(user) -> dict:
    return {"Authorization": f"Bearer {create_token(user)}"}


@pytest.fixture
def catalog(db):
    """One product with an Odoo variant (+560), an 18% tax and a monthly plan."""
    product = Product(
        name="ERP Suite", sales_price=Decimal("1000"),
        variants=[ProductVariant(attribute="Brand", value="Odoo", extra_price=Decimal("560"))],
    )
    other = Product(name="Hosting", sales_price=Decimal("500"))
    tax = Tax(name="GST 18%", type=TaxType.PERCENT, rate=Decimal("18"))
    plan = Plan(name="Monthly", price=Decimal("0"), billing_period=BillingPeriod.MONTHLY, start_date=date(2020, 1, 1))
    db.add_all([product, other, tax, plan])
    db.commit()
    return {"product": product, "variant": product.variants[0], "other": other, "tax": tax, "plan": plan}


@pytest.fixture
def active_subscription(db, catalog):
    """Factory: an ACTIVE subscription for `customer` starting on `start`."""

    def _make(customer, start: date, quantity: int = 1, with_variant: bool = True, product=None, plan=None):
        product = product or catalog["product"]
        sub = subscription_service.create_subscription(
            db, customer_id=customer.id, plan_id=(plan or catalog["plan"]).id, start_date=start,
            expiry_date=None, payment_terms=15,
            lines=[{
                "product_id": product.id,
                "variant_id": catalog["variant"].id if with_variant and product is catalog["product"] else None,
                "quantity": quantity,
                "tax_id": catalog["tax"].id,
            }],
        )
        for status in (SubscriptionStatus.QUOTATION, SubscriptionStatus.CONFIRMED, SubscriptionStatus.ACTIVE):
            sub = subscription_service.change_status(db, sub.id, status)
        return sub

    return _make
