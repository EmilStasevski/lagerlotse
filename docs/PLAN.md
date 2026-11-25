# Plan

Ziel: in etwa einer Woche ein vorführbares MVP, das drei Minuten Demo trägt.

## Stand

- [x] Meilenstein 1: Schema, Generator, Fixture-Daten; `task data` liefert reproduzierbar denselben Hash
- [x] Meilenstein 2: acht Lese-Tools mit Tests gegen Fixture-Daten, Nur-Lese-Rolle
- [x] Aus Meilenstein 3 vorgezogen: Tool-Registry (API-Tool-Definitionen) und Zahlenprüfung mit Tests
- [x] Aus Meilenstein 5 vorgezogen: Wochenbericht (Markdown und HTML) über `task report`; jede Zahl darin besteht die Zahlenprüfung. Zeitplanung (cron) folgt mit dem Deployment.
- [x] Meilenstein 3: Agent-Schleife, deutscher Systemprompt, `task ask`, Evaluationsset mit 40 Fragen (`task eval`)

## Meilensteine

1. **Daten (Tag 1):** Schema, Seed-Generator, Fixture-Daten für Tests. Fertig, wenn `task data` zweimal denselben Hash liefert.
2. **Tools (Tag 2):** acht typisierte Lese-Tools mit Tests gegen Fixture-Daten.
3. **Agent und Prüfung (Tag 3-4):** Agent-Schleife mit Claude API, Zahlenprüfung, Evaluationsset mit etwa 40 Fragen.
4. **Web-App (Tag 5):** Chat-Seite und Berichtsseite.
5. **Dashboard und Bericht (Tag 6):** Metabase-Dashboards, wöchentlicher Nachbestellbericht.
6. **Betrieb (Tag 7):** CI, Deployment auf einer VM, README-Tabellen aus `results/`, Demo-Skript.

## Nächste Schritte nach dem MVP (nicht jetzt bauen)

- Anmeldung und Rollen (Vertrieb sieht keine Einkaufspreise)
- Anbindung an ein echtes ERP über eine Schnittstelle
- Eingabe von Aufträgen per E-Mail-Anhang, Extraktion mit Prüfung
- Schulungsmaterial für Kollegen: eine Seite „So fragst du den Assistenten gut"
