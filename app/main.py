from fastapi import FastAPI
from sqlalchemy import text

from app.db import engine


def create_app() -> FastAPI:
    app = FastAPI(title="Brightloop Subscription Management")

    @app.get("/api/health")
    def health():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()
