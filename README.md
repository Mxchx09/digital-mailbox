# Schul-Postfach

Anonymes Postfach, über das Schüler:innen Probleme und Feedback melden können.
Festgelegte Ansprechpartner – zum Beispiel die Schülervertretung oder die
Schulsozialarbeit – lesen die Nachrichten und antworten darauf.
Mit einem zufällig generierten Code kann der Absender Antworten abrufen und
Rückfragen stellen.
Der Austausch bleibt dabei anonym: Namen, IP-Adressen und Geräteinformationen
werden nicht gespeichert.
Zuständige Empfänger erhalten Status-Updates per E-Mail.

## Inhaltsverzeichnis

- [Umgebungsvariablen](#umgebungsvariablen)
- [Docker](#docker)
  - [Einrichtung und Start](#einrichtung-und-start)
  - [Zugang anlegen](#zugang-anlegen)
  - [CLI-Befehle im Container](#cli-befehle-im-container)
  - [Zugänge](#zugänge)
  - [Nachrichten und Datenbank](#nachrichten-und-datenbank)
  - [Alle Empfänger abmelden](#alle-empfänger-abmelden)
- [Entwicklung](#entwicklung)
  - [Linux / macOS](#linux--macos)
  - [Windows PowerShell](#windows-powershell)
  - [Anwendung starten](#anwendung-starten)
  - [Linux / macOS](#linux--macos-1)
  - [Windows PowerShell](#windows-powershell-1)
  - [Tests ausführen](#tests-ausführen)

## Umgebungsvariablen

Die Anwendung liest Werte aus der Umgebung. Diese können in der Shell
oder der `.env` Datei gesetzt werden.

| Variable | Beschreibung | Standard lokal | Standard Docker |
|---|---|---:|---:|
| `SECRET_KEY` | Schlüssel für Sitzungen und Formularschutz. Im Betrieb einen festen, zufälligen Wert setzen. | zufällig bei jedem Start | erforderlich |
| `HTTPS` | Setzt Sitzungs-Cookies auf „nur über HTTPS“. | `0` | `0` |
| `DB_PATH` | Pfad zur SQLite-Datenbank. | `postfach.db` | `/data/postfach.db` |
| `COOKIE_PATH` | Pfad für das Login-Cookie, z. B. `/postfach` bei einem Unterpfad. | `/` | `/` |
| `BASE_URL` | Öffentliche Basisadresse für Links in Benachrichtigungs-E-Mails. | `http://localhost:8000` | `http://localhost:8000` |
| `SMTP_HOST` | Hostname des SMTP-Servers. Leer: kein E-Mail-Versand. | leer | leer |
| `SMTP_PORT` | SMTP-Port. | `587` | `587` |
| `SMTP_SECURITY` | Verschlüsselung: `starttls`, `ssl` oder `none`. | `starttls` | `starttls` |
| `SMTP_USER` | SMTP-Benutzername, falls erforderlich. | leer | leer |
| `SMTP_PASSWORD` | SMTP-Passwort, falls erforderlich. | leer | leer |
| `SMTP_FROM` | Absenderadresse für Benachrichtigungen. | leer | leer |
| `NOTIFY_AT` | Versandzeiten, z. B. `07:00` oder `07:00,15:00`. Leer: deaktiviert. | leer | `07:00` |
| `NOTIFY_TZ` | Zeitzone für `NOTIFY_AT`. | `Europe/Vienna` | `Europe/Vienna` |

## Docker

### Einrichtung und Start

```bash
cp .env.example .env
```

Danach `SECRET_KEY` in `.env` durch einen festen zufälligen Wert ersetzen:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Image bauen und Container starten:

```bash
docker compose up -d --build
docker compose ps
```

### Zugang anlegen

```bash
docker compose exec postfach \
  flask --app app create-user admin --role admin
```

Die Anwendung ist danach erreichbar unter:

- Formular: <http://localhost:8000>
- Verwaltung: <http://localhost:8000/verwaltung/login>

### CLI-Befehle im Container

Alle CLI-Befehle aus dem nächsten Abschnitt werden im Container so ausgeführt:

```bash
docker compose exec postfach flask --app app <BEFEHL>
```

Beispiel:

```bash
docker compose exec postfach \
  flask --app app list-users
```

Die Datenbank liegt im persistenten Docker-Volume `postfach-data`.
Für Backups im Container muss ein beschreibbarer Pfad unter `/data` verwendet
und die Datei anschließend aus dem Volume kopiert werden:

```bash
docker compose exec postfach \
  flask --app app backup /data/postfach-backup.db
docker cp "$(docker compose ps -q postfach)":/data/postfach-backup.db ./postfach-backup.db
```

### Zugänge

```bash
# Zugang anlegen; das Passwort wird interaktiv abgefragt.
flask --app app create-user NAME

# Admin anlegen
flask --app app create-user NAME --role admin

# Zugang mit E-Mail-Adresse und Bereichen anlegen
flask --app app create-user NAME \
  --email NAME@beispiel.at \
  --section sv \
  --section sozial

# Alle Zugänge anzeigen
flask --app app list-users

# Passwort ändern; interaktive Abfrage
flask --app app set-password NAME

# Benutzernamen ändern
flask --app app rename-user ALT NEU

# Rolle ändern
flask --app app set-role NAME admin
flask --app app set-role NAME empfaenger

# Bereiche festlegen; ohne Bereich sieht der Zugang keine Nachrichten
flask --app app set-sections NAME sv sozial direktion
flask --app app set-sections NAME

# E-Mail-Adresse setzen oder entfernen
flask --app app set-email NAME NAME@beispiel.at
flask --app app set-email NAME

# Zugang löschen; fragt standardmäßig nach
flask --app app remove-user NAME
flask --app app remove-user NAME --yes
```

Bereiche: `sv`, `sozial` und `direktion`

Rollen: `admin` und `empfaenger`.

### Nachrichten und Datenbank

```bash
# Übersicht ohne Nachrichteninhalte
flask --app app stats

# Eine Nachricht anhand ihrer ID löschen
flask --app app delete-message ID
flask --app app delete-message ID --yes

# Nachrichten löschen, die älter als N Tage sind
flask --app app purge --days N
flask --app app purge --days N --only-done
flask --app app purge --days N --only-done --yes

# Alle Nachrichten löschen, Zugänge behalten
flask --app app clear-messages
flask --app app clear-messages --yes

# Nachrichten und Zugänge löschen
flask --app app reset-db
flask --app app reset-db --yes

# Datenbank sichern; Ziel ist optional
flask --app app backup
flask --app app backup ./postfach-backup.db
```

Löschbefehle fragen standardmäßig nach einer Bestätigung. Mit `--yes` wird
die Rückfrage übersprungen.

### Alle Empfänger abmelden

`SECRET_KEY` ändern und den Dienst neu starten:

```bash
docker compose up -d
```

## Entwicklung

Voraussetzung: Python 3.10 oder neuer.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Anwendung starten

Alle Befehle müssen aus demselben Projektordner ausgeführt werden. Alternativ
kann mit `DB_PATH` ein absoluter Datenbankpfad angegeben werden.

```bash
flask --app app create-user admin --role admin
flask --app app run
```

Die Anwendung ist danach erreichbar unter:

- Formular: <http://127.0.0.1:5000>
- Verwaltung: <http://127.0.0.1:5000/verwaltung/login/>

`flask run` ist nur für die lokale Entwicklung vorgesehen.

## Tests

Tests-dependencies (`pytest`) installieren:

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
### Tests ausführen

Im Projektordner:

```bash
pytest
```
