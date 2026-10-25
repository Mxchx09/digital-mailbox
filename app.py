"""Schul-Postfach: anonymes Feedback fuer Schueler.

Anonymitaet by design:
- keine Accounts/Cookies fuer Schueler, keine IP-Speicherung, kein Tracking
- nur Datum (keine Uhrzeit) wird gespeichert
- Rueckmeldecode wird nur als Hash gespeichert
Server-Logs (nginx/gunicorn) muessen ebenfalls ohne IP laufen, siehe README.
"""
import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, timedelta
from functools import wraps

import click
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.environ.get("HTTPS", "0") == "1",
    MAX_CONTENT_LENGTH=32 * 1024,
)
DB_PATH = os.environ.get("DB_PATH", "postfach.db")
MAX_LEN = 5000
MIN_WORDS = 5   # Mindestanzahl Woerter pro Nachricht
CHAT_MAX = 2000      # maximale Zeichenzahl pro Chat-Nachricht
CHAT_BURST = 3       # so viele Nachrichten in Folge darf der Absender schicken, bevor er auf eine Antwort wartet
MIN_SECONDS = 5      # so lange muss das Formular mindestens offen gewesen sein (Bot-Schutz)
MAX_AGE = 24 * 3600  # aelter als 24 h: Formular gilt als abgelaufen
MIN_UNIQUE = 3   # davon mindestens so viele verschiedene (gegen 'asdf asdf asdf ...')
CATEGORIES = ["Mobbing / Streit", "Unterricht", "Organisation", "Sonstiges"]
STATUS = ["neu", "in Bearbeitung", "erledigt"]
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ohne 0/O/1/I

