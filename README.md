# Lagerlotse

**In short (EN):** an internal-tools demo for a technical wholesaler. Staff ask questions in German, a Claude-based agent answers using a fixed set of typed database tools, and every number in the answer is checked against the tool results. Includes a dashboard and an automated weekly reorder report. All data is synthetic.

> Status: MVP in Arbeit. Daten, Lese-Tools, Zahlenprüfung, Assistent und Evaluation stehen; Web-App und Dashboard folgen. Alle Zahlen in dieser Datei werden später von `task report` erzeugt.

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

## Evaluation

40 Testfragen in vier Kategorien (`tests/eval/questions.yaml`). Die erwarteten Zahlen berechnet eigenes SQL, unabhängig vom Tool-Code. Eine Frage gilt als bestanden, wenn die richtigen Tools aufgerufen wurden, die erwarteten Zahlen in der Antwort stehen und die Zahlenprüfung keine unbelegte Zahl findet. Die Tabelle erzeugt `task report` aus `results/eval.json`.

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
