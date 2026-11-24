# Lagerlotse

**In short (EN):** an internal-tools demo for a technical wholesaler. Staff ask questions in German, a Claude-based agent answers using a fixed set of typed database tools, and every number in the answer is checked against the tool results. Includes a dashboard and an automated weekly reorder report. All data is synthetic.

> Status: MVP in Arbeit. Daten, Lese-Tools und Zahlenprüfung stehen; Agent, Web-App und Dashboard folgen. Alle Zahlen in dieser Datei werden später von `task report` erzeugt.

## Worum es geht

Vertrieb, Einkauf und Lager stellen täglich dieselben Fragen: Welche Kunden bringen den Umsatz? Welche Artikel liegen zu lange? Was muss nachbestellt werden? Lagerlotse beantwortet solche Fragen auf Deutsch, zeigt die Zahlen im Dashboard und erstellt jede Woche einen Nachbestellvorschlag.

Alle Daten sind **synthetisch** und mit festem Seed erzeugt. Es werden keine echten Firmen-, Kunden- oder Katalogdaten verwendet.

## Bausteine

| Baustein | Technik |
|---|---|
| Daten | PostgreSQL, ERP-artiges Schema, reproduzierbarer Generator |
| Agent | Claude API mit Tool-Calling, nur typisierte Lese-Tools |
| Prüfung | Jede Zahl der Antwort wird gegen die Tool-Ergebnisse geprüft |
| Web-App | FastAPI, Jinja, htmx |
| Dashboard | Metabase |
| Automatisierung | Wöchentlicher Bericht mit Nachbestellvorschlägen |
| Betrieb | Docker Compose, GitHub Actions, Deployment auf einer kleinen VM |

## Schnellstart

```bash
cp .env.example .env     # ANTHROPIC_API_KEY eintragen (nur für den Agenten nötig)
task setup
task up
task data
task test
```

Danach: Chat unter http://localhost:8000, Dashboard unter http://localhost:3000.

## Dokumentation

- [`docs/PLAN.md`](docs/PLAN.md): Umfang, Meilensteine, nächste Schritte
- [`docs/DECISIONS.md`](docs/DECISIONS.md): Entscheidungen mit Begründung
- [`docs/DEMO.md`](docs/DEMO.md): Demo in drei Minuten
- [`CLAUDE.md`](CLAUDE.md): Arbeitsanweisungen für Claude Code
