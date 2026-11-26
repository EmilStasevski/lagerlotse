"""Test database setup. Needs the Postgres from `docker compose up -d postgres`.

The test database (default `lagerlotse_test`) is created if missing and loaded with the
hand-made fixture dataset once per test session.
"""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, create_engine, make_url, text

from lagerlotse.data.seed import load, setup_reader_role
from tests.fixture_data import fixture_dataset

TEST_DATABASE_URL = os.environ.get(
    "LAGERLOTSE_TEST_DATABASE_URL",
    "postgresql+psycopg://lagerlotse:lagerlotse@localhost:5432/lagerlotse_test",
)
READER_ROLE = "lagerlotse_reader_test"
READER_PASSWORD = "test_reader"


def _ensure_database(url: str) -> None:
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": target.database}
        ).first()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    _ensure_database(TEST_DATABASE_URL)
    eng = create_engine(TEST_DATABASE_URL)
    with eng.begin() as conn:
        load(conn, fixture_dataset())
        setup_reader_role(conn, READER_PASSWORD, READER_ROLE)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as connection:
        yield connection
        connection.rollback()


@pytest.fixture
def reader_url(engine: Engine) -> str:
    url = make_url(TEST_DATABASE_URL)
    return url.set(username=READER_ROLE, password=READER_PASSWORD).render_as_string(
        hide_password=False
    )
