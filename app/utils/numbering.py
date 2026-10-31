from sqlalchemy import text
from sqlalchemy.orm import Session


def next_number(db: Session, prefix: str) -> str:
    """Return the next number for a prefix, e.g. SUB-0001.

    Uses a single upsert so concurrent transactions never get the same value.
    Runs inside the caller's transaction; if that rolls back, so does the counter.
    """
    value = db.execute(
        text(
            "INSERT INTO counters (name, value) VALUES (:name, 1) "
            "ON CONFLICT (name) DO UPDATE SET value = counters.value + 1 "
            "RETURNING value"
        ),
        {"name": prefix},
    ).scalar_one()
    return f"{prefix}-{value:04d}"
