# Demo in drei Minuten

Vorbereitung (einmalig, vor dem Termin): `task up`, `task data`, `task dashboard`. Tabs öffnen:
http://localhost:8000 (Assistent), http://localhost:3000 (Dashboard „Lagerlotse Überblick"),
http://localhost:8000/bericht (Wochenbericht). Kosten der Demo: unter 0,20 USD.

## 1. Problem (30 s)

„Vertrieb, Einkauf und Lager stellen jede Woche dieselben Fragen. Die Zahlen liegen im ERP, aber
jede Auswertung kostet jemanden eine halbe Stunde. Ein Sprachmodell könnte das beantworten, nur:
Kann man den Zahlen trauen?"

## 2. Chat (60 s)

1. Beispiel-Button **„Welche fünf Kunden hatten im letzten Quartal den höchsten Umsatz?"**
   Zeigen: Zeitraum wird genannt (Q3 2026), Tabelle, grünes Badge „Alle Zahlen belegt".
2. Folgefrage tippen: **„Und was davon ist Wendrich im ganzen Jahr 2025?"**
   (nutzt den Gesprächsverlauf und ruft das Tool neu auf).
3. Beispiel-Button **„Wie wird das Wetter morgen?"**: höfliche Absage, Liste der möglichen Fragen,
   kein Tool-Aufruf.

## 3. Prüfung (45 s)

- Bei einer Antwort **„Wie wurde das geprüft?"** aufklappen: aufgerufene Tools mit Parametern und
  für jede Zahl die Fundstelle im Tool-Ergebnis.
- Eine markierte Abweichung zeigen. Gute Kandidaten (das Modell rechnet hier gern selbst):
  **„Welche Lieferanten haben überfällige Bestellungen, und wie war ihre Liefertreue in diesem Jahr?"**
  oder **„Welche Ladenhüter binden das meiste Kapital?"**. Selbst errechnete Zahlen erscheinen rot
  markiert mit dem Hinweis „Ungeprüft".
- Falls live alles belegt ist: README-Abschnitt „Evaluation" zeigen, dort steht der Fall `m04`
  („Pünktlich waren 55,6 %": vom Modell selbst gerechnet, deshalb markiert).
- Kernsatz: „Das Modell schreibt Text, die Zahlen kommen aus festen Abfragen. Was nicht belegt
  ist, wird markiert und nie still angezeigt."

## 4. Dashboard und Bericht (30 s)

- Metabase: Umsatz laufendes Jahr. Gleiche Zahl wie im Chat, gleiche Definition (ein Test
  sichert das ab).
- `/bericht`: Nachbestellvorschläge mit Regel, überfällige Bestellungen, Ladenhüter. Läuft
  wöchentlich per Cron aus denselben Tools.

## 5. Ausblick (15 s)

Anmeldung mit Rollen (Vertrieb sieht keine Einkaufspreise), Anbindung an ein echtes ERP über eine
Schnittstelle, Aufträge aus E-Mail-Anhängen mit derselben Zahlenprüfung.

## Wenn etwas hakt

- Keine Antwort: `docker compose logs app` (API-Schlüssel, Modell in `.env`?).
- Dashboard leer: `task data`, dann `task dashboard` erneut.
- Ohne Internet: Wochenbericht und Dashboard funktionieren weiter, nur der Chat braucht die API.
