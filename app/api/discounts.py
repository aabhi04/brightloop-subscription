from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps.auth import ADMIN_ONLY
from app.models import Discount, Product
from app.schemas.catalog import DiscountIn, DiscountOut
from app.utils.errors import AppError, get_or_404
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/discounts", tags=["discounts"], dependencies=[Depends(ADMIN_ONLY)])


def _products(db: Session, ids: list[int]) -> list[Product]:
    if not ids:
        return []
    products = db.scalars(select(Product).where(Product.id.in_(ids))).all()
    missing = set(ids) - {p.id for p in products}
    if missing:
        raise AppError(f"Unknown product ids: {sorted(missing)}")
    return list(products)


@router.get("")
def list_discounts(
    active_on: date | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Discount).options(selectinload(Discount.products)).order_by(Discount.id)
    if active_on:
        stmt = stmt.where(Discount.start_date <= active_on, Discount.end_date >= active_on)
    page = paginate(db, stmt, params)
    page["items"] = [DiscountOut.model_validate(d) for d in page["items"]]
    return page


@router.get("/{discount_id}", response_model=DiscountOut)
def get_discount(discount_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, Discount, discount_id)


@router.post("", response_model=DiscountOut, status_code=201)
def create_discount(body: DiscountIn, db: Session = Depends(get_db)):
    discount = Discount(**body.model_dump(exclude={"product_ids"}), products=_products(db, body.product_ids))
    db.add(discount)
    db.commit()
    return discount


@router.put("/{discount_id}", response_model=DiscountOut)
def update_discount(discount_id: int, body: DiscountIn, db: Session = Depends(get_db)):
    discount = get_or_404(db, Discount, discount_id)
    for key, value in body.model_dump(exclude={"product_ids"}).items():
        setattr(discount, key, value)
    discount.products = _products(db, body.product_ids)
    db.commit()
    return discount


@router.delete("/{discount_id}", status_code=204)
def delete_discount(discount_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Discount, discount_id))
    db.commit()
    return Response(status_code=204)
