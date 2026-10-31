from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Payment, Plan, Product, QuotationTemplate, Tax, User
from app.schemas.subscription import SubscriptionIn
from app.services import (
    auth_service,
    billing_service,
    invoice_service,
    payment_service,
    report_service,
    subscription_service,
)
from app.utils.constants import (
    SUBSCRIPTION_TRANSITIONS,
    InvoiceStatus,
    PaymentMethod,
    PlanStatus,
    Role,
    SubscriptionStatus,
)
from app.utils.dates import today
from app.utils.errors import AppError, NotFound
from app.utils.money import money
from app.utils.pagination import PageParams, paginate
from app.web.common import (
    PASSWORD_RULES,
    STAFF_PAGE,
    date_or_none,
    enum_or_none,
    int_or_none,
    lines_from_form,
    page_args,
    parse,
    render,
    run_action,
)

router = APIRouter()

STATUS_OPTIONS = {
    "subscription_statuses": [(s.value, s.value.title()) for s in SubscriptionStatus],
    "invoice_statuses": [(s.value, s.value.title()) for s in InvoiceStatus],
    "payment_methods": [(m.value, m.value.replace("_", " ").title()) for m in PaymentMethod],
}


def _customers(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.role == Role.CUSTOMER).order_by(User.name)))


def _customer_options(db: Session) -> list[tuple]:
    return [(c.id, f"{c.name} ({c.email})") for c in _customers(db)]


