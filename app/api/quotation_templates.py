from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps.auth import ADMIN_ONLY, STAFF_OR_ADMIN
from app.models import Plan, QuotationTemplate, QuotationTemplateLine
from app.schemas.catalog import TemplateIn, TemplateOut
from app.services.subscription_service import resolve_product_and_variant
from app.utils.errors import get_or_404
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/quotation-templates", tags=["quotation templates"])


def _build_lines(db: Session, body: TemplateIn) -> list[QuotationTemplateLine]:
    lines = []
    for line in body.lines:
        resolve_product_and_variant(db, line.product_id, line.variant_id)  # validates ids
        lines.append(QuotationTemplateLine(**line.model_dump()))
    return lines


@router.get("", dependencies=[Depends(STAFF_OR_ADMIN)])
def list_templates(params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    stmt = (
        select(QuotationTemplate)
        .options(selectinload(QuotationTemplate.lines), selectinload(QuotationTemplate.plan))
        .order_by(QuotationTemplate.id)
    )
    page = paginate(db, stmt, params)
    page["items"] = [TemplateOut.model_validate(t) for t in page["items"]]
    return page


@router.get("/{template_id}", response_model=TemplateOut, dependencies=[Depends(STAFF_OR_ADMIN)])
def get_template(template_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, QuotationTemplate, template_id, "Quotation template")


@router.post("", response_model=TemplateOut, status_code=201, dependencies=[Depends(ADMIN_ONLY)])
def create_template(body: TemplateIn, db: Session = Depends(get_db)):
    get_or_404(db, Plan, body.plan_id)
    template = QuotationTemplate(
        name=body.name, validity_days=body.validity_days, plan_id=body.plan_id, lines=_build_lines(db, body)
    )
    db.add(template)
    db.commit()
    return template


@router.put("/{template_id}", response_model=TemplateOut, dependencies=[Depends(ADMIN_ONLY)])
def update_template(template_id: int, body: TemplateIn, db: Session = Depends(get_db)):
    template = get_or_404(db, QuotationTemplate, template_id, "Quotation template")
    get_or_404(db, Plan, body.plan_id)
    template.name = body.name
    template.validity_days = body.validity_days
    template.plan_id = body.plan_id
    template.lines = _build_lines(db, body)
    db.commit()
    return template


@router.delete("/{template_id}", status_code=204, dependencies=[Depends(ADMIN_ONLY)])
def delete_template(template_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, QuotationTemplate, template_id, "Quotation template"))
    db.commit()
    return Response(status_code=204)
