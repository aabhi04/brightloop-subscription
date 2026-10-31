from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps.auth import ADMIN_ONLY, STAFF_OR_ADMIN
from app.models import Product, ProductVariant
from app.schemas.catalog import ProductIn, ProductOut, VariantIn, VariantOut
from app.utils.errors import NotFound, get_or_404
from app.utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", dependencies=[Depends(STAFF_OR_ADMIN)])
def list_products(q: str | None = None, params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(Product).options(selectinload(Product.variants)).order_by(Product.id)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    page = paginate(db, stmt, params)
    page["items"] = [ProductOut.model_validate(p) for p in page["items"]]
    return page


@router.get("/{product_id}", response_model=ProductOut, dependencies=[Depends(STAFF_OR_ADMIN)])
def get_product(product_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, Product, product_id)


@router.post("", response_model=ProductOut, status_code=201, dependencies=[Depends(ADMIN_ONLY)])
def create_product(body: ProductIn, db: Session = Depends(get_db)):
    data = body.model_dump(exclude={"variants"})
    product = Product(**data, variants=[ProductVariant(**v.model_dump()) for v in body.variants])
    db.add(product)
    db.commit()
    return product


@router.put("/{product_id}", response_model=ProductOut, dependencies=[Depends(ADMIN_ONLY)])
def update_product(product_id: int, body: ProductIn, db: Session = Depends(get_db)):
    product = get_or_404(db, Product, product_id)
    for key, value in body.model_dump(exclude={"variants"}).items():
        setattr(product, key, value)
    db.commit()
    return product


@router.delete("/{product_id}", status_code=204, dependencies=[Depends(ADMIN_ONLY)])
def delete_product(product_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Product, product_id))
    db.commit()
    return Response(status_code=204)


# ---------- Variants ----------
def _variant(db: Session, product_id: int, variant_id: int) -> ProductVariant:
    variant = db.get(ProductVariant, variant_id)
    if not variant or variant.product_id != product_id:
        raise NotFound("Variant")
    return variant


@router.get("/{product_id}/variants", response_model=list[VariantOut], dependencies=[Depends(STAFF_OR_ADMIN)])
def list_variants(product_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, Product, product_id).variants


@router.post("/{product_id}/variants", response_model=VariantOut, status_code=201, dependencies=[Depends(ADMIN_ONLY)])
def create_variant(product_id: int, body: VariantIn, db: Session = Depends(get_db)):
    get_or_404(db, Product, product_id)
    variant = ProductVariant(product_id=product_id, **body.model_dump())
    db.add(variant)
    db.commit()
    return variant


@router.put("/{product_id}/variants/{variant_id}", response_model=VariantOut, dependencies=[Depends(ADMIN_ONLY)])
def update_variant(product_id: int, variant_id: int, body: VariantIn, db: Session = Depends(get_db)):
    variant = _variant(db, product_id, variant_id)
    for key, value in body.model_dump().items():
        setattr(variant, key, value)
    db.commit()
    return variant


@router.delete("/{product_id}/variants/{variant_id}", status_code=204, dependencies=[Depends(ADMIN_ONLY)])
def delete_variant(product_id: int, variant_id: int, db: Session = Depends(get_db)):
    db.delete(_variant(db, product_id, variant_id))
    db.commit()
    return Response(status_code=204)
