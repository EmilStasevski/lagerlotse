# Betrieb auf einer kleinen VM

Ziel: Lagerlotse auf einem einzelnen Server betreiben, z. B. 2 vCPU und 4 GB RAM (Metabase braucht davon gut 1,5 GB). Alles läuft in Docker Compose; geheime Werte stehen nur in `.env` auf dem Server.

## 1. Server vorbereiten

```bash
# Debian/Ubuntu: Docker Engine und Compose-Plugin nach docs.docker.com installieren
sudo apt-get update && sudo apt-get install -y git
git clone <repository-url> /opt/lagerlotse && cd /opt/lagerlotse
cp .env.example .env && chmod 600 .env
```

In `.env` auf dem Server **immer** eigene Werte setzen:

| Variable | Wert |
|---|---|
| `ANTHROPIC_API_KEY` | API-Schlüssel (am besten ein eigener Schlüssel nur für diesen Server) |
| `LAGERLOTSE_MODEL` | z. B. `claude-sonnet-5-5` |
| `LAGERLOTSE_APP_KEY` | langer Zufallswert, Zugangsschlüssel für die Web-App |
| `POSTGRES_PASSWORD` | langer Zufallswert |
| `LAGERLOTSE_READER_PASSWORD` | langer Zufallswert |
| `MB_ADMIN_PASSWORD` | langer Zufallswert |

Zufallswerte erzeugen: `openssl rand -base64 24`. Die Datenbank-URLs setzt `compose.yaml` aus diesen Passwörtern selbst zusammen.

## 2. Starten und Daten laden

```bash
docker compose up -d --build --wait postgres
docker compose run --rm -T app python -m lagerlotse.data.seed   # legt auch die Lese-Rolle an
docker compose up -d --build --wait
docker compose run --rm -T -e LAGERLOTSE_METABASE_URL=http://metabase:3000 \
  app python scripts/metabase_setup.py
```

Reihenfolge beachten: Die App meldet sich erst „healthy", wenn die Daten und die Lese-Rolle existieren. Alle Ports binden nur an `127.0.0.1`. Von außen ist zunächst nichts erreichbar.

**Kleine Rechner:** Der Stack läuft auch auf einem Thin Client mit 4 GB RAM (getestet: Celeron J1900, Ubuntu 24.04). Metabase ist dafür auf 1 GB Heap begrenzt (`MB_JAVA_OPTS`); der erste Start dauert dort einige Minuten.

### Variante: nur privat über Tailscale

Ohne Domain und ohne offene Ports: Läuft auf dem Server bereits Tailscale, veröffentlicht `tailscale serve` die Dienste nur im eigenen Tailnet, mit HTTPS-Zertifikat:

```bash
sudo tailscale serve --bg --https=443  http://127.0.0.1:8000   # Web-App
sudo tailscale serve --bg --https=8443 http://127.0.0.1:3000   # Dashboard
```

Beim ersten Mal muss „Serve" in der Tailscale-Verwaltung freigegeben werden (der Befehl nennt den Link). Abschnitte 3 und 4 entfallen dann.

## 3. Web-App über HTTPS veröffentlichen

Ein Reverse Proxy auf dem Host übernimmt TLS. Beispiel mit Caddy (holt Zertifikate automatisch):

```
# /etc/caddy/Caddyfile
lagerlotse.example.de {
    reverse_proxy 127.0.0.1:8000
}
```

Die App verlangt dann den Zugangsschlüssel aus `LAGERLOTSE_APP_KEY`; Cookies werden über HTTPS mit `Secure` gesetzt. Firewall: nur 22, 80 und 443 öffnen.

## 4. Dashboard nur über SSH-Tunnel

Metabase bleibt intern. Zugriff vom eigenen Rechner:

```bash
ssh -L 3000:127.0.0.1:3000 user@server   # danach http://localhost:3000
```

## 5. Wöchentlicher Bericht

Cron des Benutzers, der Docker ausführen darf (`crontab -e`), montags 6 Uhr:

```
0 6 * * 1  cd /opt/lagerlotse && docker compose run --rm -T app python -m lagerlotse.report /app/reports >> $HOME/lagerlotse-report.log 2>&1
```

Die Dateien landen in `/opt/lagerlotse/reports/`. Die Seite `/bericht` der Web-App rechnet bei jedem Aufruf neu.

## 6. Aktualisieren und Kosten im Blick behalten

```bash
cd /opt/lagerlotse && git pull && docker compose up -d --build --wait
```

- Im Anthropic Console ein monatliches Ausgabenlimit setzen.
- Protokolle: `docker compose logs app` zeigt je Frage nur Status, Tool-Anzahl und Tokens, keine Inhalte.
- Sicherung: nicht nötig, die Daten sind synthetisch und mit `lagerlotse.data.seed` jederzeit reproduzierbar. Bei echten Daten wären tägliche `pg_dump`-Sicherungen außerhalb des Servers Pflicht.
