# Schul-Postfach

Anonymes digitales Postfach für Schüler: Probleme und Feedback melden, ohne Account und ohne gespeicherte IP-Adresse. Die zuständigen Empfänger lesen die Nachrichten, antworten und werden per E-Mail benachrichtigt. Mit einem zufälligen Code holt der Absender die Antwort ab und kann Rückfragen stellen (anonymer Chat-Verlauf).

Technik: Python, Flask, SQLite, Podman (rootless). Keine externen Dienste, kein Tracking.

## Inhaltsverzeichnis

- [Funktionen](#funktionen)
- [Was gespeichert wird](#was-gespeichert-wird)
- [Hosting: Schritt für Schritt](#hosting-schritt-für-schritt)
- [Rollen, Empfänger und Bereiche](#rollen-empfänger-und-bereiche)
- [E-Mail-Benachrichtigung](#e-mail-benachrichtigung)
- [Konfiguration](#konfiguration)
- [Befehle](#befehle)
- [Lokal entwickeln und testen](#lokal-entwickeln-und-testen)
- [Wartung](#wartung)

## Funktionen

**Schüler** (ohne Anmeldung): Empfänger wählen (z. B. Schülervertretung oder Schulsozialarbeit), Thema wählen, Nachricht schreiben. Danach erscheint ein einmaliger **Rückmeldecode** (im Passwortmanager speicherbar). Unter „Antwort abholen“ sieht man den Verlauf und kann Rückfragen stellen. Kein Echtzeit-Chat, der Absender wird nicht benachrichtigt. Ein verlorener Code kann nicht wiederhergestellt werden.

**Empfänger** (eigener Zugang unter `/verwaltung`): Eingang mit Statusfilter, Verlauf lesen, antworten, Status ändern, interne Notiz. Offene Rückfragen sind markiert. Jeder Empfänger sieht **nur die Nachrichten seines Bereichs**. Der Absender sieht nur „Schule“, nicht wer geantwortet hat. **Admins** sehen keine Nachrichten, sondern die Liste der Zugänge.

## Was gespeichert wird

| Gespeichert | Nicht gespeichert |
|---|---|
| Nachricht, Thema, gewählter Empfänger, Chat-Verlauf | IP-Adresse, Uhrzeit, Browser, Gerät |
| Datum (ohne Uhrzeit), Status, interne Notiz | Cookies oder Kennungen für Schüler |
| Hash des Rückmeldecodes | der Rückmeldecode selbst |
| Zugänge: gehashtes Passwort, Rolle, Bereich, E-Mail | Tracking, Statistik, externe Schriften |

Die Anwendung schreibt keine IP-Adressen, **Webserver, Proxy und Firewall tun das aber oft von sich aus** (siehe Hosting, Schritt 5). Der Text einer Nachricht kann den Absender verraten, und wer Zugriff auf Server oder Datenbank hat (z. B. root auf dem Server), kann alles lesen. Schüler können auch über mobile Daten senden, deren IP-Adressen liegen hinter CGNAT.

## Hosting: Schritt für Schritt

**So läuft es:** Browser → Reverse Proxy (nginx/Apache, HTTPS, ohne Logs) → Podman-Container (Gunicorn + Flask, Port 8000) → Datenbank im Volume. Der Container läuft **rootless** unter einem eigenen Benutzer: Der Betreiber verwaltet nur seinen Dienst, ohne Root-Rechte auf dem Server. Nur Schritt 1 braucht root.

**Voraussetzungen:** Linux-Server mit Podman ab Version 4.4 (wegen Quadlet) · Adresse mit HTTPS-Zertifikat (`postfach.beispiel-schule.at` oder Unterpfad `/postfach`) · Reverse Proxy der Schul-IT · für Mails: SMTP-Zugangsdaten vom Admin.

**Schritt 1: Dienst-Benutzer anlegen** (einmalig, Schul-IT mit root)
```bash
sudo useradd -m postfach
grep postfach /etc/subuid /etc/subgid      # beide Zeilen müssen vorhanden sein (sonst per usermod --add-subuids/--add-subgids ergänzen)
sudo loginctl enable-linger postfach       # Dienst läuft ohne Login und startet nach einem Neustart
```

Ab jetzt alles als Benutzer `postfach`, per SSH-Login (nicht mit `su`, sonst fehlt die systemd-Sitzung).

**Schritt 2: Code und Einstellungen**

```bash
git clone <Repository-URL> schulpostfach && cd schulpostfach     # oder ZIP entpacken
cp .env.example .env
podman run --rm python:3.12-slim python -c "import secrets; print(secrets.token_hex(32))"   # Wert für SECRET_KEY
nano .env
```

Mindestens diese Werte in die `.env` (`BASE_URL` steht als Link in den Mails, alle Variablen: [Konfiguration](#konfiguration)):

```
SECRET_KEY=<erzeugter Wert>
HTTPS=1
BASE_URL=https://postfach.beispiel-schule.at
# nur bei Betrieb unter einem Unterpfad:
# COOKIE_PATH=/postfach
```

**Schritt 3: Image bauen und als Dienst starten** (Quadlet, systemd)
```bash
podman build -t localhost/schulpostfach:latest .
mkdir -p ~/.config/containers/systemd && cp podman/* ~/.config/containers/systemd/
nano ~/.config/containers/systemd/postfach.container     # Pfad bei EnvironmentFile= prüfen
systemctl --user daemon-reload && systemctl --user start postfach
systemctl --user status postfach                         # "active (running)", Logs: podman logs postfach
```

Der Dienst startet nach einem Neustart automatisch. Der Port ist in `postfach.container` fest auf `127.0.0.1:8000` gesetzt, nur der Proxy erreicht ihn.

**Schritt 4: Zugänge anlegen** (je Person einer, siehe [Rollen, Empfänger und Bereiche](#rollen-empfänger-und-bereiche))
```bash
podman exec -it postfach flask --app app create-user anna --section sv --email anna@beispiel-schule.at
```

**Schritt 5: Reverse Proxy mit HTTPS, ohne IP-Logs** (nginx, Betrieb durch die Schul-IT)
```nginx
server {
    listen 443 ssl;                          # ssl_certificate / ssl_certificate_key hier eintragen
    server_name postfach.beispiel-schule.at;
    access_log off;                          # keine IP-Adressen loggen
    error_log /var/log/nginx/postfach-error.log crit;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;   # X-Forwarded-For bewusst nicht weitergeben
    }
}
```

Unter einem Unterpfad (`https://server/postfach`): im Block oben `location /` ersetzen, `COOKIE_PATH=/postfach` in die `.env` setzen:

```nginx
location /postfach/ {                                  # statt: location /
    proxy_pass http://127.0.0.1:8000/;                 # der Schrägstrich am Ende entfernt den Pfad
    proxy_set_header X-Forwarded-Prefix /postfach;     # zusätzlich zu Host und X-Forwarded-Proto
}
```

**Schritt 6: Mailversand einrichten und testen** → [E-Mail-Benachrichtigung](#e-mail-benachrichtigung)

**Checkliste vor dem Start**

- [ ] `SECRET_KEY` gesetzt, `.env` liegt nicht im Repository, `HTTPS=1`, Seite nur über HTTPS erreichbar
- [ ] Der Dienst-Benutzer hat keine sudo-Rechte, sein Home ist für andere Benutzer gesperrt (dort liegt die Datenbank)
- [ ] **Keine IP-Logs:** `access_log off`, außerdem Logs im `server`-/`http`-Block und die Firewall prüfen (das Fehlerlog lässt sich nicht pro `location` abschalten). Test: Seite aus dem Mobilfunknetz aufrufen und die IT in den Logs nach dieser IP suchen lassen
- [ ] Zugänge mit Bereichen angelegt, Testmail erfolgreich
- [ ] Mit der Schulleitung geklärt: Datenschutz, wer Zugriff auf Server und Backups hat

**Updates:** `git pull && podman build -t localhost/schulpostfach:latest . && systemctl --user restart postfach`. Die Daten bleiben im Volume, `podman volume rm postfach-data` löscht dagegen auch die Datenbank.

## Rollen, Empfänger und Bereiche

Jeder Zugang hat eine **Rolle**: **Empfänger** hat genau einen **Bereich** (`sv` oder `sozial`), sieht nur dessen Nachrichten und bekommt nur dafür Mails. **Admin** hat keinen Bereich, sieht keine Nachrichten und bekommt keine Benachrichtigungen. Er sieht die Liste der Zugänge und Hinweise, z. B. wenn für einen Bereich keine E-Mail-Adresse hinterlegt ist. Fremde Nachrichten sind nicht aufrufbar (Fehler 404). Schüler wählen erst den **Empfänger**, dann ein **Thema** dazu. Empfänger (Schlüssel `sv`, `sozial`), Anzeigenamen, Hinweise und Themen stehen oben in `app.py` im Block `RECIPIENTS`. Zugänge legst du mit `create-user` und `set-section` an (siehe [Befehle](#befehle)).

- **Neuer Bereich:** Eintrag in `RECIPIENTS` ergänzen und neu bauen. Schlüssel nicht mehr umbenennen, sobald Nachrichten existieren.
- **Update einer älteren Datenbank:** Admins verlieren ihren Bereich, Empfänger mit mehreren behalten den ersten. Zum Testen einen Empfänger-Zugang anlegen, ein Admin sieht keine Nachrichten.

## E-Mail-Benachrichtigung

- Täglich zur Uhrzeit `NOTIFY_AT` (Standard 07:00) prüft die Anwendung auf neue Nachrichten oder Rückfragen. Gibt es welche, geht **eine Sammelmail** an die Empfänger des betroffenen Bereichs, sonst **passiert nichts**.
- Jeder erfährt nur etwas über **seinen Bereich**. Die Mail enthält **keine Inhalte**, nur Anzahl, Bereich und Link zur Verwaltung. Eine Sammelmail statt Sofortmail, weil sonst die genaue Uhrzeit einer Einreichung verraten würde.
- Bei Fehlern gibt es bis zu 6 Wiederholungen im Stundenabstand. Hat für einen Bereich niemand eine Adresse, wird nachgeholt, sobald eine hinterlegt ist.
- Läuft im Gunicorn-Prozess mit **einem** Worker (wie im Dockerfile). Ohne `SMTP_HOST`/`SMTP_FROM` startet es nicht, der Grund steht im Log (`[notify]`).

**Einrichten:** Daten vom Schul-Admin in die `.env`, dann `systemctl --user restart postfach`. Bei einem Relay ohne Login `SMTP_USER`/`SMTP_PASSWORD` weglassen (meist Port 25, `none`).

```
SMTP_HOST=mail.beispiel-schule.at
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USER=postfach@beispiel-schule.at
SMTP_PASSWORD=...
SMTP_FROM=postfach@beispiel-schule.at
```

**Testen:** `podman exec -it postfach flask --app app test-mail meine.adresse@beispiel.at` schickt eine Testmail, `send-notifications --dry-run` zeigt, was gesendet würde. Fehlermeldungen: *Connection refused* = Host/Port/Firewall, *Authentication failed* = Login, *certificate verify failed* = internes Zertifikat, *Relay access denied* = Absender bzw. Server-IP nicht freigegeben.

- **Microsoft 365:** SMTP mit Passwort wird laut Ankündigung Ende Dezember 2026 standardmäßig abgeschaltet (Stand November 2026, bitte prüfen). Dann einen IP-basierten SMTP-Relay verwenden, OAuth wird nicht unterstützt.
- **Ohne echte Mails testen:** `docker-compose.override.yml` startet Mailpit (Mails unter http://localhost:8025). Nur für den eigenen Rechner, nie auf den Server.

## Konfiguration

Umgebungsvariablen in der `.env` (Vorlage: `.env.example`), `SECRET_KEY` und `SMTP_PASSWORD` **nie ins Repository**. Weitere Einstellungen (`MIN_WORDS`, Chat-Limits) stehen oben in `app.py`.

| Variable | Bedeutung | Standard |
|---|---|---|
| `SECRET_KEY` | Schlüssel für Sitzungen, im Betrieb **Pflicht** | zufällig je Start |
| `HTTPS` | `1` = Cookies nur über HTTPS | `0` |
| `BASE_URL` | Öffentliche Adresse (Link in den Mails) | `http://localhost:8000` |
| `COOKIE_PATH` | Cookie-Pfad, bei Unterpfad z. B. `/postfach` | `/` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` | Mailserver, Sicherheit `starttls`, `ssl` oder `none` | leer, `587`, `starttls` |
| `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Login (falls nötig) und Absenderadresse | leer |
| `NOTIFY_AT`, `NOTIFY_TZ` | Uhrzeit(en) des Mailversands (`07:00` oder `07:00,15:00`, leer = aus), Zeitzone | `07:00`, `Europe/Vienna` |

## Befehle

Aufruf als `flask --app app <befehl>`, im Container mit `podman exec -it postfach` davor. Gefährliche Befehle fragen nach, `--yes` überspringt die Rückfrage.

| Befehl | Wirkung |
|---|---|
| `create-user NAME [--role admin\|empfaenger] [--section S] [--email ADRESSE]` | Zugang anlegen (Empfänger brauchen `--section` = Bereich, Admins haben keine; Passwort mind. 10 Zeichen) |
| `list-users`, `remove-user NAME`, `set-password NAME`, `rename-user ALT NEU` | Zugänge anzeigen, löschen (letzter Admin geschützt), Passwort, Namen ändern |
| `set-role NAME ROLLE [--section S]` / `set-section NAME S` / `set-email NAME [ADRESSE]` | Rolle, Section bzw. E-Mail ändern (E-Mail ohne Angabe: entfernen) |
| `test-mail ADRESSE` / `send-notifications [--dry-run]` | Testmail / Sammelmail von Hand auslösen |
| `delete-message ID` / `purge --days N [--only-done]` | einzelne bzw. alte Nachrichten samt Verlauf löschen |
| `clear-messages` / `reset-db` | alle Nachrichten / **alles** löschen (Bestätigung `LOESCHEN`) |
| `stats` / `backup [DATEI]` | Zahlen je Empfänger, Status, Thema (keine Inhalte) / Sicherungskopie |

## Lokal entwickeln und testen

Mit Compose (Podman oder Docker): `cp .env.example .env`, `SECRET_KEY` eintragen, dann `podman compose up -d --build` (bzw. `docker compose ...`), Formular unter http://localhost:8000. Die mitgelieferte `docker-compose.override.yml` startet dabei auch Mailpit. Ohne Container (Python 3.10+):

```bash
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app app create-user anna --section sv && flask --app app run     # http://127.0.0.1:5000, nur zum Testen
```

Führe `flask`-Befehle immer im selben Ordner aus oder setze die Variable `DB_PATH`, **sonst entsteht eine zweite, leere Datenbank**. Änderungen an `app.py`, `templates/` oder `static/` brauchen bei Containern einen neuen Build, Änderungen an der `.env` nur einen Neustart.

## Wartung

- **Backups:** `podman exec postfach flask --app app backup /data/backup.db`, dann `podman cp postfach:/data/backup.db .`. Die Kopie enthält alle Nachrichten und gehört genauso geschützt wie die Datenbank.
- **Alte Nachrichten löschen** (Datensparsamkeit), z. B. sonntags um 3 Uhr per `crontab -e` des Dienst-Benutzers: `0 3 * * 0 podman exec postfach flask --app app purge --days 180 --only-done --yes`
- **Logs prüfen:** `podman logs postfach` oder `journalctl --user -u postfach` (Mailversand: Zeilen mit `[notify]`). Alle Zugänge abmelden: `SECRET_KEY` ändern und neu starten.
