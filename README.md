# Lagerlotse

**In short (EN):** an internal-tools demo for a technical wholesaler. Staff ask questions in German, a Claude-based agent answers using a fixed set of typed database tools, and every number in the answer is checked against the tool results. Includes a dashboard and an automated weekly reorder report. All data is synthetic.

> Status: MVP vollständig (Daten, Assistent mit Zahlenprüfung, Web-App, Dashboard, Wochenbericht, Docker). Zahlen in dieser Datei stammen ausschließlich aus `task eval` und `task report`.

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

## So funktioniert die Zahlenprüfung

1. Das Modell darf kein SQL schreiben. Es wählt aus festen, typisierten Lese-Tools (z. B. `top_customers`, `reorder_suggestions`), die über eine Datenbankrolle mit reinen Leserechten laufen.
2. Jedes Tool liefert Zahlen mit Einheit und Zeitraum.
3. Nach der Antwort sucht ein deterministischer Prüfer jede Zahl und jedes Datum im Text (deutsches Format, auch „1,7 Mio. €") und vergleicht sie mit den Tool-Ergebnissen, einschließlich Einheit.
4. Nicht belegte Zahlen werden in der Antwort markiert und als „ungeprüft" gekennzeichnet. Unter jeder Antwort steht, aus welchem Tool-Feld jede Zahl stammt.

Dieselben Tools erzeugen den Wochenbericht; das Dashboard nutzt dieselben Definitionen (per Test abgesichert).

## Evaluation

Testfragen in vier Kategorien (`tests/eval/questions.yaml`). Die erwarteten Zahlen berechnet eigenes SQL, unabhängig vom Tool-Code. Eine Frage gilt als bestanden, wenn die richtigen Tools aufgerufen wurden, die erwarteten Zahlen in der Antwort stehen und die Zahlenprüfung keine unbelegte Zahl findet. Die Tabelle erzeugt `task report` aus `results/eval.json`.

<!-- eval:start -->
Stand: Lauf vom 25.11.2026, Modell `claude-sonnet-5-5`, Denktiefe `medium`, Datenstand 20.11.2026.

| Kategorie | bestanden |
|---|--:|
| Direkt beantwortbar | 22 von 22 |
| Mehrere Schritte | 7 von 8 |
| Außerhalb des Umfangs | 5 von 5 |
| Manipulationsversuche | 5 von 5 |
| **Gesamt** | **39 von 40** |

- Antworten mit Zahlen, bei denen jede Zahl belegt war: 33 von 34
- Richtige Tool-Auswahl: 40 von 40
- Kosten des Laufs: 0,75 USD (Ø 0,019 USD je Frage), Ø 4,1 s je Frage

Nicht bestanden:
- `m04` Welche Lieferanten haben überfällige Bestellungen, und wie war ihre Liefertreue in diesem Jahr? – Ungeprüfte Zahlen: 55,6 %
<!-- eval:end -->

## Schnellstart

Voraussetzungen: Docker, [uv](https://docs.astral.sh/uv/), [Task](https://taskfile.dev).

```bash
cp .env.example .env     # ANTHROPIC_API_KEY, LAGERLOTSE_MODEL, MB_ADMIN_PASSWORD eintragen
task setup               # Abhängigkeiten, Git-Hooks
task up                  # Postgres, Web-App, Metabase
task data                # synthetische Daten (reproduzierbar, gibt einen Hash aus)
task dashboard           # Metabase-Dashboard anlegen
```

Danach: Assistent unter http://localhost:8000, Dashboard unter http://localhost:3000, Wochenbericht unter http://localhost:8000/bericht.

Weitere Befehle: `task ask -- "Frage"` (eine Frage im Terminal, mit Kosten), `task test`, `task lint`, `task eval` (Evaluation, kostet API-Guthaben), `task report` (Bericht und README-Tabelle).

Daten, Tools, Bericht, Dashboard und alle Tests laufen ohne API-Schlüssel; nur der Assistent braucht ihn.

## Dokumentation

- [`docs/PLAN.md`](docs/PLAN.md): Umfang, Meilensteine, nächste Schritte
- [`docs/DECISIONS.md`](docs/DECISIONS.md): Entscheidungen mit Begründung
- [`docs/DEMO.md`](docs/DEMO.md): Demo in drei Minuten
- [`docs/DEPLOY.md`](docs/DEPLOY.md): Betrieb auf einer kleinen VM
- [`dashboards/README.md`](dashboards/README.md): Dashboard als Code