# ---------- Customers ----------
@router.get("/customers")
def customers_page(request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    q = request.query_params.get("q") or ""
    stmt = select(User).where(User.role == Role.CUSTOMER).order_by(User.id.desc())
    if q:
        stmt = stmt.where(or_(User.name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    page = paginate(db, stmt, page_args(request))
    return render(request, "staff/customers.html", user, page=page, q=q, password_rules=PASSWORD_RULES)


@router.post("/customers")
async def create_customer(request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        auth_service.create_user(db, form.get("name", ""), form.get("email", ""), form.get("password", ""), Role.CUSTOMER)
        db.commit()

    return run_action(db, action, "/customers", "Customer created", "/customers")


# ---------- Subscriptions ----------
@router.get("/subscriptions")
def subscriptions_page(request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    qp = request.query_params
    filters = {
        "status": enum_or_none(SubscriptionStatus, qp.get("status")),
        "customer_id": int_or_none(qp.get("customer_id")),
        "q": qp.get("q") or None,
    }
    page = paginate(db, subscription_service.subscription_list_query(**filters), page_args(request))
    templates_ = db.scalars(select(QuotationTemplate).order_by(QuotationTemplate.name)).all()
    return render(
        request, "staff/subscriptions.html", user, page=page, filters=qp,
        customers=_customer_options(db), templates_=templates_, **STATUS_OPTIONS,
    )


def _form_context(db: Session) -> dict:
    return {
        "customers": _customer_options(db),
        "plans": db.scalars(select(Plan).where(Plan.status != PlanStatus.CLOSED).order_by(Plan.name)).all(),
        "products": db.scalars(select(Product).options(selectinload(Product.variants)).order_by(Product.name)).all(),
        "taxes": db.scalars(select(Tax).where(Tax.is_active.is_(True)).order_by(Tax.name)).all(),
    }


def _subscription_data(form) -> dict:
    data = parse(SubscriptionIn, {
        "customer_id": form.get("customer_id") or 0,
        "plan_id": form.get("plan_id") or 0,
        "start_date": form.get("start_date"),
        "expiry_date": form.get("expiry_date") or None,
        "payment_terms": form.get("payment_terms") or 15,
        "lines": lines_from_form(form),
    })
    return data.model_dump()


@router.get("/subscriptions/new")
def new_subscription_page(request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    return render(request, "staff/subscription_form.html", user, sub=None, today=today(), **_form_context(db))


@router.post("/subscriptions")
async def create_subscription(request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    form = await request.form()
    return run_action(
        db,
        lambda: subscription_service.create_subscription(db, **_subscription_data(form)),
        lambda sub: f"/subscriptions/{sub.id}",
        "Subscription created as DRAFT",
        "/subscriptions/new",
    )


@router.post("/subscriptions/from-template")
async def create_from_template(request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        template_id, customer_id = int_or_none(form.get("template_id")), int_or_none(form.get("customer_id"))
        if not template_id or not customer_id:
            raise AppError("Choose a template and a customer")
        return subscription_service.create_from_template(db, template_id, customer_id, date_or_none(form.get("start_date")))

    return run_action(db, action, lambda sub: f"/subscriptions/{sub.id}", "Quotation created from template", "/subscriptions")


@router.get("/subscriptions/{subscription_id}")
def subscription_detail(subscription_id: int, request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    sub = subscription_service.get_subscription(db, subscription_id)
    invoices = paginate(db, invoice_service.invoice_list_query(subscription_id=sub.id), page_args(request, 10))
    lifecycle = [s for s in SubscriptionStatus]
    next_steps = sorted(SUBSCRIPTION_TRANSITIONS[sub.status], key=lambda s: lifecycle.index(s))
    return render(
        request, "staff/subscription_detail.html", user, sub=sub, invoices=invoices,
        lifecycle=lifecycle, next_steps=next_steps, editable=sub.status in subscription_service.EDITABLE_STATUSES,
        is_overdue=invoice_service.is_overdue,
    )


@router.get("/subscriptions/{subscription_id}/edit")
def edit_subscription_page(subscription_id: int, request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    sub = subscription_service.get_subscription(db, subscription_id)
    return render(request, "staff/subscription_form.html", user, sub=sub, today=today(), **_form_context(db))


@router.post("/subscriptions/{subscription_id}")
async def update_subscription(subscription_id: int, request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    form = await request.form()
    return run_action(
        db,
        lambda: subscription_service.update_subscription(db, subscription_id, **_subscription_data(form)),
        f"/subscriptions/{subscription_id}",
        "Subscription updated",
        f"/subscriptions/{subscription_id}/edit",
    )


@router.post("/subscriptions/{subscription_id}/status")
async def change_subscription_status(subscription_id: int, request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        status = enum_or_none(SubscriptionStatus, form.get("status"))
        if not status:
            raise AppError("Unknown status")
        return subscription_service.change_status(db, subscription_id, status)

    url = f"/subscriptions/{subscription_id}"
    return run_action(db, action, url, f"Status changed to {form.get('status')}", url)


@router.post("/subscriptions/{subscription_id}/delete")
def delete_subscription(subscription_id: int, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    return run_action(
        db,
        lambda: subscription_service.delete_subscription(db, subscription_id),
        "/subscriptions",
        "Subscription deleted",
        f"/subscriptions/{subscription_id}",
    )


# ---------- Invoices ----------
def _invoice_filters(qp) -> dict:
    return {
        "status": enum_or_none(InvoiceStatus, qp.get("status")),
        "customer_id": int_or_none(qp.get("customer_id")),
        "overdue": qp.get("overdue") == "1",
        "date_from": date_or_none(qp.get("date_from")),
        "date_to": date_or_none(qp.get("date_to")),
        "q": qp.get("q") or None,
    }


@router.get("/invoices")
def invoices_page(request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    page = paginate(db, invoice_service.invoice_list_query(**_invoice_filters(request.query_params)), page_args(request))
    return render(
        request, "staff/invoices.html", user, page=page, filters=request.query_params,
        customers=_customer_options(db), is_overdue=invoice_service.is_overdue, **STATUS_OPTIONS,
    )


@router.post("/invoices/generate-due")
def generate_due(user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    result = billing_service.generate_due_invoices(db)
    msg = f"Billing run complete: {result['invoices_created']} invoice(s) created"
    if result["failed_subscription_ids"]:
        msg += f"; failed for subscriptions {result['failed_subscription_ids']} (see server log)"
    return run_action(db, lambda: None, "/invoices", msg, "/invoices")


@router.get("/invoices/{invoice_id}")
def invoice_detail(invoice_id: int, request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    invoice = invoice_service.get_invoice(db, invoice_id)
    return render(
        request, "staff/invoice_detail.html", user, invoice=invoice, overdue=invoice_service.is_overdue(invoice),
        today=today(), staff_view=True, **STATUS_OPTIONS,
    )


@router.post("/invoices/{invoice_id}/{verb}")
def invoice_action(invoice_id: int, verb: str, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    actions = {
        "confirm": (invoice_service.confirm_invoice, "Invoice confirmed"),
        "cancel": (invoice_service.cancel_invoice, "Invoice cancelled"),
        "send": (invoice_service.send_invoice, "Invoice sent to the customer"),
    }
    url = f"/invoices/{invoice_id}"
    if verb not in actions:
        raise NotFound("Action")
    fn, message = actions[verb]
    return run_action(db, lambda: fn(db, invoice_id), url, message, url)


# ---------- Payments ----------
@router.post("/payments")
async def record_payment(request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    form = await request.form()
    invoice_id = int_or_none(form.get("invoice_id")) or 0
    url = f"/invoices/{invoice_id}"

    def action():
        method = enum_or_none(PaymentMethod, form.get("method"))
        if not method:
            raise AppError("Choose a payment method")
        try:
            amount = money(form.get("amount") or "0")
        except Exception:
            raise AppError("Enter a valid amount")
        return payment_service.record_payment(
            db, invoice_id=invoice_id, method=method, amount=amount,
            payment_date=date_or_none(form.get("payment_date")) or today(), note=form.get("note") or None,
        )

    return run_action(db, action, url, "Payment recorded", url)


@router.get("/payments")
def payments_page(request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    qp = request.query_params
    stmt = select(Payment).options(selectinload(Payment.invoice)).order_by(Payment.payment_date.desc(), Payment.id.desc())
    if method := enum_or_none(PaymentMethod, qp.get("method")):
        stmt = stmt.where(Payment.method == method)
    if date_from := date_or_none(qp.get("date_from")):
        stmt = stmt.where(Payment.payment_date >= date_from)
    if date_to := date_or_none(qp.get("date_to")):
        stmt = stmt.where(Payment.payment_date <= date_to)
    if invoice_id := int_or_none(qp.get("invoice_id")):
        stmt = stmt.where(Payment.invoice_id == invoice_id)
    page = paginate(db, stmt, page_args(request))
    return render(request, "staff/payments.html", user, page=page, filters=qp, **STATUS_OPTIONS)


# ---------- Reports ----------
@router.get("/reports")
def reports_page(request: Request, user: User = Depends(STAFF_PAGE), db: Session = Depends(get_db)):
    qp = request.query_params
    date_from, date_to = date_or_none(qp.get("date_from")), date_or_none(qp.get("date_to"))
    customer_id = int_or_none(qp.get("customer_id"))
    stats = report_service.summary(db, date_from, date_to, customer_id)
    overdue = paginate(db, report_service.overdue_invoices_query(date_from, date_to, customer_id), page_args(request))
    revenue = report_service.revenue_by_month(db, PageParams(page=1, limit=12), date_from, date_to, customer_id)
    return render(
        request, "staff/reports.html", user, stats=stats, overdue=overdue, revenue=revenue["items"],
        filters=qp, customers=_customer_options(db), days_overdue=report_service.days_overdue,
    )