# Keine Zugriffslogs mit IP-Adressen vom eingebauten Server
logging.getLogger("werkzeug").disabled = True

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    code_hash TEXT NOT NULL UNIQUE,
    kategorie TEXT NOT NULL,
    text TEXT NOT NULL,
    datum TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'neu',
    notiz TEXT NOT NULL DEFAULT '',
    neu_vom_schueler INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS chat (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    von TEXT NOT NULL CHECK (von IN ('schueler', 'empfaenger')),
    text TEXT NOT NULL,
    datum TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'empfaenger'
);
"""


def migrate(conn):
    """Legt Tabellen an und uebernimmt Daten aus aelteren Versionen."""
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
    if "neu_vom_schueler" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN neu_vom_schueler INTEGER NOT NULL DEFAULT 0")
    if "antwort" in cols:  # fruehere Einzelantworten in den Verlauf uebernehmen
        for mid, txt in conn.execute("SELECT id, antwort FROM messages WHERE antwort != ''").fetchall():
            conn.execute("INSERT INTO chat (message_id, von, text, datum) VALUES (?, 'empfaenger', ?, ?)",
                         (mid, txt, date.today().isoformat()))
            conn.execute("UPDATE messages SET antwort='' WHERE id=?", (mid,))


with sqlite3.connect(DB_PATH) as _c:
    migrate(_c)


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA secure_delete=ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn:
        conn.close()


# ---------- Hilfsfunktionen ----------
_recent = []  # globale Zeitstempel im RAM, keine IPs


def rate_limited(limit=30, window=60):
    now = time.time()
    _recent[:] = [t for t in _recent if now - t < window]
    if len(_recent) >= limit:
        return True
    _recent.append(now)
    return False


def hash_code(code):
    clean = "".join(ch for ch in code.upper() if ch in CODE_ALPHABET)
    return hashlib.sha256(clean.encode()).hexdigest()


def new_code():
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_admin_posts():
    if request.method == "POST" and request.path.startswith("/verwaltung"):
        sent = request.form.get("csrf", "")
        if not secrets.compare_digest(sent, session.get("csrf", "")):
            abort(400)


@app.after_request
def security_headers(resp):
    resp.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------- Oeffentlich (Schueler) ----------
def _sign(ts):
    return hmac.new(app.config["SECRET_KEY"].encode(), str(ts).encode(), hashlib.sha256).hexdigest()[:32]


def make_token():
    """Signierter Zeitstempel fuers Formular. Zustandslos: nichts wird gespeichert, keine Nutzerdaten."""
    ts = int(time.time())
    return f"{ts}.{_sign(ts)}"


def token_error(token):
    try:
        ts, sig = token.split(".", 1)
        if not secrets.compare_digest(sig.encode(), _sign(int(ts)).encode()):
            raise ValueError
        age = time.time() - int(ts)
    except (ValueError, AttributeError):
        return "Die Seite ist abgelaufen. Bitte sende deine Nachricht noch einmal ab."
    if age < MIN_SECONDS:
        return "Das ging etwas schnell. Bitte versuche es in ein paar Sekunden noch einmal."
    if age > MAX_AGE:
        return "Die Seite war zu lange geöffnet. Bitte sende deine Nachricht noch einmal ab."
    return None


_seen = {}  # Hash -> Zeitpunkt, nur im RAM: erkennt doppelt eingeschickte Texte


def is_duplicate(text, window=3600):
    now = time.time()
    for k in [k for k, t in _seen.items() if now - t > window]:
        del _seen[k]
    h = hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()
    if h in _seen:
        return True
    _seen[h] = now
    return False


def render_form(status=200, **kw):
    return render_template("index.html", categories=CATEGORIES, max_len=MAX_LEN,
                           min_words=MIN_WORDS, zt=make_token(), **kw), status


def validate(kategorie, text):
    """Gibt eine Fehlermeldung zurueck oder None, wenn alles passt."""
    words = text.split()
    if kategorie not in CATEGORIES:
        return "Bitte wähle ein Thema aus."
    if len(text) > MAX_LEN:
        return f"Deine Nachricht ist zu lang (maximal {MAX_LEN} Zeichen)."
    if len(words) < MIN_WORDS:
        return (f"Bitte beschreibe dein Anliegen etwas genauer: mindestens {MIN_WORDS} Wörter "
                f"(bisher {len(words)}).")
    if len({w.lower() for w in words}) < MIN_UNIQUE:
        return "Bitte schreibe in eigenen, vollständigen Sätzen, damit wir dein Anliegen verstehen."
    return None


@app.get("/")
def index():
    return render_form()


@app.post("/senden")
def senden():
    if request.form.get("website"):  # Honeypot fuer Bots
        return redirect(url_for("index"))
    if rate_limited():
        return render_form(429, error="Gerade sind zu viele Nachrichten eingegangen. "
                                      "Bitte versuche es in einer Minute erneut.")
    text = request.form.get("text", "").strip()
    kategorie = request.form.get("kategorie", "")
    error = token_error(request.form.get("zt", "")) or validate(kategorie, text)
    if not error and is_duplicate(text):
        error = "Diese Nachricht haben wir bereits erhalten."
    if error:
        return render_form(400, text=text, error=error, selected=kategorie)
    code = new_code()
    db().execute(
        "INSERT INTO messages (code_hash, kategorie, text, datum) VALUES (?,?,?,?)",
        (hash_code(code), kategorie, text, date.today().isoformat()))
    db().commit()
    return render_template("danke.html", code=code)  # kein Redirect: Code steht nie in einer URL


def find_message(code):
    return db().execute("SELECT * FROM messages WHERE code_hash=?", (hash_code(code),)).fetchone()


def chat_of(mid):
    return db().execute("SELECT von, text, datum FROM chat WHERE message_id=? ORDER BY id", (mid,)).fetchall()


def render_status(code="", msg=None, searched=False, status=200, **kw):
    chat = chat_of(msg["id"]) if msg else []
    return render_template("status.html", code=code, msg=msg, chat=chat, searched=searched, **kw), status


@app.route("/status", methods=["GET", "POST"])
def status():
    if request.method == "GET":
        return render_status()
    if rate_limited():
        abort(429)
    code = request.form.get("code", "")
    return render_status(code, find_message(code), searched=True)


@app.post("/status/schreiben")
def status_schreiben():
    """Der Absender schreibt eine Rueckfrage. Authentifiziert wird nur ueber den Code."""
    if rate_limited():
        abort(429)
    code = request.form.get("code", "")
    msg = find_message(code)
    if not msg:
        abort(404)
    text = request.form.get("text", "").strip()
    last = db().execute("SELECT von FROM chat WHERE message_id=? ORDER BY id DESC LIMIT ?",
                        (msg["id"], CHAT_BURST)).fetchall()
    error = None
    if not text:
        error = "Bitte schreibe etwas."
    elif len(text) > CHAT_MAX:
        error = f"Deine Nachricht ist zu lang (maximal {CHAT_MAX} Zeichen)."
    elif len(last) == CHAT_BURST and all(r["von"] == "schueler" for r in last):
        error = "Du hast schon mehrere Nachrichten geschickt. Bitte warte auf eine Antwort."
    if error:
        return render_status(code, msg, True, 400, error=error, text=text)
    db().execute("INSERT INTO chat (message_id, von, text, datum) VALUES (?, 'schueler', ?, ?)",
                 (msg["id"], text, date.today().isoformat()))
    # Rueckfrage markieren; war die Nachricht schon erledigt, wird sie wieder geoeffnet
    db().execute("UPDATE messages SET neu_vom_schueler=1, "
                 "status=CASE WHEN status='erledigt' THEN 'in Bearbeitung' ELSE status END WHERE id=?",
                 (msg["id"],))
    db().commit()
    return render_status(code, find_message(code), True)  # kein Redirect: Code steht nie in einer URL


# ---------- Verwaltung (Empfaenger) ----------
_fails = {}  # username -> (Fehlversuche, gesperrt bis)


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        uid = session.get("uid")
        if not uid or not db().execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
            session.clear()
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapped


@app.route("/verwaltung/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("username", "").strip().lower()
        count, until = _fails.get(name, (0, 0))
        if count >= 5 and time.time() < until:
            flash("Zu viele Fehlversuche. Bitte warte 5 Minuten.")
            return render_template("login.html"), 429
        user = db().execute("SELECT * FROM users WHERE username=?", (name,)).fetchone()
        if user and check_password_hash(user["pw_hash"], request.form.get("password", "")):
            _fails.pop(name, None)
            session.clear()
            session["uid"], session["role"] = user["id"], user["role"]
            return redirect(url_for("inbox"))
        _fails[name] = (count + 1, time.time() + 300)
        flash("Benutzername oder Passwort stimmt nicht.")
    return render_template("login.html")


@app.post("/verwaltung/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/verwaltung")
@login_required
def inbox():
    flt = request.args.get("status", "")
    order = "ORDER BY neu_vom_schueler DESC, id DESC"  # offene Rueckfragen zuerst
    if flt in STATUS:
        rows = db().execute(f"SELECT * FROM messages WHERE status=? {order}", (flt,)).fetchall()
    else:
        rows = db().execute(f"SELECT * FROM messages {order}").fetchall()
    return render_template("inbox.html", rows=rows, flt=flt, statuses=STATUS)


@app.route("/verwaltung/<int:mid>", methods=["GET", "POST"])
@login_required
def message(mid):
    row = db().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if not row:
        abort(404)
    if request.method == "POST":
        st = request.form.get("status", "")
        if st not in STATUS:
            abort(400)
        antwort = request.form.get("antwort", "").strip()[:MAX_LEN]
        if antwort:
            db().execute("INSERT INTO chat (message_id, von, text, datum) VALUES (?, 'empfaenger', ?, ?)",
                         (mid, antwort, date.today().isoformat()))
        offen = 0 if (antwort or st == "erledigt") else row["neu_vom_schueler"]
        db().execute("UPDATE messages SET status=?, notiz=?, neu_vom_schueler=? WHERE id=?",
                     (st, request.form.get("notiz", "")[:2000], offen, mid))
        db().commit()
        flash("Gespeichert.")
        return redirect(url_for("message", mid=mid))
    return render_template("message.html", m=row, chat=chat_of(mid), statuses=STATUS)


# ---------- Befehle: flask --app app <befehl> ----------
def _name(s):
    return s.strip().lower()


@contextmanager
def cli_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA secure_delete=ON")  # geloeschte Inhalte werden ueberschrieben
    conn.execute("PRAGMA foreign_keys=ON")   # Chat-Verlauf wird mit der Nachricht geloescht
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _vacuum():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("VACUUM")
    conn.close()


def _check_pw(pw):
    if len(pw) < 8:
        raise click.ClickException("Das Passwort braucht mindestens 8 Zeichen.")


def _user(conn, name):
    row = conn.execute("SELECT id, role FROM users WHERE username=?", (_name(name),)).fetchone()
    if not row:
        raise click.ClickException(f"Benutzer '{name}' nicht gefunden.")
    return row


def _is_last_admin(conn, uid):
    return conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND id!=?", (uid,)).fetchone()[0] == 0


ROLES = click.Choice(["admin", "empfaenger"])
yes_option = click.option("--yes", is_flag=True, help="Ohne Rueckfrage ausfuehren")


@app.cli.command("create-user")
@click.argument("username")
@click.option("--role", type=ROLES, default="empfaenger")
@click.password_option()
def create_user(username, role, password):
    """Neuen Zugang anlegen."""
    _check_pw(password)
    try:
        with cli_db() as c:
            c.execute("INSERT INTO users (username, pw_hash, role) VALUES (?,?,?)",
                      (_name(username), generate_password_hash(password), role))
    except sqlite3.IntegrityError:
        raise click.ClickException("Diesen Benutzernamen gibt es schon.")
    click.echo(f"Zugang '{username}' ({role}) angelegt.")


@app.cli.command("list-users")
def list_users():
    """Alle Zugaenge anzeigen."""
    with cli_db() as c:
        rows = c.execute("SELECT username, role FROM users ORDER BY username").fetchall()
    for name, role in rows:
        click.echo(f"{name}  ({role})")
    if not rows:
        click.echo("Noch keine Zugaenge angelegt.")


@app.cli.command("set-password")
@click.argument("username")
@click.password_option()
def set_password(username, password):
    """Passwort eines Zugangs aendern."""
    _check_pw(password)
    with cli_db() as c:
        uid, _ = _user(c, username)
        c.execute("UPDATE users SET pw_hash=? WHERE id=?", (generate_password_hash(password), uid))
    click.echo("Passwort geaendert.")


@app.cli.command("rename-user")
@click.argument("old")
@click.argument("new")
def rename_user(old, new):
    """Benutzernamen aendern."""
    try:
        with cli_db() as c:
            uid, _ = _user(c, old)
            c.execute("UPDATE users SET username=? WHERE id=?", (_name(new), uid))
    except sqlite3.IntegrityError:
        raise click.ClickException("Diesen Benutzernamen gibt es schon.")
    click.echo("Benutzername geaendert.")


@app.cli.command("set-role")
@click.argument("username")
@click.argument("role", type=ROLES)
def set_role(username, role):
    """Rolle aendern (admin / empfaenger)."""
    with cli_db() as c:
        uid, old = _user(c, username)
        if old == "admin" and role != "admin" and _is_last_admin(c, uid):
            raise click.ClickException("Das ist der letzte Admin und kann nicht herabgestuft werden.")
        c.execute("UPDATE users SET role=? WHERE id=?", (role, uid))
    click.echo(f"'{username}' ist jetzt {role}.")


@app.cli.command("remove-user")
@click.argument("username")
@yes_option
def remove_user(username, yes):
    """Zugang loeschen."""
    with cli_db() as c:
        uid, role = _user(c, username)
        if role == "admin" and _is_last_admin(c, uid):
            raise click.ClickException("Das ist der letzte Admin und kann nicht geloescht werden.")
        if not yes:
            click.confirm(f"Zugang '{username}' wirklich loeschen?", abort=True)
        c.execute("DELETE FROM users WHERE id=?", (uid,))
    click.echo("Zugang geloescht. Laufende Sitzungen enden beim naechsten Seitenaufruf.")


@app.cli.command("stats")
def stats():
    """Uebersicht: Anzahl Nachrichten und Zugaenge."""
    with cli_db() as c:
        total = c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        click.echo(f"Nachrichten gesamt: {total}")
        click.echo(f"Offene Rueckfragen: {c.execute('SELECT COUNT(*) FROM messages WHERE neu_vom_schueler=1').fetchone()[0]}")
        for st, n in c.execute("SELECT status, COUNT(*) FROM messages GROUP BY status"):
            click.echo(f"  {st}: {n}")
        for k, n in c.execute("SELECT kategorie, COUNT(*) FROM messages GROUP BY kategorie"):
            click.echo(f"  Thema {k}: {n}")
        first, last = c.execute("SELECT MIN(datum), MAX(datum) FROM messages").fetchone()
        if first:
            click.echo(f"Zeitraum: {first} bis {last}")
        click.echo(f"Zugaenge: {c.execute('SELECT COUNT(*) FROM users').fetchone()[0]}")


@app.cli.command("delete-message")
@click.argument("message_id", type=int)
@yes_option
def delete_message(message_id, yes):
    """Eine Nachricht anhand ihrer Nummer loeschen."""
    with cli_db() as c:
        if not c.execute("SELECT 1 FROM messages WHERE id=?", (message_id,)).fetchone():
            raise click.ClickException("Nachricht nicht gefunden.")
        if not yes:
            click.confirm(f"Nachricht {message_id} wirklich loeschen?", abort=True)
        c.execute("DELETE FROM messages WHERE id=?", (message_id,))
    _vacuum()
    click.echo("Nachricht geloescht.")


@app.cli.command("purge")
@click.option("--days", type=click.IntRange(min=0), required=True, help="Nachrichten aelter als N Tage")
@click.option("--only-done", is_flag=True, help="Nur Nachrichten mit Status 'erledigt'")
@yes_option
def purge(days, only_done, yes):
    """Alte Nachrichten loeschen (Datensparsamkeit)."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    where = "FROM messages WHERE datum < ?" + (" AND status='erledigt'" if only_done else "")
    with cli_db() as c:
        n = c.execute(f"SELECT COUNT(*) {where}", (cutoff,)).fetchone()[0]
        if not n:
            click.echo("Keine passenden Nachrichten.")
            return
        if not yes:
            click.confirm(f"{n} Nachricht(en) vor {cutoff} loeschen?", abort=True)
        c.execute(f"DELETE {where}", (cutoff,))
    _vacuum()
    click.echo(f"{n} Nachricht(en) geloescht.")


