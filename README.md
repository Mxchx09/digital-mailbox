# Schul-Postfach

Anonymes digitales Postfach für Schüler: Probleme und Feedback melden. Ausgewählte Verantwortliche (z. B. Vertrauenslehrer, SV) lesen die Nachrichten und können antworten. Mit einem zufälligen Code holt der Absender die Antwort ab und kann Rückfragen stellen, ohne dass jemand erfährt, wer er ist. So entsteht ein anonymer Chat-Verlauf. Die zuständigen Empfänger werden per E-Mail benachrichtigt, wenn es etwas Neues gibt (ohne dass Inhalte in der Mail stehen).

---

## Inhaltsverzeichnis

- [Funktionen](#funktionen)
- [Was gespeichert wird (und was nicht)](#was-gespeichert-wird-und-was-nicht)
- [Schnellstart (Entwicklung)](#schnellstart-entwicklung)
- [Konfiguration](#konfiguration)
- [Empfänger und Bereiche](#empfänger-und-bereiche)
- [E-Mail-Benachrichtigung](#e-mail-benachrichtigung)
- [Befehle für Zugänge und Daten](#befehle-für-zugänge-und-daten)
- [Docker](#docker)
- [Beispiel: Reverse Proxy ohne Logs](#beispiel-reverse-proxy-ohne-logs)
- [Wartung](#wartung)

---

## Funktionen

**Für Schüler**

- Zuerst den **Empfänger** wählen (z. B. Schülervertretung oder Schulsozialarbeit), dann das passende **Thema**, und die Nachricht abschicken. Nur der gewählte Empfänger kann sie lesen.
- Danach erscheint ein einmaliger **Rückmeldecode** (z. B. `K7M2-XQ4P-...`). Damit lässt sich unter „Antwort abholen“ der Verlauf einsehen. Der Rückmeldecode kann zum Beispiel im Passwortmanager (Google, Firefox, Bitwarden, KeePass) gespeichert werden.
- **Chat über den Code:** Schreibt ein Empfänger zurück oder hat Fragen, sieht der Absender das im Verlauf und kann dort antworten. Der Verlauf ist wie ein Postfach aufgebaut, nicht in Echtzeit: Beide Seiten müssen nachsehen (der Absender mit Code, „Aktualisieren“ lädt neu). Der Absender wird nicht benachrichtigt.
- Der Code wird nur als Hash gespeichert und nie in einer URL angezeigt. Geht er verloren, kann er nicht wiederhergestellt werden. Wer den Code kennt, kann den Verlauf lesen und mitschreiben.

**Für Empfänger** (eigener Zugang pro Person, unter `/verwaltung`)

- Eingang mit Filter nach Status (neu / in Bearbeitung / erledigt).
- Pro Nachricht: Verlauf lesen, dem Absender schreiben, Status ändern, interne Notiz.
- **Offene Rückfragen** erscheinen mit einem Hinweis oben im Eingang und bleiben markiert, bis ein Empfänger antwortet oder die Nachricht auf „erledigt“ setzt.
- Schreibt ein Absender nach „erledigt“ noch einmal, wird die Nachricht automatisch wieder auf „in Bearbeitung“ gesetzt.
- Im Verlauf erscheint für den Absender nur „Schule“, nicht, welche Person geantwortet hat.
- **Jeder Zugang sieht nur die Nachrichten seiner Bereiche** (siehe [Empfänger und Bereiche](#empfänger-und-bereiche)). Fremde Nachrichten sind nicht aufrufbar.
- **Benachrichtigung per E-Mail:** Gibt es neue Nachrichten oder Rückfragen, bekommt jeder Empfänger eine kurze Sammelmail, aber nur zu seinen eigenen Bereichen und ohne Inhalte (siehe [E-Mail-Benachrichtigung](#e-mail-benachrichtigung)).

Rollen: `admin` und `empfaenger`. Beide sehen genau die Nachrichten ihrer zugewiesenen Bereiche, die Rolle `admin` gibt keinen zusätzlichen Einblick. Sie schützt nur davor, dass der letzte Admin gelöscht wird.

## Was gespeichert wird (und was nicht)

| Gespeichert | Nicht gespeichert |
|---|---|
| Nachrichtentext, Thema und gewählter Empfänger, Chat-Verlauf (Text, wer geschrieben hat: Absender oder Schule) | IP-Adresse |
| Datum (ohne Uhrzeit), auch bei Chat-Nachrichten | Uhrzeit, Browser, Gerät |
| Status, interne Notiz | Cookies oder Kennungen für Schüler |
| Hash des Rückmeldecodes | der Rückmeldecode selbst |
| Empfänger-Zugänge mit gehashten Passwörtern, E-Mail-Adresse und zugewiesenen Bereichen | Tracking, Statistik, externe Schriften |

Wichtig: Die Anwendung selbst schreibt keine IP-Adressen. **Webserver, Proxy und Firewall der Schule tun das aber oft von sich aus.** Mehr dazu in [Beispiel: Reverse-Proxy ohne Logs](#beispiel-reverse-proxy-ohne-logs). Die E-Mail-Adressen der Empfänger sind personenbezogene Daten; sie stehen in der Datenbank (und in Backups) und werden mit `remove-user` bzw. `set-email NAME` (ohne Adresse) gelöscht.

**Für Schüler:** Alternativ kann man seine Nachricht über Mobile Daten senden. Die IP-Adressen von mobilen Daten sind unter CGNAT und können nicht auf ein einzelnes Gerät zurückverfolgt werden.

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
| `COOKIE_PATH` | Pfad des Login-Cookies. Läuft die Seite hinter einem Proxy unter einem Unterpfad (z. B. `/postfach`), auf diesen Pfad setzen. | `/` |
| `BASE_URL` | Öffentliche Adresse der Seite. Wird als Link in den Benachrichtigungsmails verwendet, z. B. `https://service.htlinn.ac.at/postfach` | `http://localhost:8000` |
| `SMTP_HOST` | Mailserver für die Benachrichtigungen. Ohne Eintrag wird nichts verschickt. | leer |
| `SMTP_PORT` | Port des Mailservers | `587` |
| `SMTP_SECURITY` | `starttls`, `ssl` oder `none` | `starttls` |
| `SMTP_USER`, `SMTP_PASSWORD` | Login am Mailserver, falls nötig (bei einem Relay ohne Login leer lassen) | leer |
| `SMTP_FROM` | Absenderadresse, z. B. `postfach@beispiel-schule.at` | leer |
| `NOTIFY_AT` | Uhrzeit(en) des automatischen Versands, z. B. `07:00` oder `07:00,15:00`. Leer = kein automatischer Versand. In `docker-compose.yml` ist `07:00` voreingestellt. | leer |
| `NOTIFY_TZ` | Zeitzone für `NOTIFY_AT` | `Europe/Vienna` |

Ohne festen `SECRET_KEY` werden Empfänger bei jedem Neustart ausgeloggt, und bei mehreren Gunicorn-Workern bekommt jeder einen eigenen Schlüssel, was zu zufälligen Abbrüchen führt.

Die Mail-Zugangsdaten (`SMTP_PASSWORD`) gehören wie der `SECRET_KEY` nur in die `.env` auf dem Server und **nie ins Repository**. Eine Vorlage mit Platzhaltern steht in `.env.example`.

## Empfänger und Bereiche

Schüler wählen zuerst, **an wen** sie schreiben, und danach ein **Thema**, das zu diesem Empfänger passt. Die Empfänger und ihre Themen stehen oben in `app.py` im Block `RECIPIENTS`:

```python
RECIPIENTS = {
    "sv": {
        "label": "Schülervertretung",            # Anzeigename im Formular
        "hint": "Verwaltung / Allgemeines",      # Erklärung unter dem Dropdown
        "topics": ["Unterricht", "Organisation / Verwaltung", "Vorschläge / Feedback", "Sonstiges"],
    },
    "sozial": {
        "label": "Schulsozialarbeit (Maurice Kumar)",
        "hint": "Persönliches",
        "topics": ["Mobbing / Streit", "Persönliche Probleme", "Stress / Schule", "Sonstiges"],
    },
}
```

- **Neuen Empfänger ergänzen:** einen weiteren Eintrag hinzufügen (z. B. `"leitung"`) und neu bauen (`docker compose up -d --build`). Er erscheint automatisch im Formular.
- **Die Schlüssel** (`sv`, `sozial`) dürfen nicht mehr umbenannt werden, sobald Nachrichten existieren. Anzeigenamen, Hinweise und Themen kann man jederzeit ändern.

**Zugänge den Bereichen zuordnen**

Jeder Zugang sieht nur Nachrichten der Bereiche, die ihm zugewiesen sind, und bekommt auch nur dazu Mails:

```bash
flask --app app create-user maurice --email maurice@beispiel-schule.at --bereich sozial
flask --app app create-user anna --email anna@beispiel-schule.at --bereich sv
flask --app app create-user michael --role admin --bereich sv --bereich sozial   # beide Bereiche
flask --app app set-bereiche anna sv sozial                                     # später ändern
```

- Ein Zugang **ohne Bereich sieht nichts** und bekommt eine entsprechende Meldung im Eingang.
- Nachrichten anderer Bereiche sind nicht aufrufbar (Fehler 404), auch nicht zum Antworten.
- **Beim Update einer bestehenden Datenbank** bekommen alle vorhandenen Zugänge automatisch alle Bereiche, damit sich zunächst nichts ändert, und alte Nachrichten werden dem ersten Bereich zugeordnet. Danach kann man mit `set-bereiche` einschränken.
- Wer Zugriff auf den Server oder die Datenbankdatei hat (z. B. die Schul-IT), kann technisch alle Nachrichten lesen. Das sollte mit der Schulleitung geklärt sein.

## E-Mail-Benachrichtigung

Empfänger bekommen eine E-Mail, wenn es etwas Neues gibt.

**So funktioniert es**

- Täglich zur eingestellten Uhrzeit (`NOTIFY_AT`, in Docker standardmäßig 07:00 Uhr) prüft die Anwendung, ob es **neue Nachrichten oder neue Rückfragen von Absendern** gibt, die noch nicht gemeldet wurden.
- Gibt es etwas, geht **eine Sammelmail** an jeden betroffenen Empfänger. Gibt es nichts, wird **nichts verschickt**.
- Jeder bekommt nur Hinweise zu **seinen eigenen Bereichen**. Die Schulsozialarbeit erfährt nichts über Nachrichten an die Schülervertretung und umgekehrt.
- Hat für einen Bereich niemand eine E-Mail-Adresse, bleiben die Nachrichten ungemeldet und werden nachgeholt, sobald eine Adresse eingetragen ist.
- Schlägt der Versand fehl (z. B. Mailserver nicht erreichbar), wird bis zu 6-mal im Abstand von einer Stunde wiederholt. Die Nachrichten gelten erst nach erfolgreichem Versand als gemeldet.
- Der automatische Versand läuft im Gunicorn-Prozess der Anwendung. Er startet nur, wenn `SMTP_HOST` und `SMTP_FROM` gesetzt sind und `NOTIFY_AT` eine gültige Uhrzeit enthält, sonst steht der Grund im Log. Dafür darf nur **ein** Gunicorn-Worker laufen (`-w 1`, wie im Dockerfile). Bei `flask run` und bei `flask`-Befehlen startet er nicht.

**Die Mail enthält bewusst keine Inhalte**, nur Anzahl und Bereich sowie einen Link zur Verwaltung:

```
Betreff: Neues im Schul-Postfach

Im Schul-Postfach gibt es Neues (neue oder aktualisierte Nachrichten):
- Schulsozialarbeit (Maurice Kumar): 2

Bitte melde dich an: https://service.htlinn.ac.at/postfach/verwaltung

Aus Datenschutzgruenden enthaelt diese Mail keine Inhalte.
```

E-Mails sind unverschlüsselt und liegen auf Mailservern und Handys. Außerdem verrät eine Sofortmail die genaue Uhrzeit einer Einreichung, die die Anwendung sonst bewusst nicht speichert. Deshalb gibt es eine tägliche Sammelmail statt einer Mail pro Nachricht.

**Einrichten**

1. Vom Admin der Schule bekommst du Mailserver, Port, Verschlüsselung, ggf. Login und eine Absenderadresse. Die Werte kommen in die `.env` auf dem Server:

   ```
   # Relay ohne Login (z. B. nur für die IP des Servers freigegeben)
   SMTP_HOST=mail.beispiel-schule.at
   SMTP_PORT=25
   SMTP_SECURITY=none
   SMTP_FROM=postfach@beispiel-schule.at
   BASE_URL=https://service.htlinn.ac.at/postfach
   ```

   ```
   # oder mit Login über STARTTLS
   SMTP_HOST=mail.beispiel-schule.at
   SMTP_PORT=587
   SMTP_SECURITY=starttls
   SMTP_USER=postfach@beispiel-schule.at
   SMTP_PASSWORD=das-passwort-vom-admin
   SMTP_FROM=postfach@beispiel-schule.at
   BASE_URL=https://service.htlinn.ac.at/postfach
   ```

   Port 465 nutzt `SMTP_SECURITY=ssl`. Danach `docker compose up -d`. Auf dem Server darf **keine** `docker-compose.override.yml` liegen (die startet Mailpit, siehe unten).

2. E-Mail-Adresse und Bereiche pro Empfänger festlegen (bei neuen Zugängen schon beim Anlegen, siehe [Empfänger und Bereiche](#empfänger-und-bereiche)):

   ```bash
   flask --app app set-email anna anna@beispiel-schule.at
   flask --app app set-bereiche anna sv
   ```

3. Testmail schicken und prüfen:

   ```bash
   flask --app app test-mail meine.adresse@beispiel.at
   flask --app app send-notifications --dry-run   # zeigt, was gesendet würde
   ```

Mit `flask --app app send-notifications` lässt sich der Versand auch von Hand auslösen. Den automatischen Lauf zeigt das Log (`docker compose logs postfach`, Zeilen mit `[notify]`).

**Hinweise zum Mailserver:** Gerade bei Microsoft 365 / Exchange Online sollte der Admin vorab prüfen, ob Versand per Benutzername und Passwort (SMTP AUTH, „Basic Authentication“) erlaubt ist. Microsoft hat angekündigt, diese Anmeldung Ende Dezember 2026 für bestehende Mandanten standardmäßig abzuschalten, und unterstützt dann nur noch OAuth, was diese Anwendung nicht kann (Stand November 2026, bitte aktuell prüfen). Ein IP-basierter SMTP-Relay ist davon nicht betroffen. Damit die Mails nicht im Spam landen, sollte der Admin SPF und DKIM für die Absenderadresse einrichten.

**Fehlersuche bei `test-mail`**

| Meldung | Bedeutung |
|---|---|
| `SMTP_HOST und SMTP_FROM sind nicht gesetzt` | Die `.env` wird nicht gelesen oder die Werte fehlen. |
| `Connection refused` / `timed out` | Falscher Host oder Port, oder die Firewall blockiert den Server. |
| `certificate verify failed` | Der Server nutzt ein internes Zertifikat. Der Admin soll ein gültiges bereitstellen. |
| `Authentication failed` | Benutzername oder Passwort stimmt nicht. |
| `Relay access denied` / `550 ...` | Der Mailserver erlaubt diesen Absender oder diese Server-IP nicht. |

**Testen ohne echte Mails (Mailpit)**

Die mitgelieferte Datei `docker-compose.override.yml` startet zusätzlich den Mail-Fänger Mailpit und richtet die Anwendung darauf aus. Docker lädt sie automatisch. Alle Mails erscheinen dann unter http://localhost:8025, es wird nichts echt verschickt. Die Datei steht in `.gitignore` und gehört **nur auf den eigenen Rechner**. Ausschalten: Datei umbenennen und `docker compose up -d --remove-orphans` ausführen. Zum schnellen Testen setzt man in der `.env` `NOTIFY_AT` auf eine Uhrzeit in ein paar Minuten (oder ruft `send-notifications` von Hand auf).

## Befehle für Zugänge und Daten

Aufruf immer als `flask --app app <befehl>`, `--help` zeigt die Beschreibung. Gefährliche Befehle fragen nach, mit `--yes` entfällt die Rückfrage (z. B. für Cron).

**Zugänge**

| Befehl | Wirkung |
|---|---|
| `create-user NAME [--role admin\|empfaenger] [--email ADRESSE] [--bereich BEREICH]...` | neuen Zugang anlegen (Passwort mind. 10 Zeichen). `--bereich` kann mehrfach angegeben werden. |
| `list-users` | alle Zugänge mit E-Mail-Adresse und Bereichen anzeigen |
| `set-password NAME` | Passwort ändern |
| `rename-user ALT NEU` | Benutzernamen ändern |
| `set-role NAME admin\|empfaenger` | Rolle ändern |
| `remove-user NAME` | Zugang löschen |
| `set-bereiche NAME [BEREICH...]` | legt fest, welche Bereiche ein Zugang sieht und gemeldet bekommt (ohne Angabe: keine) |
| `set-email NAME [ADRESSE]` | E-Mail-Adresse setzen (ohne Adresse: entfernen, dann gibt es keine Benachrichtigung) |

Der **letzte Admin** kann weder gelöscht noch herabgestuft werden. Ein gelöschter Benutzer verliert seine laufende Sitzung beim nächsten Seitenaufruf. Nach einer Passwortänderung bleiben bereits laufende Sitzungen gültig; um alle sofort abzumelden, startest du mit einem neuen `SECRET_KEY` neu.

**Nachrichten und Datenbank**

| Befehl | Wirkung |
|---|---|
| `stats` | Anzahl nach Empfänger, Status und Thema, offene Rückfragen, Zeitraum, Anzahl Zugänge (keine Inhalte) |
| `delete-message ID` | eine Nachricht samt Chat-Verlauf löschen |
| `purge --days N [--only-done]` | Nachrichten löschen, die älter als N Tage sind (optional nur erledigte) |
| `clear-messages` | alle Nachrichten samt Verläufen löschen, Zugänge bleiben |
| `reset-db` | **alles** löschen (Nachrichten und Zugänge), Bestätigung durch Eintippen von `LOESCHEN` |
| `backup [DATEI]` | Sicherungskopie anlegen (nur für den Server-Nutzer lesbar) |

**E-Mail**

| Befehl | Wirkung |
|---|---|
| `test-mail ADRESSE` | Testmail schicken, um die SMTP-Einstellungen zu prüfen |
| `send-notifications [--dry-run]` | Sammelmail für alle noch nicht gemeldeten Nachrichten von Hand auslösen (`--dry-run`: nur anzeigen) |

Beim Löschen werden die Inhalte in der Datei überschrieben und die Datenbank anschließend bereinigt, damit gelöschte Texte nicht in der Datei zurückbleiben.

## Docker

Die App wird mithilfe von Docker gehostet. Die Datenbank liegt im eigenen Volume, damit sie nicht beim Container-Neustart gelöscht wird.

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

**Wichtig: ist der Benutzer nicht in der 'docker' Gruppe, müssen die Befehle mit `sudo` bzw. als root ausgeführt werden.**

Alle Befehle aus dem Abschnitt „Befehle für Zugänge und Daten“ funktionieren genauso, mit `docker compose exec postfach flask --app app <Befehl>` davor.

**4. Aufrufen:** Formular unter http://localhost:8000, Verwaltung unter http://localhost:8000/verwaltung/login.

**Mail-Einstellungen** (`SMTP_...`, `BASE_URL`, `NOTIFY_AT`, `COOKIE_PATH`) werden aus der `.env` an den Container weitergegeben. Nach Änderungen an der `.env` genügt `docker compose up -d`. Änderungen an `app.py`, `templates/` oder `static/` brauchen `docker compose up -d --build`. Zum Testen der Mails siehe [E-Mail-Benachrichtigung](#e-mail-benachrichtigung).

**Im Betrieb:** `HTTPS=1` setzen und `BIND=127.0.0.1` lassen. Davor kommt wie unten beschrieben nginx oder Apache mit Zertifikat und ohne Zugriffslog, der auf `http://127.0.0.1:8000` weiterleitet. Docker übernimmt Start und Neustart (`restart: unless-stopped`).

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

**Unter einem Unterpfad (z. B. `https://service.htlinn.ac.at/postfach`)**

Die Anwendung übernimmt Pfad und Protokoll aus den `X-Forwarded-...`-Headern (`ProxyFix`, `X-Forwarded-For` wird bewusst nicht ausgewertet). Der Proxy gibt den Pfad weiter:

```nginx
location /postfach/ {
    access_log off;                          # wichtig auch bei einem gemeinsam genutzten Proxy
    proxy_pass http://127.0.0.1:8000/;       # der Schrägstrich am Ende entfernt den Pfad
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /postfach;
}
```

In der `.env`: `HTTPS=1`, `COOKIE_PATH=/postfach` und `BASE_URL=https://service.htlinn.ac.at/postfach`. Der Anwendungsport darf nur vom Proxy erreichbar sein (`BIND=127.0.0.1`), weil die Anwendung den Weiterleitungs-Headern vertraut. Bei einem gemeinsamen Proxy zusätzlich prüfen, ob Zugriffslogs im `server`- oder `http`-Block IP-Adressen mitschreiben (das Fehlerlog lässt sich nicht pro `location` abschalten), und das mit einem Aufruf aus dem Mobilfunknetz und einer Suche nach dieser IP in den Logs testen.

## Wartung

- **Backups:** `flask --app app backup` legt eine Kopie an. Sie enthält alle Nachrichten und gehört genauso geschützt wie die Datenbank.
- **Alte Nachrichten automatisch löschen** (Datensparsamkeit), z. B. jeden Sonntag um 3 Uhr per Cron:

  ```cron
  0 3 * * 0 cd <Pfad zum Projektordner> && DB_PATH=<Pfad zur Datenbank> .venv/bin/flask --app app purge --days 180 --only-done --yes
  ```

- **Alle Empfänger abmelden:** `SECRET_KEY` ändern und neu starten.
- **Mailversand prüfen:** `docker compose logs postfach` zeigt die täglichen Läufe (Zeilen mit `[notify]`). Nach Änderungen an Adressen oder Bereichen hilft `send-notifications --dry-run`.