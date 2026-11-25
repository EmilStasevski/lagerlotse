# Entscheidungen

Kurz, eine Entscheidung pro Absatz: Kontext, Entscheidung, Folge.

## 001 Eine Datenbank für alles
Dashboard, Agent und Bericht lesen dieselben Daten. Wir nehmen PostgreSQL und kein zusätzliches Data Warehouse. Folge: einfacher Betrieb, die Zahlen im Dashboard und im Chat können nicht auseinanderlaufen.

## 002 Typisierte Tools statt freiem SQL
Das Modell darf kein SQL schreiben, sondern nur feste Tools aufrufen. Das ist weniger flexibel, aber nachprüfbar und sicher. Freies Text-to-SQL ist ein möglicher späterer Schritt mit AST-Prüfung und Nur-Lese-Rolle.

## 003 Server-seitiges HTML statt Single-Page-App
Für eine interne Chat-Seite reichen Jinja und htmx. Kein JavaScript-Build, weniger Wartung.

## 004 Fester Stichtag statt Systemdatum
Synthetische Daten veralten, und „heute" ändert sich bei jedem Lauf. Der Generator schreibt einen festen Stichtag (`dataset_meta.as_of`, derzeit 2026-11-20) in die Datenbank; alle Tools rechnen mit diesem Datum statt mit `CURRENT_DATE`. Folge: Daten, Tests und Hash bleiben reproduzierbar, und der Agent muss relative Angaben („letztes Quartal") vom Stichtag aus auflösen.

## 005 Einheitliche Kennzahlen-Definitionen
Umsatz ist der Netto-Auftragswert aller nicht stornierten Aufträge nach Auftragsdatum, Rohertrag ist Umsatz minus Einkaufspreis zum Verkaufszeitpunkt. Die Definitionen stehen einmal in `data/queries.py` und in den Tool-Beschreibungen; Dashboard und Bericht übernehmen sie. Folge: Chat, Dashboard und Bericht zeigen dieselben Zahlen.

## 006 „Verspätete Lieferungen" heißt Lieferantentreue
Gemeint sind Wareneingänge von Lieferanten nach dem erwarteten Termin, nicht verspätete Auslieferungen an Kunden. Das passt zu Einkauf und Nachbestellung. Die Kundenseite (Wunschtermin, Versanddatum) liegt im Schema bereit und kann später ein eigenes Tool bekommen.

## 007 Zahlenprüfung: streng bei Einheiten, tolerant nur beim Runden
Jede Zahl und jedes Datum der Antwort muss in Tool-Eingaben, Tool-Ergebnissen oder der Frage vorkommen. Erlaubt ist nur Runden auf die angezeigte Genauigkeit (auch „1,7 Mio. €"); eine Zahl mit „€", „%" oder „Tage" passt nur zu einem Feld derselben Einheit. Listenlängen gelten als Tool-Zahl. Kleine Zahlen können zufällig passen; die Prüfung fängt erfundene Beträge zuverlässig, nicht jede Zählung. Folge: Antworten mit nicht belegten Zahlen werden als „ungeprüft" markiert, nie still angezeigt.

## 008 Nachbestellregel
Tagesbedarf aus den letzten 90 Tagen, Meldebestand = Tagesbedarf × (Lieferzeit + 14 Tage Sicherheit), Bestellmenge deckt zusätzlich 30 Tage und wird auf die Mindestbestellmenge aufgerundet. Bewusst einfach und erklärbar statt Prognosemodell; Parameter stehen als Konstanten in `data/queries.py`.

## 009 Eigene Agent-Schleife statt SDK-Tool-Runner
Der Tool-Runner des Anthropic-SDK ist eine Beta-Hilfe und versteckt die Schleife. Wir schreiben die Schleife selbst (rund 60 Zeilen), weil jeder Tool-Aufruf für die Zahlenprüfung protokolliert und auf einer eigenen Nur-Lese-Verbindung ausgeführt wird, mit fester Obergrenze an Runden. Folge: keine Beta-Abhängigkeit in der Schleife, volle Kontrolle; Tests laufen mit einem Fake-Client ohne API-Kosten.

## 010 Kosten und Ausfallsicherheit der API-Aufrufe
Systemprompt und Tool-Definitionen sind bei jedem Aufruf gleich; automatisches Prompt-Caching senkt so die Input-Kosten stark (gemessen: eine typische Frage etwa 0,02 USD mit Sonnet 5.5). Modell und Denktiefe (`LAGERLOTSE_EFFORT`, Standard `medium`) kommen aus `.env`. Lehnt das Modell eine Anfrage aus Sicherheitsgründen ab, übernimmt serverseitig ein Ersatzmodell (`fallbacks: "default"`, abschaltbar über `LAGERLOTSE_REFUSAL_FALLBACK`). `task eval` bricht ab einer Kostengrenze ab (Standard 3 USD).
