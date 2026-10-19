"""Migration 0002 (users.manager_id): upgrades cleanly from 0001, keeps data, and downgrades.

Runs against the test database and always leaves it at head, because the other tests need that.
"""
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import BACKEND_DIR


@pytest.fixture
def alembic_cfg(engine):
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    yield cfg
    command.upgrade(cfg, "head")


def user_columns(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("users")}


def user_constraints(engine) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text("SELECT conname FROM pg_constraint WHERE conrelid = 'users'::regclass")
            ).scalars()
        )


def insert_user(engine, n: int) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO users (employee_code, name, email, password_hash, role) "
                "VALUES (:c, :n, :e, 'x', 'MANAGER') RETURNING id"
            ),
            {"c": f"EMP-{n:04d}", "n": f"User {n}", "e": f"user{n}@example.com"},
        ).scalar_one()


def test_0002_upgrades_from_0001_keeping_existing_users(engine, alembic_cfg):
    command.downgrade(alembic_cfg, "0001")
    assert "manager_id" not in user_columns(engine)
    existing = insert_user(engine, 1)

    command.upgrade(alembic_cfg, "0002")

    assert "manager_id" in user_columns(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, manager_id FROM users WHERE id = :u"), {"u": existing}
        ).one()
    assert tuple(row) == (existing, None)  # existing users become super managers until assigned
    assert {"fk_users_manager_id", "ck_users_manager_not_self"} <= user_constraints(engine)


def test_0002_downgrades_to_0001_keeping_users(engine, alembic_cfg):
    command.downgrade(alembic_cfg, "0001")
    command.upgrade(alembic_cfg, "0002")
    manager = insert_user(engine, 1)
    report = insert_user(engine, 2)
    with engine.begin() as conn:
        conn.execute(text("UPDATE users SET manager_id = :m WHERE id = :r"), {"m": manager, "r": report})

    command.downgrade(alembic_cfg, "0001")

    assert "manager_id" not in user_columns(engine)
    assert not {"fk_users_manager_id", "ck_users_manager_not_self"} & user_constraints(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() == 2


def test_0002_is_the_head_and_follows_0001(alembic_cfg):
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_cfg)

    assert script.get_heads() == ["0002"]
    assert script.get_revision("0002").down_revision == "0001"


def test_0002_constraints_exist_after_a_full_cycle(engine, alembic_cfg):
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
    only = insert_user(engine, 1)

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET manager_id = id WHERE id = :u"), {"u": only})
