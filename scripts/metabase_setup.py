"""Set up Metabase from dashboards/metabase.yaml: admin user, database connection on the
read-only role, a "Lagerlotse" collection with all cards and the dashboard.

    task dashboard

Needs MB_ADMIN_EMAIL and MB_ADMIN_PASSWORD in .env (never committed). Safe to run again:
existing Lagerlotse cards and dashboards are archived and recreated.
"""

import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

from lagerlotse.config import get_settings

SPEC = Path("dashboards/metabase.yaml")
COLLECTION = "Lagerlotse"
DATABASE_NAME = "Lagerlotse (nur lesen)"


def wait_until_ready(client: httpx.Client, timeout_s: int = 180) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if client.get("/api/health").json().get("status") == "ok":
                return
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(3)
    sys.exit("Metabase antwortet nicht (läuft `task up`?).")


def login(client: httpx.Client, email: str, password: str) -> None:
    props = client.get("/api/session/properties").json()
    token = props.get("setup-token")
    if token and not props.get("has-user-setup"):
        client.post(
            "/api/setup",
            json={
                "token": token,
                "user": {"first_name": "Lagerlotse", "last_name": "Admin", "email": email,
                         "password": password, "site_name": "Lagerlotse"},
                "prefs": {"site_name": "Lagerlotse", "site_locale": "de", "allow_tracking": False},
            },
        ).raise_for_status()  # fmt: skip
        print("Metabase: Admin angelegt")
    session = client.post("/api/session", json={"username": email, "password": password})
    if session.status_code != 200:
        sys.exit("Metabase-Anmeldung fehlgeschlagen (MB_ADMIN_EMAIL/MB_ADMIN_PASSWORD prüfen).")
    client.headers["X-Metabase-Session"] = session.json()["id"]


def ensure_database(client: httpx.Client) -> int:
    settings = get_settings()
    databases = client.get("/api/database").json()
    for db in databases.get("data", databases if isinstance(databases, list) else []):
        if db["name"] == DATABASE_NAME:
            return int(db["id"])
    created = client.post(
        "/api/database",
        json={
            "engine": "postgres",
            "name": DATABASE_NAME,
            "details": {"host": "postgres", "port": 5432, "dbname": "lagerlotse",
                        "user": "lagerlotse_reader", "password": settings.reader_password,
                        "ssl": False},
        },
    )  # fmt: skip
    created.raise_for_status()
    print("Metabase: Datenbankverbindung angelegt (Rolle lagerlotse_reader)")
    return int(created.json()["id"])


def ensure_collection(client: httpx.Client) -> int:
    for c in client.get("/api/collection").json():
        if c.get("name") == COLLECTION and not c.get("archived"):
            items = client.get(f"/api/collection/{c['id']}/items").json()
            for item in items.get("data", []):
                if item["model"] in ("card", "dashboard"):
                    client.put(f"/api/{item['model']}/{item['id']}", json={"archived": True})
            return int(c["id"])
    created = client.post("/api/collection", json={"name": COLLECTION, "color": "#1D5FA8"})
    created.raise_for_status()
    return int(created.json()["id"])


def visualization(card: dict[str, Any]) -> dict[str, Any]:
    if card["display"] in ("line", "bar"):
        return {"graph.dimensions": [card["dimension"]], "graph.metrics": card["metrics"]}
    return {}


def create_cards(client: httpx.Client, db_id: int, collection_id: int, spec: dict[str, Any]) -> int:
    dashcards = []
    for i, card in enumerate(spec["cards"]):
        created = client.post(
            "/api/card",
            json={
                "name": card["name"],
                "display": card["display"],
                "collection_id": collection_id,
                "dataset_query": {"database": db_id, "type": "native",
                                  "native": {"query": card["sql"]}},
                "visualization_settings": visualization(card),
            },
        )  # fmt: skip
        if created.status_code >= 400:
            sys.exit(f"Karte '{card['name']}' fehlgeschlagen: {created.text[:300]}")
        dashcards.append({"id": -(i + 1), "card_id": created.json()["id"], **card["position"]})

    dashboard = client.post(
        "/api/dashboard",
        json={"name": spec["dashboard"], "description": spec["description"],
              "collection_id": collection_id},
    )  # fmt: skip
    dashboard.raise_for_status()
    dash_id = int(dashboard.json()["id"])
    client.put(f"/api/dashboard/{dash_id}", json={"dashcards": dashcards}).raise_for_status()
    return dash_id


def main() -> None:
    settings = get_settings()
    email, password = settings.mb_admin_email, settings.mb_admin_password.get_secret_value()
    if not email or not password:
        sys.exit("MB_ADMIN_EMAIL und MB_ADMIN_PASSWORD in .env setzen (siehe .env.example).")
    base_url = settings.metabase_url
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    with httpx.Client(base_url=base_url, timeout=60) as client:
        wait_until_ready(client)
        login(client, email, password)
        db_id = ensure_database(client)
        collection_id = ensure_collection(client)
        dash_id = create_cards(client, db_id, collection_id, spec)
    print(f"Dashboard: {base_url}/dashboard/{dash_id} ({len(spec['cards'])} Karten)")


if __name__ == "__main__":
    main()
