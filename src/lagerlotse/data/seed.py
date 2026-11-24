"""Create the schema, load synthetic data and set up the read-only role.

Run with `task data`. Prints a hash over all table contents; two runs with the same seed
must print the same hash.
"""

from importlib.resources import files

import psycopg
from psycopg import sql
from sqlalchemy import Connection, create_engine, text

from lagerlotse.config import get_settings
from lagerlotse.data.generator import Dataset, generate

READER_ROLE = "lagerlotse_reader"
HASH_ORDER = {"dataset_meta": "key", "stock": "product_id"}


def schema_sql() -> str:
    return files("lagerlotse.data").joinpath("schema.sql").read_text(encoding="utf-8")


def load(conn: Connection, dataset: Dataset) -> None:
    """Recreate all tables and bulk-load the dataset with COPY."""
    raw = conn.connection.driver_connection
    assert isinstance(raw, psycopg.Connection)
    with raw.cursor() as cur:
        cur.execute(schema_sql())
        for table, rows in dataset.tables():
            if not rows:
                continue
            columns = list(rows[0])
            stmt = sql.SQL("COPY {} ({}) FROM STDIN").format(
                sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns))
            )
            with cur.copy(stmt) as copy:
                for row in rows:
                    copy.write_row([row[c] for c in columns])


def setup_reader_role(conn: Connection, password: str, role_name: str = READER_ROLE) -> None:
    """Read-only role for the agent: SELECT only, read-only transactions, statement timeout.

    Roles are cluster-wide, so tests pass their own role name to leave the dev role alone.
    """
    raw = conn.connection.driver_connection
    assert isinstance(raw, psycopg.Connection)
    role = sql.Identifier(role_name)
    with raw.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
        if cur.fetchone() is None:
            cur.execute(sql.SQL("CREATE ROLE {} LOGIN").format(role))
        cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(role, sql.Literal(password)))
        cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5s'").format(role))
        cur.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(role))
        cur.execute("SELECT current_database()")
        row = cur.fetchone()
        assert row is not None
        cur.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(row[0]), role)
        )
        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
        cur.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(role))


def dataset_hash(conn: Connection, dataset: Dataset) -> str:
    """MD5 over all rows of all tables, in a stable order."""
    parts = []
    for table, _ in dataset.tables():
        order = HASH_ORDER.get(table, "id")
        value = conn.execute(
            text(f"SELECT md5(string_agg(t::text, '|' ORDER BY {order})) FROM {table} t")
        ).scalar_one()
        parts.append(f"{table}:{value}")
    return str(conn.execute(text("SELECT md5(:s)"), {"s": ";".join(parts)}).scalar_one())


def main() -> None:
    settings = get_settings()
    dataset = generate(settings.seed)
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        load(conn, dataset)
        setup_reader_role(conn, settings.reader_password)
        digest = dataset_hash(conn, dataset)
    for table, rows in dataset.tables():
        print(f"{table:<22} {len(rows):>7} Zeilen")
    print(f"Seed {settings.seed}, Datenstand {dataset.meta[0]['value']}, Hash {digest}")


if __name__ == "__main__":
    main()
