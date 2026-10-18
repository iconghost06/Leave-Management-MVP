from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds TEST_DATABASE_URL, used only by the tests
        case_sensitive=False,
    )

    database_url: str
    # Required, no default: the app refuses to start without them.
    secret_key: str
    signup_code: str
    password_hash_fast: bool = False
    cors_origins: str = "http://localhost:5173"

    @field_validator("database_url")
    @classmethod
    def _use_psycopg3_driver(cls, url: str) -> str:
        # Hosts hand out postgres:// or postgresql://; SQLAlchemy would pick psycopg2 for those.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
