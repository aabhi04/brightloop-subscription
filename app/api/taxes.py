from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps.auth import ADMIN_ONLY, STAFF_OR_ADMIN
from app.models import Tax
from app.schemas.catalog import TaxIn, TaxOut
from app.utils.errors import get_or_404
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/taxes", tags=["taxes"])


# Staff can read taxes (needed to pick a tax on subscription lines); only admins can change them.
@router.get("", dependencies=[Depends(STAFF_OR_ADMIN)])
def list_taxes(active: bool | None = None, params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(Tax).order_by(Tax.id)
    if active is not None:
        stmt = stmt.where(Tax.is_active.is_(active))
    page = paginate(db, stmt, params)
    page["items"] = [TaxOut.model_validate(t) for t in page["items"]]
    return page


@router.get("/{tax_id}", response_model=TaxOut, dependencies=[Depends(STAFF_OR_ADMIN)])
def get_tax(tax_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, Tax, tax_id)


@router.post("", response_model=TaxOut, status_code=201, dependencies=[Depends(ADMIN_ONLY)])
def create_tax(body: TaxIn, db: Session = Depends(get_db)):
    tax = Tax(**body.model_dump())
    db.add(tax)
    db.commit()
    return tax


@router.put("/{tax_id}", response_model=TaxOut, dependencies=[Depends(ADMIN_ONLY)])
def update_tax(tax_id: int, body: TaxIn, db: Session = Depends(get_db)):
    tax = get_or_404(db, Tax, tax_id)
    for key, value in body.model_dump().items():
        setattr(tax, key, value)
    db.commit()
    return tax


@router.delete("/{tax_id}", status_code=204, dependencies=[Depends(ADMIN_ONLY)])
def delete_tax(tax_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Tax, tax_id))
    db.commit()
    return Response(status_code=204)
