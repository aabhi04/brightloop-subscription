from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import (
    Discount,
    Plan,
    Product,
    ProductVariant,
    QuotationTemplate,
    QuotationTemplateLine,
    Subscription,
    Tax,
    User,
)
from app.schemas.catalog import DiscountIn, PlanIn, ProductIn, TaxIn, TemplateIn, VariantIn
from app.services import auth_service, plan_service, report_service
from app.services.subscription_service import resolve_product_and_variant
from app.utils.constants import (
    BillingPeriod,
    DiscountScope,
    DiscountType,
    Role,
    SubscriptionStatus,
    TaxType,
)
from app.utils.errors import AppError, NotFound, get_or_404
from app.utils.pagination import paginate
from app.web.common import (
    ADMIN_PAGE,
    PASSWORD_RULES,
    blank_to_none,
    form_bool,
    int_or_none,
    lines_from_form,
    page_args,
    parse,
    render,
    run_action,
)

router = APIRouter(prefix="/admin")

ENUM_OPTIONS = {
    "billing_periods": [(p.value, p.value.title()) for p in BillingPeriod],
    "tax_types": [(t.value, t.value.title()) for t in TaxType],
    "discount_types": [(t.value, t.value.title()) for t in DiscountType],
    "discount_scopes": [(s.value, s.value.title()) for s in DiscountScope],
}


def _editing(db: Session, model, request: Request):
    edit_id = int_or_none(request.query_params.get("edit"))
    return db.get(model, edit_id) if edit_id else None


