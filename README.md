# Schul-Postfach

Ein anonymes digitales Postfach für Schüler: Probleme und Feedback melden, ohne Account, ohne Cookies, ohne gespeicherte IP-Adresse. Ausgewählte Verantwortliche (z. B. Vertrauenslehrer, SV) lesen die Nachrichten in einem geschützten Bereich und können antworten. Mit einem zufälligen Code holt der Absender die Antwort ab und kann Rückfragen stellen, ohne dass jemand erfährt, wer er ist. So entsteht ein anonymer Chat-Verlauf.

Technik: Python, Flask, SQLite. Keine externen Dienste, keine Fremd-Skripte, keine Tracker.

---

## Inhalt

1. [Funktionen](#funktionen)
2. [Was gespeichert wird (und was nicht)](#was-gespeichert-wird-und-was-nicht)
3. [Schnellstart (Entwicklung)](#schnellstart-entwicklung)
4. [Konfiguration](#konfiguration)
5. [Befehle für Zugänge und Daten](#befehle-für-zugänge-und-daten)
6. [Schutz vor Bots und Unsinn](#schutz-vor-bots-und-unsinn)
7. [Betrieb auf dem Schulserver](#betrieb-auf-dem-schulserver)
8. [Wartung](#wartung)
9. [Sicherheit: Grenzen und Empfehlungen](#sicherheit-grenzen-und-empfehlungen)
10. [Datenschutz und Organisation](#datenschutz-und-organisation)
11. [Design anpassen](#design-anpassen)
12. [Projektstruktur](#projektstruktur)

---

## Funktionen

**Für Schüler** (keine Anmeldung nötig)
- Nachricht mit Thema und Text abschicken.
- Danach erscheint ein einmaliger **Rückmeldecode** (z. B. `K7M2-XQ4P-...`). Damit lässt sich unter „Antwort abholen“ der Verlauf einsehen.
- **Chat über den Code:** Schreibt ein Empfänger zurück oder hat Fragen, sieht der Absender das im Verlauf und kann dort antworten. Der Verlauf ist wie ein Postfach aufgebaut, nicht in Echtzeit: Beide Seiten müssen nachsehen (der Absender mit Code, „Aktualisieren“ lädt neu). Der Absender wird nicht benachrichtigt, das würde die Anonymität aufheben.
- Der Code wird nur als Hash gespeichert und nie in einer URL angezeigt. Geht er verloren, kann er nicht wiederhergestellt werden. Wer den Code kennt, kann den Verlauf lesen und mitschreiben.

**Für Empfänger** (eigener Zugang pro Person, unter `/verwaltung`)
- Eingang mit Filter nach Status (neu / in Bearbeitung / erledigt).
- Pro Nachricht: Verlauf lesen, dem Absender schreiben, Status ändern, interne Notiz.
- **Offene Rückfragen** erscheinen mit einem Hinweis oben im Eingang und bleiben markiert, bis ein Empfänger antwortet oder die Nachricht auf „erledigt“ setzt.
- Schreibt ein Absender nach „erledigt“ noch einmal, wird die Nachricht automatisch wieder auf „in Bearbeitung“ gesetzt.
- Im Verlauf erscheint für den Absender nur „Schule“, nicht, welche Person geantwortet hat.
- Rollen: `admin` und `empfaenger`.

## Was gespeichert wird (und was nicht)

| Gespeichert | Nicht gespeichert |
|---|---|
| Nachrichtentext und Thema, Chat-Verlauf (Text, wer geschrieben hat: Absender oder Schule) | IP-Adresse |
| Datum (ohne Uhrzeit), auch bei Chat-Nachrichten | Uhrzeit, Browser, Gerät |
| Status, interne Notiz | Cookies oder Kennungen für Schüler |
| Hash des Rückmeldecodes | der Rückmeldecode selbst |
| Empfänger-Zugänge mit gehashten Passwörtern | Tracking, Statistik, externe Schriften |

Wichtig: Die Anwendung selbst schreibt keine IP-Adressen. **Webserver, Proxy und Firewall der Schule tun das aber oft von sich aus.** Ohne die Einstellungen im Abschnitt [Betrieb](#betrieb-auf-dem-schulserver) ist die Anonymität nicht gegeben. Auch der Text einer Nachricht kann den Absender verraten (Namen, Details, Schreibstil). Auf der Seite sollte deshalb nicht „100 % anonym“ versprochen werden, sondern genau erklärt werden, was gespeichert wird.

## Schnellstart (Entwicklung)

Voraussetzung: Python 3.10 oder neuer.

Linux / macOS:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Dann einen Admin anlegen und starten:

```bash
flask --app app create-user anna --role admin
flask --app app run
```

- Schüler-Formular: http://127.0.0.1:5000
- Verwaltung: http://127.0.0.1:5000/verwaltung/login

Die Datenbank `postfach.db` entsteht beim ersten Start automatisch **im aktuellen Arbeitsverzeichnis**. Führe alle `flask`-Befehle deshalb immer im selben Ordner aus oder setze `DB_PATH` (siehe unten), sonst legst du versehentlich eine zweite, leere Datenbank an.

`flask run` ist nur für Tests auf dem eigenen Rechner gedacht, nicht für den echten Betrieb.

## Konfiguration

**Umgebungsvariablen**

| Variable | Bedeutung | Standard |
|---|---|---|
| `SECRET_KEY` | Schlüssel für Sitzungen und die Formular-Prüfung. Im Betrieb **Pflicht**, lang und zufällig. | zufällig bei jedem Start |
| `HTTPS` | `1` setzt Cookies auf „nur über HTTPS“. Im Betrieb auf `1` stellen. | `0` |
| `DB_PATH` | Pfad zur SQLite-Datei | `postfach.db` |

Einen Schlüssel erzeugst du mit:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Ohne festen `SECRET_KEY` werden Empfänger bei jedem Neustart ausgeloggt, und bei mehreren Gunicorn-Workern bekommt jeder einen eigenen Schlüssel, was zu zufälligen Abbrüchen führt.

**Einstellungen in `app.py`** (oben im Code, danach Anwendung neu starten)

| Name | Bedeutung | Standard |
|---|---|---|
| `MIN_WORDS` | Mindestanzahl Wörter pro Nachricht | 15 |
| `MIN_UNIQUE` | davon mindestens so viele verschiedene Wörter | 8 |
| `MIN_SECONDS` | so lange muss das Formular mindestens offen sein | 5 |
| `MAX_AGE` | nach so vielen Sekunden gilt das Formular als abgelaufen | 86400 |
| `MAX_LEN` | maximale Zeichenzahl pro Nachricht | 5000 |
| `CHAT_MAX` | maximale Zeichenzahl pro Chat-Nachricht des Absenders | 2000 |
| `CHAT_BURST` | so viele Nachrichten in Folge darf der Absender schicken, bevor er auf eine Antwort warten muss | 3 |
| `CATEGORIES` | Themen im Auswahlfeld | Mobbing / Streit, Unterricht, Organisation, Sonstiges |
| `STATUS` | Bearbeitungsstatus | neu, in Bearbeitung, erledigt |

`MIN_UNIQUE` darf nie größer als `MIN_WORDS` sein, sonst kann niemand mehr eine Nachricht senden.

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

## Schutz vor Bots und Unsinn

Alle Maßnahmen kommen ohne IP-Speicherung, Cookies oder Drittanbieter aus (Dienste wie reCAPTCHA wären für ein anonymes Postfach ungeeignet).

1. **Honeypot-Feld:** ein verstecktes Feld, das nur Bots ausfüllen. Solche Einsendungen werden verworfen.
2. **Zeitprüfung:** das Formular enthält einen signierten Zeitstempel. Wird es schneller als `MIN_SECONDS` abgeschickt, gefälscht oder erst nach `MAX_AGE` benutzt, wird es abgelehnt. Die Prüfung ist zustandslos, es wird nichts gespeichert.
3. **Mindestlänge:** `MIN_WORDS` Wörter, davon `MIN_UNIQUE` verschiedene. Das fängt „asdf asdf asdf …“ ab.
4. **Duplikat-Filter:** derselbe Text wird innerhalb einer Stunde nicht zweimal angenommen. Die Prüfung läuft nur im Arbeitsspeicher.
   Im Chat bremst `CHAT_BURST` das Fluten: Nach 3 Nachrichten in Folge ohne Antwort muss der Absender warten.
5. **Globales Limit** (gilt auch für Abruf und Chat): höchstens 30 Nachrichten bzw. Abfragen pro Minute insgesamt, nicht pro Nutzer.

Grenzen: Ein gezielter Angreifer, der das Formular lädt, wartet und sinnvoll klingende Texte schickt, wird davon nicht gestoppt. Das globale Limit kann außerdem von Bots ausgelastet werden und blockiert dann auch echte Schüler. Als nächste Stufe wäre ein „Proof-of-Work“ möglich (der Browser löst vor dem Absenden eine kleine Rechenaufgabe), ebenfalls ohne Tracking. Offensichtlichen Unsinn markierst du im Eingang einfach als „erledigt“ oder löschst ihn mit `delete-message`.

## Betrieb auf dem Schulserver

Gunicorn läuft hinter einem Webserver (nginx oder Apache), der HTTPS übernimmt. **Entscheidend für die Anonymität: keine Zugriffslogs mit IP-Adressen.**

**Gunicorn**

```bash
SECRET_KEY=<langer-zufallswert> HTTPS=1 DB_PATH=/var/lib/schulpostfach/postfach.db \
  gunicorn -w 1 --threads 4 -b 127.0.0.1:8000 --access-logfile /dev/null app:app
```

Mit `-w 1 --threads 4` laufen die Zähler im Arbeitsspeicher (Login-Sperre, Limit, Duplikat-Filter) in einem gemeinsamen Prozess. Mit mehreren Workern gelten sie je Worker.

**systemd-Dienst** (`/etc/systemd/system/schulpostfach.service`)

```ini
[Unit]
Description=Schul-Postfach
After=network.target

[Service]
User=postfach
WorkingDirectory=/opt/schulpostfach
EnvironmentFile=/etc/schulpostfach.env
ExecStart=/opt/schulpostfach/venv/bin/gunicorn -w 1 --threads 4 -b 127.0.0.1:8000 --access-logfile /dev/null app:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`/etc/schulpostfach.env` (nur für root und den Dienst lesbar, `chmod 600`):

```
SECRET_KEY=<langer-zufallswert>
HTTPS=1
DB_PATH=/var/lib/schulpostfach/postfach.db
```

**nginx** (Beispiel)

```nginx
server {
    listen 443 ssl;
    server_name postfach.beispiel-schule.at;
    # ssl_certificate / ssl_certificate_key hier eintragen

    access_log off;                          # wichtig: keine IP-Adressen mitschreiben
    error_log /var/log/nginx/postfach-error.log crit;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        # X-Forwarded-For wird absichtlich nicht weitergegeben
    }
}
```

Bei Apache entsprechend das Zugriffslog für diesen VirtualHost abschalten. Prüfe außerdem mit der Schul-IT, ob **Proxy, Firewall oder Monitoring** des Schulnetzes Zugriffe protokollieren. Das kann der Code nicht verhindern.

**Dateirechte:** Ordner und `postfach.db` sollen nur dem Dienst-Benutzer gehören (`chmod 700` bzw. `600`). Dasselbe gilt für Backups.

## Wartung

- **Backups:** `flask --app app backup` legt eine Kopie an. Sie enthält alle Nachrichten und gehört genauso geschützt wie die Datenbank. Dateien `*.db` sind im `.gitignore` und dürfen nie ins Repository.
- **Alte Nachrichten automatisch löschen** (Datensparsamkeit), z. B. jeden Sonntag um 3 Uhr per Cron:

  ```
  0 3 * * 0 cd /opt/schulpostfach && DB_PATH=/var/lib/schulpostfach/postfach.db venv/bin/flask --app app purge --days 180 --only-done --yes
  ```
- **Updates:** neue Dateien einspielen, danach `sudo systemctl restart schulpostfach`.
- **Alle Empfänger abmelden:** `SECRET_KEY` ändern und neu starten.

## Sicherheit: Grenzen und Empfehlungen

Bereits umgesetzt: gehashte Passwörter, parametrisierte Datenbankabfragen (keine SQL-Injection), automatisches Maskieren von Texten und strenge Content-Security-Policy, CSRF-Schutz im Verwaltungsbereich, `HttpOnly`- und `SameSite=Strict`-Cookies, Sperre nach 5 Fehlversuchen, kein Caching, kein Referrer.

Bekannte Grenzen:
- **Der Code ist der einzige Schlüssel zum Chat.** Wer ihn kennt oder auf einem geteilten Gerät sieht, kann den Verlauf lesen und mitschreiben. Schüler sollten darauf hingewiesen werden (steht auch auf der Seite).
- **Keine Benachrichtigung der Absender:** Antworten werden nur sichtbar, wenn der Absender mit seinem Code nachsieht. Das ist Absicht, weil E-Mail oder Push die Anonymität aufheben würden.
- **Keine 2-Faktor-Anmeldung.** Ein erratenes oder wiederverwendetes Passwort genügt, um alle Nachrichten zu lesen.
- **Die Login-Sperre kann missbraucht werden:** Wer einen Benutzernamen kennt, kann diesen Account durch absichtliche Fehlversuche 5 Minuten sperren.
- **Nachrichten liegen unverschlüsselt in der Datenbank.** Wer Zugriff auf Server oder Datei hat (z. B. ein IT-Administrator), kann sie lesen.
- **Keine Sicherheitsprüfung durch Dritte.** Der Code hat keinen externen Audit durchlaufen.

Empfehlung vor dem echten Einsatz: 2FA für Empfänger ergänzen, die Server-Konfiguration von der Schul-IT prüfen lassen und klären, wer Zugriff auf Server und Backups hat.

## Datenschutz und Organisation

Vor dem Start mit der Schulleitung und der IT klären:

- Wer darf die Nachrichten lesen, und wie wird mit ihnen umgegangen? Das gehört offen auf die Seite.
- Welche Themen gehen an wen (z. B. Mobbing nur an Vertrauenslehrer)? Aktuell sehen alle Empfänger alle Nachrichten.
- Wie schnell wird auf Nachrichten und Rückfragen reagiert? Absender sehen Antworten nur, wenn sie nachsehen, deshalb lohnt sich ein Hinweis auf der Seite („Wir antworten innerhalb von …“).
- Wie lange werden Nachrichten und Verläufe aufbewahrt (`purge`)?
- Wie wird bei Hinweisen auf Gefahr für Leib und Leben vorgegangen? Schulen haben hier Pflichten, anonymes Melden darf kein Ersatz für Hilfe sein. Auf der Seite stehen Notruf 112 und Rat auf Draht 147.
- Datenschutzverantwortliche bzw. die Schulleitung einbinden (DSGVO).
- Ob die Seite mit Schulname und Logo auftreten darf.

## Design anpassen

Modern und schlicht: heller Hintergrund, abgerundete Karten, Chat-Blasen, ein farbiger Streifen oben nach dem Mosaik im Logo.

- **Farben:** ganz oben in `static/style.css`. `--accent` ist das Logo-Blau (`#003c8b`), `--accent-dark` die dunklere Variante. Der bunte Streifen (`.stripe`) nutzt die Farben des Logo-Mosaiks.
- **Logo:** `static/logo.svg` (HTL Anichstraße). Zum Austauschen die Datei ersetzen, ggf. Größe in `templates/base.html` und `.brand img` in der CSS anpassen. Externe Bilder blockiert die Content-Security-Policy, Bilder müssen deshalb im Ordner `static/` liegen.
- **Themen:** `CATEGORIES` in `app.py`.
- **Texte** der Startseite stehen in `templates/index.html`.

## Projektstruktur

```
app.py               Anwendung: Routen, Prüfungen, Befehle
requirements.txt     Abhängigkeiten (Flask, Gunicorn)
static/
  style.css          Design
  logo.svg           Schul-Logo
  counter.js         Live-Wortzähler im Formular
templates/
  base.html          Rahmen (Kopf, Claim, Fuß)
  index.html         Formular für Schüler
  danke.html         Bestätigung mit Rückmeldecode
  status.html        Antwort abholen und Chat-Verlauf für Absender
  login.html         Anmeldung Verwaltung
  inbox.html         Eingang der Empfänger
  message.html       Verlauf lesen, antworten, Status und Notiz
postfach.db          Datenbank (entsteht automatisch, nicht ins Repository)
```