@app.cli.command("clear-messages")
@yes_option
def clear_messages(yes):
    """Alle Nachrichten loeschen, Zugaenge bleiben."""
    with cli_db() as c:
        n = c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        if not yes:
            click.confirm(f"Wirklich ALLE {n} Nachrichten loeschen?", abort=True)
        c.execute("DELETE FROM messages")
    _vacuum()
    click.echo("Alle Nachrichten geloescht.")


@app.cli.command("reset-db")
@yes_option
def reset_db(yes):
    """Komplett zuruecksetzen: loescht Nachrichten UND Zugaenge."""
    if not yes and click.prompt("Das loescht ALLES. Tippe LOESCHEN zur Bestaetigung") != "LOESCHEN":
        raise click.Abort()
    with cli_db() as c:
        c.executescript("DROP TABLE IF EXISTS chat; DROP TABLE IF EXISTS messages; DROP TABLE IF EXISTS users;")
        c.executescript(SCHEMA)
    _vacuum()
    click.echo("Datenbank zurueckgesetzt. Lege jetzt mit create-user einen Admin an.")


@app.cli.command("backup")
@click.argument("ziel", required=False)
def backup(ziel):
    """Sicherungskopie der Datenbank anlegen (enthaelt Nachrichten, gut schuetzen!)."""
    ziel = ziel or f"postfach-backup-{date.today().isoformat()}.db"
    if os.path.exists(ziel):
        raise click.ClickException(f"'{ziel}' existiert schon.")
    src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(ziel)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    os.chmod(ziel, 0o600)
    click.echo(f"Sicherung: {ziel}")
