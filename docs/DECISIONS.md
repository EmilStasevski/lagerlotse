# Entscheidungen

Kurz, eine Entscheidung pro Absatz: Kontext, Entscheidung, Folge.

## 001 Eine Datenbank für alles
Dashboard, Agent und Bericht lesen dieselben Daten. Wir nehmen PostgreSQL und kein zusätzliches Data Warehouse. Folge: einfacher Betrieb, die Zahlen im Dashboard und im Chat können nicht auseinanderlaufen.

## 002 Typisierte Tools statt freiem SQL
Das Modell darf kein SQL schreiben, sondern nur feste Tools aufrufen. Das ist weniger flexibel, aber nachprüfbar und sicher. Freies Text-to-SQL ist ein möglicher späterer Schritt mit AST-Prüfung und Nur-Lese-Rolle.

## 003 Server-seitiges HTML statt Single-Page-App
Für eine interne Chat-Seite reichen Jinja und htmx. Kein JavaScript-Build, weniger Wartung.
