from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/brightloop"
    test_database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/brightloop_test"

    jwt_secret: str = "dev-only-secret-change-me-in-production-0001"
    jwt_expires_minutes: int = 720
    reset_token_expires_minutes: int = 60

    app_url: str = "http://localhost:8000"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Brightloop <no-reply@brightloop.local>"

    enable_scheduler: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
