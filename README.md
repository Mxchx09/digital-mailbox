# Schul-Postfach

Anonymes digitales Postfach für Schüler: Probleme und Feedback melden. Ausgewählte Verantwortliche (z. B. Vertrauenslehrer, SV) lesen die Nachrichten und können antworten. Mit einem zufälligen Code holt der Absender die Antwort ab und kann Rückfragen stellen, ohne dass jemand erfährt, wer er ist. So entsteht ein anonymer Chat-Verlauf.

---
## Inhaltsverzeichnis

- [Funktionen](#funktionen)
- [Was gespeichert wird (und was nicht)](#was-gespeichert-wird-und-was-nicht)
- [Schnellstart (Entwicklung)](#schnellstart-entwicklung)
- [Konfiguration](#konfiguration)
- [Befehle für Zugänge und Daten](#befehle-für-zugänge-und-daten)
- [Docker](#docker)
- [Beispiel: Reverse Proxy ohne Logs](#beispiel-reverse-proxy-ohne-logs)
- [Wartung](#wartung)
---

## Funktionen

**Für Schüler** 
- Nachricht mit Thema und Text abschicken.
- Danach erscheint ein einmaliger **Rückmeldecode** (z. B. `K7M2-XQ4P-...`). Damit lässt sich unter „Antwort abholen“ der Verlauf einsehen. Der Rückmeldecode kann zum Beispiel im Passwortmaanager (Google, Firefox, Bitwarden, KeePass) gespeichert werden.
- **Chat über den Code:** Schreibt ein Empfänger zurück oder hat Fragen, sieht der Absender das im Verlauf und kann dort antworten. Der Verlauf ist wie ein Postfach aufgebaut, nicht in Echtzeit: Beide Seiten müssen nachsehen (der Absender mit Code, „Aktualisieren“ lädt neu). Der Absender wird nicht benachrichtigt.
- Der Code wird nur als Hash gespeichert und nie in einer URL angezeigt. Geht er verloren, kann er nicht wiederhergestellt werden. Wer den Code kennt, kann den Verlauf lesen und mitschreiben.

**Für Empfänger** (eigener Zugang pro Person, unter `/verwaltung`)
- Eingang mit Filter nach Status (neu / in Bearbeitung / erledigt).
- Pro Nachricht: Verlauf lesen, dem Absender schreiben, Status ändern, interne Notiz.
- **Offene Rückfragen** erscheinen mit einem Hinweis oben im Eingang und bleiben markiert, bis ein Empfänger antwortet oder die Nachricht auf „erledigt“ setzt.
- Schreibt ein Absender nach „erledigt“ noch einmal, wird die Nachricht automatisch wieder auf „in Bearbeitung“ gesetzt.
- Im Verlauf erscheint für den Absender nur „Schule“, nicht, welche Person geantwortet hat.

Rollen: `admin` und `empfaenger`.

## Was gespeichert wird (und was nicht)

| Gespeichert | Nicht gespeichert |
|---|---|
| Nachrichtentext und Thema, Chat-Verlauf (Text, wer geschrieben hat: Absender oder Schule) | IP-Adresse |
| Datum (ohne Uhrzeit), auch bei Chat-Nachrichten | Uhrzeit, Browser, Gerät |
| Status, interne Notiz | Cookies oder Kennungen für Schüler |
| Hash des Rückmeldecodes | der Rückmeldecode selbst |
| Empfänger-Zugänge mit gehashten Passwörtern | Tracking, Statistik, externe Schriften |

Wichtig: Die Anwendung selbst schreibt keine IP-Adressen. **Webserver, Proxy und Firewall der Schule tun das aber oft von sich aus, kann aber ausgeschaltet werden.** Mehr dazu in
[Beispiel: Reverse-Proxy ohne Logs](#beispiel-reverse-proxy-ohne-logs).


**Für Schüler:** Alternativ kann man seine Nachricht über Mobile Daten senden. Die IP-Addressen von Mobilen Daten sind unter CGNAT und können nicht auf ein einzelnes Gerät zurückverfolgt werden.**

## Schnellstart (Entwicklung)

Voraussetzung: Python 3.10 oder neuer.

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Dann einen Admin anlegen und starten:

```bash
flask --app app create-user admin --role admin
flask --app app run
```

- Schüler-Formular: http://127.0.0.1:5000
- Verwaltung: http://127.0.0.1:5000/verwaltung/login/

Die Datenbank `postfach.db` entsteht beim ersten Start automatisch im aktuellen Arbeitsverzeichnis. Führe alle `flask`-Befehle deshalb immer im selben Ordner aus oder setze `DB_PATH` (siehe unten), **sonst legst du versehentlich eine zweite, leere Datenbank an**.

`flask run` ist nur für Tests auf dem eigenen Rechner gedacht, nicht für den echten Betrieb.

## Konfiguration

**Umgebungsvariablen**

| Variable | Bedeutung | Standard |
|---|---|---|
| `SECRET_KEY` | Schlüssel für Sitzungen und die Formular-Prüfung. Im Betrieb **Pflicht**, lang und zufällig. Generiert mit `openssl rand -base64 32` oder `python -c "import secrets; print(secrets.token_hex(32))"` | zufällig bei jedem Start |
| `HTTPS` | `1` setzt Cookies auf „nur über HTTPS“. Im Betrieb auf `1` stellen. | `0` |
| `DB_PATH` | Pfad zur SQLite-Datei | `postfach.db` |

Ohne festen `SECRET_KEY` werden Empfänger bei jedem Neustart ausgeloggt, und bei mehreren Gunicorn-Workern bekommt jeder einen eigenen Schlüssel, was zu zufälligen Abbrüchen führt.

## Befehle für Zugänge und Daten

Aufruf immer als `flask --app app <befehl>`, `--help` zeigt die Beschreibung. Gefährliche Befehle fragen nach, mit `--yes` entfällt die Rückfrage (z. B. für Cron).

**Zugänge**

| Befehl | Wirkung |
|---|---|
| `create-user NAME [--role admin\|empfaenger]` | neuen Zugang anlegen (Passwort mind. 10 Zeichen) |
| `list-users` | alle Zugänge anzeigen |
| `set-password NAME` | Passwort ändern |
| `rename-user ALT NEU` | Benutzernamen ändern |
| `set-role NAME admin\|empfaenger` | Rolle ändern |
| `remove-user NAME` | Zugang löschen |

Der **letzte Admin** kann weder gelöscht noch herabgestuft werden. Ein gelöschter Benutzer verliert seine laufende Sitzung beim nächsten Seitenaufruf. Nach einer Passwortänderung bleiben bereits laufende Sitzungen gültig; um alle sofort abzumelden, startest du mit einem neuen `SECRET_KEY` neu.

**Nachrichten und Datenbank**

| Befehl | Wirkung |
|---|---|
| `stats` | Anzahl nach Status und Thema, offene Rückfragen, Zeitraum, Anzahl Zugänge (keine Inhalte) |
| `delete-message ID` | eine Nachricht samt Chat-Verlauf löschen |
| `purge --days N [--only-done]` | Nachrichten löschen, die älter als N Tage sind (optional nur erledigte) |
| `clear-messages` | alle Nachrichten samt Verläufen löschen, Zugänge bleiben |
| `reset-db` | **alles** löschen (Nachrichten und Zugänge), Bestätigung durch Eintippen von `LOESCHEN` |
| `backup [DATEI]` | Sicherungskopie anlegen (nur für den Server-Nutzer lesbar) |

Beim Löschen werden die Inhalte in der Datei überschrieben und die Datenbank anschließend bereinigt, damit gelöschte Texte nicht in der Datei zurückbleiben.

## Docker

Die App wird mithilfe von Docker gehostet. Die Datenbank liegt im eigenen Volume damit sie nicht beim container-neustart gelöscht wird.

**1. Einrichtung**

```bash
cp .env.example .env
docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_hex(32))" # oder 'openssl rand -base64 32'
```

Den ausgegebenen Wert in `.env` bei `SECRET_KEY=` eintragen.

**2. Starten**

```bash
docker compose up -d --build
docker compose ps # Status sollte nach kurzer Zeit "healthy" zeigen
```

**3. Ersten Admin anlegen**

```bash
docker compose exec postfach flask --app app create-user anna --role admin
```

**Wichtig: ist der Benutzer nicht in der 'docker' Gruppe, müssen die Befehle mit `sudo` oder als root ausgeführt werden.**

Alle Befehle aus dem Abschnitt „Befehle für Zugänge und Daten“ funktionieren genauso, mit `docker compose exec postfach flask --app app <Befehl>` davor.

**4. Aufrufen:** Formular unter http://localhost:8000, Verwaltung unter http://localhost:8000/verwaltung/login.

**Im Betrieb:** `HTTPS=1` setzen und `BIND=127.0.0.1` lassen. Davor kommt wie unten beschrieben nginx oder Apache mit Zertifikat und ohne Zugriffslog, der auf `http://127.0.0.1:8000` weiterleitet. Der Abschnitt zu systemd und Gunicorn entfällt dann, Docker übernimmt Start und Neustart (`restart: unless-stopped`).

## Beispiel: Reverse Proxy ohne Logs

**Für nginx:**

```nginx
server {
    listen 443 ssl;
    server_name postfach.example.com;
    # ssl_certificate / ssl_certificate_key hier eintragen

    access_log off; # keine IP-Adressen loggen
    error_log /var/log/nginx/postfach-error.log crit;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        # X-Forwarded-For wird absichtlich nicht weitergegeben
    }
}
```

Bei anderen Proxies wie Apache oder Caddy muss man die jeweilige Konfiguration anpassen.

## Wartung

- **Backups:** `flask --app app backup` legt eine Kopie an. Sie enthält alle Nachrichten und gehört genauso geschützt wie die Datenbank. 
- **Alte Nachrichten automatisch löschen** (Datensparsamkeit), z. B. jeden Sonntag um 3 Uhr per Cron:

  ```
  0 3 * * 0 cd /opt/schulpostfach && DB_PATH=/var/lib/schulpostfach/postfach.db venv/bin/flask --app app purge --days 180 --only-done --yes
  ```
- **Alle Empfänger abmelden:** `SECRET_KEY` ändern und neu starten.