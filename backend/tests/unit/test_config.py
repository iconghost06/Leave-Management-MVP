"""Settings rewrites the host's Postgres URL so SQLAlchemy uses psycopg 3 (PLAN 1.3)."""
import pytest

from app.core.config import Settings


def _database_url(url: str) -> str:
    return Settings(_env_file=None, database_url=url, secret_key="k", signup_code="c").database_url


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:pw@host:5432/db", "postgresql+psycopg://u:pw@host:5432/db"),
        ("postgresql://u:pw@host/db", "postgresql+psycopg://u:pw@host/db"),
        # the query string survives the rewrite
        (
            "postgres://u:pw@host/db?sslmode=require",
            "postgresql+psycopg://u:pw@host/db?sslmode=require",
        ),
        (
            "postgresql://u:pw@host/db?sslmode=require&channel_binding=require",
            "postgresql+psycopg://u:pw@host/db?sslmode=require&channel_binding=require",
        ),
    ],
)
def test_host_urls_are_rewritten_to_psycopg3(given, expected):
    assert _database_url(given) == expected


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://localhost:5432/leave",
        "postgresql+psycopg://u:pw@host/db?sslmode=require",
    ],
)
def test_urls_already_naming_the_driver_are_unchanged(url):
    assert _database_url(url) == url