# ---------- Dashboard ----------
@router.get("")
def dashboard(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    stats = report_service.summary(db)
    counts = {
        "products": db.scalar(select(func.count(Product.id))),
        "plans": db.scalar(select(func.count(Plan.id))),
        "customers": db.scalar(select(func.count(User.id)).where(User.role == Role.CUSTOMER)),
        "staff": db.scalar(select(func.count(User.id)).where(User.role == Role.STAFF)),
    }
    by_status = dict(
        db.execute(select(Subscription.status, func.count(Subscription.id)).group_by(Subscription.status)).all()
    )
    sub_counts = [(s.value, by_status.get(s, 0)) for s in SubscriptionStatus]
    return render(request, "admin/dashboard.html", user, stats=stats, counts=counts, sub_counts=sub_counts)


# ---------- Products & variants ----------
@router.get("/products")
def products_page(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    q = request.query_params.get("q") or ""
    stmt = select(Product).options(selectinload(Product.variants)).order_by(Product.id)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    page = paginate(db, stmt, page_args(request))
    return render(request, "admin/products.html", user, page=page, q=q, editing=_editing(db, Product, request))


def _product_data(form) -> ProductIn:
    return parse(ProductIn, {
        "name": form.get("name", ""),
        "type": form.get("type") or "SERVICE",
        "sales_price": form.get("sales_price") or "0",
        "cost_price": form.get("cost_price") or "0",
        "notes": blank_to_none(form.get("notes")),
    })


@router.post("/products")
async def create_product(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        product = Product(**_product_data(form).model_dump(exclude={"variants"}))
        db.add(product)
        db.commit()

    return run_action(db, action, "/admin/products", "Product created", "/admin/products")


@router.post("/products/{product_id}")
async def update_product(product_id: int, request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        product = get_or_404(db, Product, product_id)
        for key, value in _product_data(form).model_dump(exclude={"variants"}).items():
            setattr(product, key, value)
        db.commit()

    return run_action(db, action, "/admin/products", "Product updated", f"/admin/products?edit={product_id}")


@router.post("/products/{product_id}/delete")
def delete_product(product_id: int, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    def action():
        db.delete(get_or_404(db, Product, product_id))
        db.commit()

    return run_action(db, action, "/admin/products", "Product deleted", "/admin/products")


@router.post("/products/{product_id}/variants")
async def add_variant(product_id: int, request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        get_or_404(db, Product, product_id)
        data = parse(VariantIn, {
            "attribute": form.get("attribute", ""),
            "value": form.get("value", ""),
            "extra_price": form.get("extra_price") or "0",
        })
        db.add(ProductVariant(product_id=product_id, **data.model_dump()))
        db.commit()

    return run_action(db, action, "/admin/products", "Variant added", "/admin/products")


@router.post("/products/{product_id}/variants/{variant_id}/delete")
def delete_variant(product_id: int, variant_id: int, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    def action():
        variant = db.get(ProductVariant, variant_id)
        if not variant or variant.product_id != product_id:
            raise NotFound("Variant")
        db.delete(variant)
        db.commit()

    return run_action(db, action, "/admin/products", "Variant deleted", "/admin/products")


# ---------- Plans ----------
@router.get("/plans")
def plans_page(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    page = paginate(db, select(Plan).order_by(Plan.id), page_args(request))
    return render(request, "admin/plans.html", user, page=page, editing=_editing(db, Plan, request), **ENUM_OPTIONS)


def _plan_data(form) -> PlanIn:
    return parse(PlanIn, {
        "name": form.get("name", ""),
        "price": form.get("price") or "0",
        "billing_period": form.get("billing_period"),
        "min_quantity": form.get("min_quantity") or 1,
        "start_date": form.get("start_date"),
        "end_date": blank_to_none(form.get("end_date")),
        "auto_close": form_bool(form, "auto_close"),
        "closable": form_bool(form, "closable"),
        "pausable": form_bool(form, "pausable"),
        "renewable": form_bool(form, "renewable"),
    })


@router.post("/plans")
async def create_plan(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        db.add(Plan(**_plan_data(form).model_dump()))
        db.commit()

    return run_action(db, action, "/admin/plans", "Plan created", "/admin/plans")


@router.post("/plans/{plan_id}")
async def update_plan(plan_id: int, request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        plan = get_or_404(db, Plan, plan_id)
        for key, value in _plan_data(form).model_dump().items():
            setattr(plan, key, value)
        db.commit()

    return run_action(db, action, "/admin/plans", "Plan updated", f"/admin/plans?edit={plan_id}")


@router.post("/plans/{plan_id}/{verb}")
def plan_action(plan_id: int, verb: str, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    actions = {
        "close": (plan_service.close_plan, "Plan closed"),
        "pause": (plan_service.pause_plan, "Plan paused"),
        "renew": (plan_service.renew_plan, "Plan renewed"),
    }
    if verb == "delete":
        def action():
            db.delete(get_or_404(db, Plan, plan_id))
            db.commit()
        return run_action(db, action, "/admin/plans", "Plan deleted", "/admin/plans")
    if verb not in actions:
        raise NotFound("Action")
    fn, message = actions[verb]
    return run_action(db, lambda: fn(db, plan_id), "/admin/plans", message, "/admin/plans")


# ---------- Quotation templates ----------
def _catalog(db: Session) -> dict:
    return {
        "products": db.scalars(select(Product).options(selectinload(Product.variants)).order_by(Product.name)).all(),
        "plans": db.scalars(select(Plan).order_by(Plan.name)).all(),
    }


@router.get("/templates")
def templates_page(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    stmt = (
        select(QuotationTemplate)
        .options(selectinload(QuotationTemplate.lines), selectinload(QuotationTemplate.plan))
        .order_by(QuotationTemplate.id)
    )
    page = paginate(db, stmt, page_args(request))
    return render(request, "admin/templates.html", user, page=page, **_catalog(db))


@router.post("/templates")
async def create_template(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        lines = [{k: v for k, v in l.items() if k != "tax_id"} for l in lines_from_form(form)]
        data = parse(TemplateIn, {
            "name": form.get("name", ""),
            "validity_days": form.get("validity_days") or 0,
            "plan_id": form.get("plan_id") or 0,
            "lines": lines,
        })
        get_or_404(db, Plan, data.plan_id)
        for line in data.lines:
            resolve_product_and_variant(db, line.product_id, line.variant_id)
        db.add(QuotationTemplate(
            name=data.name, validity_days=data.validity_days, plan_id=data.plan_id,
            lines=[QuotationTemplateLine(**l.model_dump()) for l in data.lines],
        ))
        db.commit()

    return run_action(db, action, "/admin/templates", "Template created", "/admin/templates")


@router.post("/templates/{template_id}/delete")
def delete_template(template_id: int, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    def action():
        db.delete(get_or_404(db, QuotationTemplate, template_id, "Quotation template"))
        db.commit()

    return run_action(db, action, "/admin/templates", "Template deleted", "/admin/templates")


# ---------- Discounts ----------
@router.get("/discounts")
def discounts_page(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    stmt = select(Discount).options(selectinload(Discount.products)).order_by(Discount.id)
    page = paginate(db, stmt, page_args(request))
    products = db.scalars(select(Product).order_by(Product.name)).all()
    return render(
        request, "admin/discounts.html", user, page=page, products=products,
        editing=_editing(db, Discount, request), **ENUM_OPTIONS,
    )


def _discount_data(form) -> DiscountIn:
    return parse(DiscountIn, {
        "name": form.get("name", ""),
        "type": form.get("type"),
        "value": form.get("value") or "0",
        "min_purchase": form.get("min_purchase") or "0",
        "min_quantity": form.get("min_quantity") or 0,
        "start_date": form.get("start_date"),
        "end_date": form.get("end_date"),
        "usage_limit": form.get("usage_limit") or 0,
        "applies_to": form.get("applies_to"),
        "product_ids": [int(p) for p in form.getlist("product_ids") if p],
    })


def _products_by_id(db: Session, ids: list[int]) -> list[Product]:
    products = db.scalars(select(Product).where(Product.id.in_(ids))).all() if ids else []
    if len(products) != len(set(ids)):
        raise AppError("One or more selected products no longer exist")
    return list(products)


@router.post("/discounts")
async def create_discount(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        data = _discount_data(form)
        db.add(Discount(**data.model_dump(exclude={"product_ids"}), products=_products_by_id(db, data.product_ids)))
        db.commit()

    return run_action(db, action, "/admin/discounts", "Discount created", "/admin/discounts")


@router.post("/discounts/{discount_id}")
async def update_discount(discount_id: int, request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        discount = get_or_404(db, Discount, discount_id)
        data = _discount_data(form)
        for key, value in data.model_dump(exclude={"product_ids"}).items():
            setattr(discount, key, value)
        discount.products = _products_by_id(db, data.product_ids)
        db.commit()

    return run_action(db, action, "/admin/discounts", "Discount updated", f"/admin/discounts?edit={discount_id}")


@router.post("/discounts/{discount_id}/delete")
def delete_discount(discount_id: int, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    def action():
        db.delete(get_or_404(db, Discount, discount_id))
        db.commit()

    return run_action(db, action, "/admin/discounts", "Discount deleted", "/admin/discounts")


# ---------- Taxes ----------
@router.get("/taxes")
def taxes_page(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    page = paginate(db, select(Tax).order_by(Tax.id), page_args(request))
    return render(request, "admin/taxes.html", user, page=page, editing=_editing(db, Tax, request), **ENUM_OPTIONS)


def _tax_data(form) -> TaxIn:
    return parse(TaxIn, {
        "name": form.get("name", ""),
        "type": form.get("type"),
        "rate": form.get("rate") or "0",
        "is_active": form_bool(form, "is_active"),
    })


@router.post("/taxes")
async def create_tax(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        db.add(Tax(**_tax_data(form).model_dump()))
        db.commit()

    return run_action(db, action, "/admin/taxes", "Tax created", "/admin/taxes")


@router.post("/taxes/{tax_id}")
async def update_tax(tax_id: int, request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        tax = get_or_404(db, Tax, tax_id)
        for key, value in _tax_data(form).model_dump().items():
            setattr(tax, key, value)
        db.commit()

    return run_action(db, action, "/admin/taxes", "Tax updated", f"/admin/taxes?edit={tax_id}")


@router.post("/taxes/{tax_id}/delete")
def delete_tax(tax_id: int, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    def action():
        db.delete(get_or_404(db, Tax, tax_id))
        db.commit()

    return run_action(db, action, "/admin/taxes", "Tax deleted", "/admin/taxes")


# ---------- Staff ----------
@router.get("/staff")
def staff_page(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    stmt = select(User).where(User.role.in_([Role.ADMIN, Role.STAFF])).order_by(User.id)
    page = paginate(db, stmt, page_args(request))
    return render(request, "admin/staff.html", user, page=page, password_rules=PASSWORD_RULES)


@router.post("/staff")
async def create_staff(request: Request, user: User = Depends(ADMIN_PAGE), db: Session = Depends(get_db)):
    form = await request.form()

    def action():
        auth_service.create_user(db, form.get("name", ""), form.get("email", ""), form.get("password", ""), Role.STAFF)
        db.commit()

    return run_action(db, action, "/admin/staff", "Staff user created", "/admin/staff")
