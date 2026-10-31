import math
from dataclasses import dataclass

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.utils.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


@dataclass
class PageParams:
    page: int = 1
    limit: int = DEFAULT_PAGE_SIZE

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def page_params(
    page: int = Query(1, ge=1),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> PageParams:
    return PageParams(page=page, limit=limit)


def paginate(db: Session, stmt: Select, params: PageParams, scalars: bool = True) -> dict:
    """Run `stmt` with LIMIT/OFFSET and a COUNT(*) over the same filters."""
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    result = db.execute(stmt.limit(params.limit).offset(params.offset))
    items = result.scalars().unique().all() if scalars else result.all()
    return {
        "items": items,
        "page": params.page,
        "limit": params.limit,
        "total": total,
        "pages": max(1, math.ceil(total / params.limit)),
    }
