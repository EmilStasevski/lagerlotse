# Dashboard (Metabase)

Das Dashboard „Lagerlotse Überblick" wird nicht von Hand geklickt, sondern aus
`metabase.yaml` erzeugt:

```bash
task up          # Postgres, App, Metabase
task data        # synthetische Daten
task dashboard   # Admin, Datenbankverbindung, 10 Karten, Dashboard
```

- Zugangsdaten: `MB_ADMIN_EMAIL` und `MB_ADMIN_PASSWORD` in `.env` (nicht im Repository).
- Metabase liest über die Rolle `lagerlotse_reader` (nur SELECT, 5 s Zeitlimit).
- Die SQL-Definitionen entsprechen den Tools des Assistenten (Umsatz, Rohertrag, Stichtag);
  `tests/test_dashboard.py` prüft, dass Karten und Tools dieselben Zahlen liefern.
- Erneutes `task dashboard` archiviert die alten Karten in der Sammlung „Lagerlotse" und legt
  sie neu an. Änderungen also in `metabase.yaml` machen, nicht in der Metabase-Oberfläche.
