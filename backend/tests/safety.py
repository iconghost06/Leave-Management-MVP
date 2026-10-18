"""Guard for the destructive test harness.

The suite runs `alembic upgrade head` and `TRUNCATE ... CASCADE` against
TEST_DATABASE_URL, so it must never be pointed at the dev or a hosted database.
"""
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class UnsafeTestDatabase(Exception):
    pass


def assert_safe_test_database(url: str) -> None:
    """Raise UnsafeTestDatabase unless the database name ends in "_test" and the host is local.

    The message names only the host and database, never the full URL, so no
    credentials reach the terminal or CI logs.
    """
    try:
        parsed = make_url(url)
    except ArgumentError:
        raise UnsafeTestDatabase(
            "Refusing to run tests: TEST_DATABASE_URL is not a valid database URL."
        ) from None

    host = parsed.host or ""
    database = parsed.database or ""
    problems = []
    if host not in LOCAL_HOSTS:
        problems.append(f"host is {host or '(none)'!r}, expected localhost")
    if not database.endswith("_test"):
        problems.append(f"database is {database or '(none)'!r}, its name must end in '_test'")
    if problems:
        raise UnsafeTestDatabase(
            "Refusing to run tests: the suite migrates and TRUNCATEs its database. "
            + "; ".join(problems)
            + ". Point TEST_DATABASE_URL at a local *_test database."
        )
