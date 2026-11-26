"""
How to run tests:
- Activate the venv (with requirements.txt installed): source .venv/bin/activate
- Run all tests:            pytest
- Run one file, verbose:    pytest -v tests/test_app.py
- Run tests matching a name: pytest -k validate
"""

import logging
import os
import re
import sqlite3
import stat
import time
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from werkzeug.security import generate_password_hash

import app

# ========== Pure functions ==========

# ---------- validate() ----------
GOOD_TEXT = "Im Klassenzimmer ist es immer viel zu kalt"

def test_validate_accepts_good_message():
    assert app.validate("sv", "Unterricht", GOOD_TEXT) is None


def test_validate_rejects_unknown_recipient():
    assert app.validate("gibts-nicht", "Unterricht", GOOD_TEXT) is not None


def test_validate_rejects_topic_of_other_recipient():
    # "Mobbing / Streit" exists, but only for "sozial", not for "sv"
    assert app.validate("sv", "Mobbing / Streit", GOOD_TEXT) is not None


def test_validate_rejects_too_few_words():
    error = app.validate("sv", "Unterricht", "zu kurz")
    assert "mindestens" in error


def test_validate_rejects_repeated_word():
    assert app.validate("sv", "Unterricht", "asdf asdf asdf asdf asdf") is not None

# Different words, so only the word count is wrong (not the repeated-word check).
WORDS = "eins zwei drei vier fuenf sechs sieben acht".split()


def test_validate_word_limit():
    just_enough = " ".join(WORDS[:app.MIN_WORDS])
    one_short = " ".join(WORDS[:app.MIN_WORDS - 1])
    assert app.validate("sv", "Unterricht", just_enough) is None
    assert "mindestens" in app.validate("sv", "Unterricht", one_short)


def test_validate_length_limit():
    # MAX_LEN counts characters, not words.
    exactly_max = ((GOOD_TEXT + " ") * 200)[:app.MAX_LEN]
    assert app.validate("sv", "Unterricht", exactly_max) is None
    assert "zu lang" in app.validate("sv", "Unterricht", exactly_max + "x")


# ---------- hash_code() ----------

def test_hash_code_ignores_case_and_dashes():
    assert app.hash_code("abcd-efgh-jkmn-pqrs") == app.hash_code("ABCDEFGHJKMNPQRS")


def test_hash_code_does_not_contain_the_code():
    code = app.new_code()
    assert code.replace("-", "") not in app.hash_code(code)

# ---------- is_duplicate() ----------
# These take `client` only so the duplicate memory is cleared first.

def test_is_duplicate_first_message_is_new(client):
    assert app.is_duplicate("testnachricht") is False


def test_is_duplicate_detects_duplicate(client):
    app.is_duplicate("testnachricht")
    assert app.is_duplicate("testnachricht") is True


def test_is_duplicate_ignores_case_and_outer_spaces(client):
    app.is_duplicate("testnachricht")
    assert app.is_duplicate("  TestNachricht  ") is True


def test_is_duplicate_collapses_inner_spaces(client):
    app.is_duplicate("test nachricht")
    assert app.is_duplicate("Test    Nachricht") is True


def test_is_duplicate_different_text_is_new(client):
    app.is_duplicate("test nachricht")
    assert app.is_duplicate("andere nachricht") is False


# ---------- new_code() ----------

def test_new_code_format():
    code = app.new_code()
    assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", code)
    # Only letters from the alphabet (no O/0/I/1, which look alike)
    assert all(ch in app.CODE_ALPHABET for ch in code.replace("-", ""))


# ---------- make_token() / token_error() ----------

def test_token_too_fast_is_rejected():
    # MIN_SECONDS is the bot protection: a fresh token is refused.
    assert "schnell" in app.token_error(app.make_token())


def test_token_old_enough_is_accepted(monkeypatch):
    monkeypatch.setattr(app, "MIN_SECONDS", 0)
    assert app.token_error(app.make_token()) is None


def test_token_expired(monkeypatch):
    ts = int(time.time()) - app.MAX_AGE - 10
    assert "zu lange" in app.token_error(f"{ts}.{app._sign(ts)}")


@pytest.mark.parametrize("token", ["", "kaputt", "123", "abc.def", None])
def test_token_garbage_is_rejected(token):
    assert "abgelaufen" in app.token_error(token)


def test_token_with_forged_timestamp_is_rejected(monkeypatch):
    # A bot can't just set an old timestamp: the signature no longer matches.
    monkeypatch.setattr(app, "MIN_SECONDS", 0)
    ts, sig = app.make_token().split(".")
    assert app.token_error(f"{int(ts) - 60}.{sig}") is not None


# ---------- rate_limited() ----------

def test_rate_limit_kicks_in_after_limit(client):
    assert not any(app.rate_limited(limit=3) for _ in range(3))
    assert app.rate_limited(limit=3) is True


def test_rate_limit_forgets_old_requests(client):
    app._recent.extend([time.time() - 120] * 30)
    assert app.rate_limited() is False


# ---------- is_duplicate() window ----------

def test_is_duplicate_forgets_after_window(client):
    app.is_duplicate("testnachricht")
    app._seen.update({k: time.time() - 7200 for k in app._seen})
    assert app.is_duplicate("testnachricht") is False


# ---------- hash_code() ----------

def test_hash_code_differs_for_different_codes():
    assert app.hash_code(app.new_code()) != app.hash_code(app.new_code())


def test_new_code_is_random():
    assert len({app.new_code() for _ in range(100)}) == 100


# ---------- _next_run() / _seconds_until() (daily mail) ----------
VIENNA = ZoneInfo("Europe/Vienna")


def test_next_run_later_today(monkeypatch):
    monkeypatch.setattr(app, "NOTIFY_AT", "15:00")
    now = datetime(2026, 5, 4, 9, 30, tzinfo=VIENNA)
    assert app._next_run(now) == datetime(2026, 5, 4, 15, 0, tzinfo=VIENNA)


def test_next_run_already_passed_means_tomorrow(monkeypatch):
    monkeypatch.setattr(app, "NOTIFY_AT", "07:00")
    now = datetime(2026, 5, 4, 7, 0, tzinfo=VIENNA)  # exactly now counts as passed
    assert app._next_run(now) == datetime(2026, 5, 5, 7, 0, tzinfo=VIENNA)


def test_next_run_picks_earliest_of_several(monkeypatch):
    monkeypatch.setattr(app, "NOTIFY_AT", " 15:00 , 07:00,")
    assert app._next_run(datetime(2026, 5, 4, 10, 0, tzinfo=VIENNA)).hour == 15
    assert app._next_run(datetime(2026, 5, 4, 16, 0, tzinfo=VIENNA)) == datetime(2026, 5, 5, 7, 0, tzinfo=VIENNA)


def test_next_run_without_times_fails(monkeypatch):
    monkeypatch.setattr(app, "NOTIFY_AT", " , ")
    with pytest.raises(ValueError):
        app._next_run(datetime.now(VIENNA))


def test_seconds_until_handles_daylight_saving(monkeypatch):
    # Night of 28 -> 29 March 2026 the clocks jump forward: one hour less.
    monkeypatch.setattr(app, "NOTIFY_AT", "07:00")
    now = datetime(2026, 3, 28, 12, 0, tzinfo=VIENNA)
    assert app._seconds_until(app._next_run(now), now) == 18 * 3600


# ---------- start_scheduler() ----------

class FakeThread:
    started = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def start(self):
        FakeThread.started.append(self.kwargs["name"])


@pytest.fixture
def fake_thread(monkeypatch):
    FakeThread.started = []
    monkeypatch.setattr(app.threading, "Thread", FakeThread)
    return FakeThread


def test_scheduler_off_without_notify_at(fake_thread, mail_server, monkeypatch):
    monkeypatch.setattr(app, "NOTIFY_AT", "")
    app.start_scheduler()
    assert fake_thread.started == []


def test_scheduler_off_without_smtp(fake_thread, monkeypatch, caplog):
    monkeypatch.setattr(app, "NOTIFY_AT", "07:00")
    app.start_scheduler()
    assert fake_thread.started == []
    assert "SMTP_HOST" in caplog.text


@pytest.mark.parametrize("notify_at, tz", [("7 Uhr", "Europe/Vienna"), ("25:00", "Europe/Vienna"),
                                           ("07:00", "Mars/Olympus")])
def test_scheduler_off_with_bad_settings(fake_thread, mail_server, monkeypatch, caplog, notify_at, tz):
    monkeypatch.setattr(app, "NOTIFY_AT", notify_at)
    monkeypatch.setattr(app, "NOTIFY_TZ", tz)
    app.start_scheduler()
    assert fake_thread.started == []
    assert "Ungueltige" in caplog.text


def test_scheduler_starts_and_releases_stuck_messages(fake_thread, mail_server, monkeypatch):
    monkeypatch.setattr(app, "NOTIFY_AT", "07:00")
    add_message()
    with app.cli_db() as c:
        c.execute("UPDATE messages SET mail_gesendet=2")  # claimed by a run that crashed
    app.start_scheduler()
    assert fake_thread.started == ["notify"]
    assert mail_flags() == [0]


# ---------- _scheduler_loop() ----------

class StopLoop(Exception):
    """The loop runs forever; the fake sleep raises this to end the test."""


@pytest.fixture
def fake_sleep(monkeypatch):
    """Records sleeps instead of waiting. Stops the loop at the start of the 2nd day."""
    sleeps = []

    def sleep(seconds):
        if seconds != 3600 and any(s != 3600 for s in sleeps):
            raise StopLoop
        sleeps.append(seconds)

    monkeypatch.setattr(app, "NOTIFY_AT", "07:00")
    monkeypatch.setattr(app.time, "sleep", sleep)
    return sleeps


def test_scheduler_loop_sends_once_per_day(fake_sleep, monkeypatch, caplog):
    runs = []
    monkeypatch.setattr(app, "run_notifications", lambda: runs.append(1) or "1 Mail(s) gesendet")
    with pytest.raises(StopLoop):
        app._scheduler_loop()
    assert runs == [1]
    assert len(fake_sleep) == 1 and 0 < fake_sleep[0] <= 24 * 3600 + 1  # waits until 07:00
    assert "notify: 1 Mail(s) gesendet" in caplog.text


def test_scheduler_loop_retries_hourly_then_gives_up(fake_sleep, monkeypatch, caplog):
    attempts = []

    def failing():
        attempts.append(1)
        raise RuntimeError("Server nicht erreichbar")

    monkeypatch.setattr(app, "run_notifications", failing)
    with pytest.raises(StopLoop):
        app._scheduler_loop()
    assert len(attempts) == 6  # then waits for the next day instead of trying forever
    assert fake_sleep[1:] == [3600] * 6
    assert "Versuch 1/6" in caplog.text and "Versuch 6/6" in caplog.text
    assert "Server nicht erreichbar" not in caplog.text  # only the error type, never details


def test_scheduler_loop_stops_retrying_after_success(fake_sleep, monkeypatch):
    results = iter([RuntimeError("weg"), RuntimeError("weg"), "1 Mail(s) gesendet"])

    def flaky():
        r = next(results)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(app, "run_notifications", flaky)
    with pytest.raises(StopLoop):
        app._scheduler_loop()
    assert fake_sleep[1:] == [3600, 3600]


# ---------- migrate() ----------

def test_migrate_upgrades_old_database(tmp_path):
    path = tmp_path / "alt.db"
    with closing(sqlite3.connect(path)) as c:
        c.executescript("""
            CREATE TABLE messages (id INTEGER PRIMARY KEY, code_hash TEXT NOT NULL UNIQUE,
                kategorie TEXT NOT NULL, text TEXT NOT NULL, datum TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'neu', notiz TEXT NOT NULL DEFAULT '',
                antwort TEXT NOT NULL DEFAULT '');
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                pw_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'empfaenger', bereiche TEXT);
            INSERT INTO messages (code_hash, kategorie, text, datum, antwort)
                VALUES ('h1', 'Sonstiges', 'alt', '2025-01-01', 'Alte Antwort');
            INSERT INTO users (username, pw_hash, bereiche) VALUES ('anna', 'x', 'sozial');
        """)
        app.migrate(c)
        c.commit()

        msg = c.execute("SELECT empfaenger, mail_gesendet, neu_vom_schueler, antwort FROM messages").fetchone()
        assert msg == ("sv", 1, 0, "")  # old messages: first section, never re-reported
        assert c.execute("SELECT von, text FROM chat").fetchall() == [("empfaenger", "Alte Antwort")]
        assert c.execute("SELECT email, sections FROM users").fetchone() == ("", "sozial")


def test_migrate_old_users_without_sections_see_everything(tmp_path):
    with closing(sqlite3.connect(tmp_path / "alt.db")) as c:
        c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, "
                  "pw_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'empfaenger')")
        c.execute("INSERT INTO users (username, pw_hash) VALUES ('anna', 'x')")
        app.migrate(c)
        assert c.execute("SELECT sections FROM users").fetchone()[0] == ",".join(app.RECIPIENTS)


def test_migrate_twice_changes_nothing(tmp_path):
    with closing(sqlite3.connect(tmp_path / "neu.db")) as c:
        app.migrate(c)
        c.execute("INSERT INTO messages (code_hash, empfaenger, kategorie, text, datum) "
                  "VALUES ('h', 'sozial', 'Sonstiges', 't', '2026-01-01')")
        app.migrate(c)
        assert c.execute("SELECT empfaenger, mail_gesendet FROM messages").fetchone() == ("sozial", 0)


# ========== Helpers for the tests below ==========
CODE_RE = r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}"
PASSWORD = "richtig-langes-passwort"


def add_user(username, email="", sections=("sv",), role="empfaenger", password="x"):
    """Inserts a user; pass a real `password` only when the test logs in with it (hashing is slow)."""
    pw_hash = password if password == "x" else generate_password_hash(password)
    with app.cli_db() as c:
        return c.execute("INSERT INTO users (username, pw_hash, role, email, sections) VALUES (?,?,?,?,?)",
                         (username, pw_hash, role, email, ",".join(sections))).lastrowid


def add_message(empfaenger="sv", text=GOOD_TEXT, datum="2026-01-01", status="neu", code=None):
    with app.cli_db() as c:
        return c.execute("INSERT INTO messages (code_hash, empfaenger, kategorie, text, datum, status) "
                         "VALUES (?, ?, 'Sonstiges', ?, ?, ?)",
                         (app.hash_code(code or app.new_code()), empfaenger, text, datum, status)).lastrowid


def add_chat(mid, von, text="Hallo"):
    with app.cli_db() as c:
        c.execute("INSERT INTO chat (message_id, von, text, datum) VALUES (?, ?, ?, '2026-01-01')",
                  (mid, von, text))


def get_message(mid):
    with app.cli_db() as c:
        c.row_factory = sqlite3.Row
        return c.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()


def get_chat(mid):
    with app.cli_db() as c:
        return c.execute("SELECT von, text FROM chat WHERE message_id=? ORDER BY id", (mid,)).fetchall()


def mail_flags():
    """mail_gesendet per message: 0 = not reported yet, 1 = reported."""
    with app.cli_db() as c:
        return [r[0] for r in c.execute("SELECT mail_gesendet FROM messages ORDER BY id")]


def log_in(client, uid):
    """Logs in without the password form and sets the CSRF token to 'csrf'."""
    with client.session_transaction() as s:
        s["uid"] = uid
        s["csrf"] = "csrf"


def send_form(client, **overrides):
    data = {"empfaenger": "sv", "kategorie": "Unterricht", "text": GOOD_TEXT, "zt": app.make_token()}
    data.update(overrides)
    return client.post("/senden", data=data)


def html_of(response):
    return response.get_data(as_text=True)


# ========== HTTP requests ==========

def test_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"


def test_student_pages_set_no_cookie(client):
    # Anonymity: students get no session cookie, not even on the form.
    assert "Set-Cookie" not in client.get("/").headers
    assert "Set-Cookie" not in client.get("/status").headers


# ---------- /senden ----------
def test_send_message_and_look_it_up(client, monkeypatch):
    # The form refuses submissions faster than MIN_SECONDS (bot protection).
    monkeypatch.setattr(app, "MIN_SECONDS", 0)

    response = client.post(
        "/senden",
        data={
            "empfaenger": "sv",
            "kategorie": "Unterricht",
            "text": GOOD_TEXT,
            "zt": app.make_token(),
        },
    )
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    code = re.search(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", html).group()

    # Anonymity: the code must not end up in a URL (no redirect to e.g. /danke?code=...)
    assert "Location" not in response.headers

    # Looking the code up on the status page must find the message again.
    status = client.post("/status", data={"code": code})
    assert GOOD_TEXT in status.get_data(as_text=True)


def test_send_stores_only_hash_and_date(client, monkeypatch):
    monkeypatch.setattr(app, "MIN_SECONDS", 0)
    code = re.search(CODE_RE, html_of(send_form(client))).group()
    msg = get_message(1)
    assert msg["code_hash"] == app.hash_code(code)
    assert code not in msg["code_hash"]
    assert msg["datum"] == date.today().isoformat()  # date only, no time of day
    assert (msg["empfaenger"], msg["kategorie"], msg["status"]) == ("sv", "Unterricht", "neu")


def test_send_too_fast_is_rejected(client):
    response = send_form(client)  # MIN_SECONDS not patched: the form was "open" 0 s
    assert response.status_code == 400
    assert "schnell" in html_of(response)
    assert get_message(1) is None


def test_send_invalid_keeps_text_in_form(client, monkeypatch):
    monkeypatch.setattr(app, "MIN_SECONDS", 0)
    response = send_form(client, text="nur drei Wörter")
    assert response.status_code == 400
    assert "mindestens" in html_of(response)
    assert "nur drei Wörter" in html_of(response)  # student doesn't lose what they typed
    assert get_message(1) is None


def test_send_honeypot_drops_message_silently(client, monkeypatch):
    monkeypatch.setattr(app, "MIN_SECONDS", 0)
    response = send_form(client, website="http://spam.example")
    assert response.status_code == 302
    assert get_message(1) is None


def test_send_same_text_twice_is_rejected(client, monkeypatch):
    monkeypatch.setattr(app, "MIN_SECONDS", 0)
    assert send_form(client).status_code == 200
    response = send_form(client)
    assert response.status_code == 400
    assert "bereits erhalten" in html_of(response)
    assert get_message(2) is None


def test_send_rate_limited(client, monkeypatch):
    monkeypatch.setattr(app, "MIN_SECONDS", 0)
    app._recent.extend([time.time()] * 30)
    response = send_form(client)
    assert response.status_code == 429
    assert get_message(1) is None


def test_send_text_is_stripped(client, monkeypatch):
    monkeypatch.setattr(app, "MIN_SECONDS", 0)
    send_form(client, text=f"   {GOOD_TEXT}  \n")
    assert get_message(1)["text"] == GOOD_TEXT


def test_message_text_is_html_escaped(client, monkeypatch):
    monkeypatch.setattr(app, "MIN_SECONDS", 0)
    evil = "<script>alert(1)</script> und noch ein paar Wörter dazu"
    code = re.search(CODE_RE, html_of(send_form(client, text=evil))).group()
    html = html_of(client.post("/status", data={"code": code}))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ---------- /status ----------

def test_status_unknown_code(client):
    response = client.post("/status", data={"code": app.new_code()})
    assert response.status_code == 200
    assert "keine Nachricht" in html_of(response)


def test_status_code_is_case_and_dash_insensitive(client):
    code = app.new_code()
    add_message(code=code)
    sloppy = code.lower().replace("-", " ")
    assert GOOD_TEXT in html_of(client.post("/status", data={"code": sloppy}))


def test_status_shows_reply_from_school(client):
    code = app.new_code()
    mid = add_message(code=code)
    add_chat(mid, "empfaenger", "Wir kümmern uns darum.")
    html = html_of(client.post("/status", data={"code": code}))
    assert "Wir kümmern uns darum." in html
    assert "Noch keine Antwort" not in html


def test_status_rate_limited(client):
    app._recent.extend([time.time()] * 30)
    assert client.post("/status", data={"code": app.new_code()}).status_code == 429


# ---------- /status/schreiben ----------

def test_reply_unknown_code_is_404(client):
    response = client.post("/status/schreiben", data={"code": app.new_code(), "text": "Hallo?"})
    assert response.status_code == 404


def test_reply_is_stored_and_flags_message(client):
    code = app.new_code()
    mid = add_message(code=code)
    response = client.post("/status/schreiben", data={"code": code, "text": "  Gibt es Neuigkeiten?  "})
    assert response.status_code == 200
    assert "Gibt es Neuigkeiten?" in html_of(response)
    assert get_chat(mid) == [("schueler", "Gibt es Neuigkeiten?")]
    assert get_message(mid)["neu_vom_schueler"] == 1


@pytest.mark.parametrize("text, error", [("   ", "Bitte schreibe etwas"),
                                         ("x" * (app.CHAT_MAX + 1), "zu lang")])
def test_reply_invalid_text(client, text, error):
    code = app.new_code()
    mid = add_message(code=code)
    response = client.post("/status/schreiben", data={"code": code, "text": text})
    assert response.status_code == 400
    assert error in html_of(response)
    assert get_chat(mid) == []


def test_reply_burst_limit(client):
    code = app.new_code()
    mid = add_message(code=code)
    for i in range(app.CHAT_BURST):
        assert client.post("/status/schreiben", data={"code": code, "text": f"Nr {i}"}).status_code == 200
    response = client.post("/status/schreiben", data={"code": code, "text": "Noch eine"})
    assert response.status_code == 400
    assert "warte auf eine Antwort" in html_of(response)

    # After the school answers, the student may write again.
    add_chat(mid, "empfaenger", "Antwort")
    assert client.post("/status/schreiben", data={"code": code, "text": "Danke"}).status_code == 200


def test_reply_reopens_finished_message(client):
    code = app.new_code()
    mid = add_message(code=code, status="erledigt")
    client.post("/status/schreiben", data={"code": code, "text": "Ist doch nicht gelöst"})
    assert get_message(mid)["status"] == "in Bearbeitung"


def test_reply_keeps_status_new(client):
    code = app.new_code()
    mid = add_message(code=code, status="neu")
    client.post("/status/schreiben", data={"code": code, "text": "Nachtrag"})
    assert get_message(mid)["status"] == "neu"


def test_reply_rate_limited(client):
    code = app.new_code()
    mid = add_message(code=code)
    app._recent.extend([time.time()] * 30)
    assert client.post("/status/schreiben", data={"code": code, "text": "Hallo?"}).status_code == 429
    assert get_chat(mid) == []


# ---------- /verwaltung ----------

def test_admin_path_without_slash_redirects(client):
    # Flask adds the trailing slash itself (308). This is NOT the login check.
    response = client.get("/verwaltung")
    assert response.status_code == 308
    assert response.headers["Location"].endswith("/verwaltung/")


def test_admin_page_requires_login(client):
    response = client.get("/verwaltung/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/verwaltung/login")


def login_form(client, username, password):
    client.get("/verwaltung/login")  # creates the CSRF token in the session
    with client.session_transaction() as s:
        csrf = s["csrf"]
    return client.post("/verwaltung/login", data={"username": username, "password": password, "csrf": csrf})


def test_login_success(client):
    add_user("anna", password=PASSWORD)
    response = login_form(client, " Anna ", PASSWORD)  # username: case and spaces don't matter
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/verwaltung/")
    assert client.get("/verwaltung/").status_code == 200


def test_login_wrong_password(client):
    add_user("anna", password=PASSWORD)
    response = login_form(client, "anna", "falsch")
    assert response.status_code == 200
    assert "stimmt nicht" in html_of(response)
    assert client.get("/verwaltung/").status_code == 302


def test_login_unknown_user_same_error(client):
    # Don't reveal which usernames exist.
    assert "stimmt nicht" in html_of(login_form(client, "gibtsnicht", "egal"))


def test_login_locked_after_five_failures(client):
    add_user("anna", password=PASSWORD)
    for _ in range(5):
        login_form(client, "anna", "falsch")
    response = login_form(client, "anna", PASSWORD)  # even the right password is refused now
    assert response.status_code == 429
    assert "Fehlversuche" in html_of(response)


def test_login_lock_expires(client):
    add_user("anna", password=PASSWORD)
    app._fails["anna"] = (5, time.time() - 1)
    assert login_form(client, "anna", PASSWORD).status_code == 302


def test_admin_post_without_csrf_is_rejected(client):
    add_user("anna", password=PASSWORD)
    client.get("/verwaltung/login")  # session now has a CSRF token, the form below doesn't send it
    response = client.post("/verwaltung/login", data={"username": "anna", "password": PASSWORD})
    assert response.status_code == 400


def test_admin_post_without_any_csrf_token_is_rejected(client):
    add_user("anna", password=PASSWORD)
    response = client.post("/verwaltung/login", data={"username": "anna", "password": PASSWORD})
    assert response.status_code == 400


def test_logout(client):
    log_in(client, add_user("anna"))
    assert client.get("/verwaltung/").status_code == 200
    assert client.post("/verwaltung/logout", data={"csrf": "csrf"}).status_code == 302
    assert client.get("/verwaltung/").status_code == 302


def test_deleted_user_session_ends(client):
    uid = add_user("anna")
    log_in(client, uid)
    with app.cli_db() as c:
        c.execute("DELETE FROM users WHERE id=?", (uid,))
    response = client.get("/verwaltung/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/verwaltung/login")


# ---------- inbox ----------

def test_inbox_shows_only_own_sections(client):
    log_in(client, add_user("anna", sections=("sv",)))
    add_message("sv", "Nachricht an die SV hier drin")
    add_message("sozial", "Geheime Nachricht an Sozialarbeit")
    html = html_of(client.get("/verwaltung/"))
    assert "Nachricht an die SV hier drin" in html
    assert "Geheime Nachricht" not in html


def test_inbox_without_sections(client):
    log_in(client, add_user("anna", sections=()))
    add_message("sv")
    html = html_of(client.get("/verwaltung/"))
    assert "kein Bereich zugewiesen" in html
    assert GOOD_TEXT not in html


def test_inbox_status_filter(client):
    log_in(client, add_user("anna"))
    add_message(text="Offene Nachricht", status="neu")
    add_message(text="Fertige Nachricht", status="erledigt")
    html = html_of(client.get("/verwaltung/?status=erledigt"))
    assert "Fertige Nachricht" in html
    assert "Offene Nachricht" not in html
    # Unknown filter: show everything instead of failing.
    html = html_of(client.get("/verwaltung/?status=quatsch"))
    assert "Fertige Nachricht" in html and "Offene Nachricht" in html


def test_inbox_open_questions_first(client):
    log_in(client, add_user("anna"))
    first = add_message(text="Erste Nachricht mit Rueckfrage")
    add_message(text="Zweite Nachricht ohne Rueckfrage")
    with app.cli_db() as c:
        c.execute("UPDATE messages SET neu_vom_schueler=1 WHERE id=?", (first,))
    html = html_of(client.get("/verwaltung/"))
    assert html.index("Erste Nachricht") < html.index("Zweite Nachricht")


# ---------- single message ----------

def test_message_page_of_other_section_is_404(client):
    log_in(client, add_user("anna", sections=("sv",)))
    mid = add_message("sozial")
    assert client.get(f"/verwaltung/{mid}").status_code == 404
    assert client.get("/verwaltung/9999").status_code == 404


def test_message_post_to_other_section_is_404(client):
    log_in(client, add_user("anna", sections=("sv",)))
    mid = add_message("sozial")
    response = client.post(f"/verwaltung/{mid}", data={"csrf": "csrf", "status": "erledigt", "antwort": "x"})
    assert response.status_code == 404
    assert get_chat(mid) == []
    assert get_message(mid)["status"] == "neu"


def test_message_answer_status_and_note(client):
    log_in(client, add_user("anna"))
    mid = add_message()
    with app.cli_db() as c:
        c.execute("UPDATE messages SET neu_vom_schueler=1 WHERE id=?", (mid,))

    response = client.post(f"/verwaltung/{mid}", data={
        "csrf": "csrf", "status": "in Bearbeitung", "antwort": "  Danke, wir schauen es uns an.  ",
        "notiz": "Mit Klassenvorstand reden"})
    assert response.status_code == 302

    msg = get_message(mid)
    assert msg["status"] == "in Bearbeitung"
    assert msg["notiz"] == "Mit Klassenvorstand reden"
    assert msg["neu_vom_schueler"] == 0  # answered, so no longer open
    assert get_chat(mid) == [("empfaenger", "Danke, wir schauen es uns an.")]
    assert "Gespeichert." in html_of(client.get(f"/verwaltung/{mid}"))


def test_message_note_only_keeps_question_open(client):
    log_in(client, add_user("anna"))
    mid = add_message()
    with app.cli_db() as c:
        c.execute("UPDATE messages SET neu_vom_schueler=1 WHERE id=?", (mid,))
    client.post(f"/verwaltung/{mid}", data={"csrf": "csrf", "status": "neu", "notiz": "später"})
    assert get_message(mid)["neu_vom_schueler"] == 1
    assert get_chat(mid) == []


def test_message_done_closes_question(client):
    log_in(client, add_user("anna"))
    mid = add_message()
    with app.cli_db() as c:
        c.execute("UPDATE messages SET neu_vom_schueler=1 WHERE id=?", (mid,))
    client.post(f"/verwaltung/{mid}", data={"csrf": "csrf", "status": "erledigt"})
    assert get_message(mid)["neu_vom_schueler"] == 0


def test_message_invalid_status_is_400(client):
    log_in(client, add_user("anna"))
    mid = add_message()
    assert client.post(f"/verwaltung/{mid}", data={"csrf": "csrf", "status": "gelöscht"}).status_code == 400


def test_message_post_without_csrf_is_400(client):
    log_in(client, add_user("anna"))
    mid = add_message()
    response = client.post(f"/verwaltung/{mid}", data={"csrf": "falsch", "status": "erledigt"})
    assert response.status_code == 400
    assert get_message(mid)["status"] == "neu"


def test_school_reply_visible_to_student_without_name(client):
    """Whole flow: admin answers -> student sees it as 'Schule', not as the username."""
    code = app.new_code()
    mid = add_message(code=code)
    log_in(client, add_user("frau.huber"))
    client.post(f"/verwaltung/{mid}", data={"csrf": "csrf", "status": "neu", "antwort": "Wir melden uns."})
    with client.session_transaction() as s:
        s.clear()
    html = html_of(client.post("/status", data={"code": code}))
    assert "Wir melden uns." in html
    assert "Schule" in html
    assert "huber" not in html


# ========== E-Mail tests ==========

# ---------- send_mails() ----------

def test_send_mails_without_settings_fails():
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        app.send_mails([("a@schule.test", "Hallo")], "Betreff")


def test_send_mails_builds_correct_message(mail_server):
    app.send_mails([("a@schule.test", "Hallo")], "Betreff")

    [msg] = mail_server.sent
    assert msg["To"] == "a@schule.test"
    assert msg["From"] == "postfach@test.invalid"
    assert msg["Subject"] == "Betreff"
    assert msg["Date"]
    assert msg.get_content().strip() == "Hallo"


def test_send_mails_uses_one_connection_for_many_mails(mail_server):
    app.send_mails([("a@schule.test", "1"), ("b@schule.test", "2")], "Betreff")
    assert len(mail_server.connections) == 1
    assert [m["To"] for m in mail_server.sent] == ["a@schule.test", "b@schule.test"]


def test_send_mails_starttls_is_default(mail_server):
    app.send_mails([("a@schule.test", "Hallo")], "Betreff")
    [conn] = mail_server.connections
    assert conn.kind == "plain"
    assert (conn.host, conn.port) == ("smtp.test.invalid", 587)
    assert conn.calls[0] == "starttls"


def test_send_mails_ssl(mail_server, monkeypatch):
    monkeypatch.setattr(app, "SMTP_SECURITY", "ssl")
    app.send_mails([("a@schule.test", "Hallo")], "Betreff")
    [conn] = mail_server.connections
    assert conn.kind == "ssl"
    assert "starttls" not in conn.calls


def test_send_mails_without_encryption(mail_server, monkeypatch):
    monkeypatch.setattr(app, "SMTP_SECURITY", "none")
    app.send_mails([("a@schule.test", "Hallo")], "Betreff")
    [conn] = mail_server.connections
    assert conn.kind == "plain"
    assert "starttls" not in conn.calls


def test_send_mails_logs_in_only_with_user(mail_server, monkeypatch):
    app.send_mails([("a@schule.test", "Hallo")], "Betreff")
    assert not any(c[0] == "login" for c in mail_server.connections[0].calls if isinstance(c, tuple))

    monkeypatch.setattr(app, "SMTP_USER", "postfach")
    monkeypatch.setattr(app, "SMTP_PASSWORD", "geheim")
    app.send_mails([("a@schule.test", "Hallo")], "Betreff")
    assert ("login", "postfach", "geheim") in mail_server.connections[1].calls


# ---------- run_notifications() ----------

def test_notify_nothing_new(mail_server):
    add_user("anna", "anna@schule.test")
    assert app.run_notifications() == "Nichts zu melden."
    assert mail_server.sent == []


def test_notify_nobody_has_email_for_section(mail_server):
    add_user("anna", "anna@schule.test", sections=("sozial",))
    add_message("sv")
    assert "kein Zugang" in app.run_notifications()
    assert mail_server.sent == []
    assert mail_flags() == [0]  # stays open, gets reported once someone has an address


def test_notify_sends_to_responsible_user_only(mail_server):
    add_user("anna", "anna@schule.test", sections=("sv",))
    add_user("bert", "bert@schule.test", sections=("sozial",))
    add_message("sv")
    add_message("sv", "Noch eine ganz andere Nachricht hier")

    app.run_notifications()

    [msg] = mail_server.sent
    assert msg["To"] == "anna@schule.test"
    body = msg.get_content()
    assert "Schülervertretung: 2" in body
    assert "http://postfach.test/verwaltung" in body
    assert mail_flags() == [1, 1]


def test_notify_mail_contains_no_message_text(mail_server):
    # Privacy: the mail only says "there is something new", never what.
    add_user("anna", "anna@schule.test")
    add_message("sv", GOOD_TEXT)
    app.run_notifications()
    assert GOOD_TEXT not in mail_server.sent[0].get_content()


def test_notify_one_mail_for_several_sections(mail_server):
    add_user("anna", "anna@schule.test", sections=("sv", "direktion"))
    add_message("sv")
    add_message("direktion", "Noch eine ganz andere Nachricht hier")

    app.run_notifications()

    [msg] = mail_server.sent
    body = msg.get_content()
    assert "Schülervertretung: 1" in body
    assert "Direktion: 1" in body


def test_notify_reports_each_message_only_once(mail_server):
    add_user("anna", "anna@schule.test")
    add_message("sv")
    app.run_notifications()
    assert app.run_notifications() == "Nichts zu melden."
    assert len(mail_server.sent) == 1


def test_notify_failure_keeps_messages_open(mail_server):
    add_user("anna", "anna@schule.test")
    add_message("sv")
    mail_server.fail = ConnectionRefusedError("Server nicht erreichbar")

    with pytest.raises(RuntimeError, match="fehlgeschlagen"):
        app.run_notifications()
    assert mail_flags() == [0]  # not lost: will be retried

    mail_server.fail = None
    app.run_notifications()
    assert len(mail_server.sent) == 1
    assert mail_flags() == [1]


def test_notify_dry_run_sends_nothing(mail_server):
    add_user("anna", "anna@schule.test")
    add_message("sv")
    result = app.run_notifications(dry_run=True)
    assert "Nichts gesendet" in result
    assert mail_server.sent == []
    assert mail_flags() == [0]


class RaceConnection:
    """Wraps a DB connection: right before the claim (UPDATE ... SET mail_gesendet=2), a second
    run grabs all open messages, as if two notification runs started at the same moment."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, *args):
        if "SET mail_gesendet=2" in sql:
            with closing(sqlite3.connect(app.DB_PATH)) as other:
                other.execute("UPDATE messages SET mail_gesendet=2 WHERE mail_gesendet=0")
                other.commit()
        return self._conn.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_notify_other_run_was_faster(mail_server, monkeypatch):
    add_user("anna", "anna@schule.test")
    add_message()
    real_cli_db = app.cli_db

    @contextmanager
    def racing_cli_db():
        with real_cli_db() as conn:
            yield RaceConnection(conn)

    monkeypatch.setattr(app, "cli_db", racing_cli_db)
    assert app.run_notifications() == "Nichts zu melden."
    assert mail_server.sent == []  # the other run sends the mail, not this one


def test_student_reply_triggers_new_notification(client, mail_server, monkeypatch):
    """Whole flow: student writes -> mail -> student asks again via code -> mail again."""
    monkeypatch.setattr(app, "MIN_SECONDS", 0)
    add_user("anna", "anna@schule.test")

    html = client.post("/senden", data={"empfaenger": "sv", "kategorie": "Unterricht",
                                        "text": GOOD_TEXT, "zt": app.make_token()}).get_data(as_text=True)
    code = re.search(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", html).group()
    app.run_notifications()
    assert len(mail_server.sent) == 1

    response = client.post("/status/schreiben", data={"code": code, "text": "Gibt es schon Neuigkeiten?"})
    assert response.status_code == 200
    app.run_notifications()
    assert len(mail_server.sent) == 2


# ---------- CLI: flask --app app test-mail / send-notifications ----------

def test_cli_test_mail(mail_server):
    result = app.app.test_cli_runner().invoke(args=["test-mail", "anna@schule.test"])
    assert result.exit_code == 0, result.output
    assert "Testmail gesendet" in result.output
    assert mail_server.sent[0]["To"] == "anna@schule.test"


def test_cli_test_mail_rejects_bad_address(mail_server):
    result = app.app.test_cli_runner().invoke(args=["test-mail", "keine-adresse"])
    assert result.exit_code != 0
    assert mail_server.sent == []


def test_cli_send_notifications_reports_failure(mail_server):
    add_user("anna", "anna@schule.test")
    add_message("sv")
    mail_server.fail = ConnectionRefusedError("Server nicht erreichbar")
    result = app.app.test_cli_runner().invoke(args=["send-notifications"])
    assert result.exit_code != 0
    assert "fehlgeschlagen" in result.output


# ========== CLI: user and data management ==========

def cli(*args, input=None):
    return app.app.test_cli_runner().invoke(args=list(args), input=input)


def users():
    with app.cli_db() as c:
        return c.execute("SELECT username, role, email, sections FROM users ORDER BY username").fetchall()


def message_ids():
    with app.cli_db() as c:
        return [r[0] for r in c.execute("SELECT id FROM messages ORDER BY id")]


# ---------- create-user ----------

def test_cli_create_user(client):
    result = cli("create-user", "Anna", "--password", PASSWORD, "--email", "anna@schule.test",
                 "--section", "sv", "--section", "direktion", "--section", "sv")
    assert result.exit_code == 0, result.output
    assert users() == [("anna", "empfaenger", "anna@schule.test", "sv,direktion")]  # lowercased, no doubles
    assert login_form(client, "anna", PASSWORD).status_code == 302  # password really works


def test_cli_create_user_without_section_gives_hint():
    result = cli("create-user", "anna", "--password", PASSWORD)
    assert result.exit_code == 0, result.output
    assert "set-sections anna" in result.output


def test_cli_create_user_short_password():
    result = cli("create-user", "anna", "--password", "kurz")
    assert result.exit_code != 0
    assert "10 Zeichen" in result.output
    assert users() == []


def test_cli_create_user_bad_email():
    result = cli("create-user", "anna", "--password", PASSWORD, "--email", "anna-at-schule")
    assert result.exit_code != 0
    assert users() == []


def test_cli_create_user_unknown_section():
    assert cli("create-user", "anna", "--password", PASSWORD, "--section", "hausmeister").exit_code != 0
    assert users() == []


def test_cli_create_user_duplicate():
    add_user("anna")
    result = cli("create-user", "ANNA", "--password", PASSWORD)
    assert result.exit_code != 0
    assert "gibt es schon" in result.output


# ---------- list-users / set-sections / set-email / rename-user / set-password ----------

def test_cli_list_users():
    assert "Noch keine Zugaenge" in cli("list-users").output
    add_user("anna", "anna@schule.test", sections=("sv", "sozial"), role="admin")
    assert "anna  (admin)  anna@schule.test  Bereiche: sv,sozial" in cli("list-users").output


def test_cli_set_sections():
    add_user("anna", sections=("sv",))
    assert cli("set-sections", "anna", "sozial", "direktion").exit_code == 0
    assert users()[0][3] == "sozial,direktion"
    assert cli("set-sections", "anna").exit_code == 0  # none: sees nothing
    assert users()[0][3] == ""


def test_cli_unknown_user():
    for args in (["set-sections", "niemand", "sv"], ["set-email", "niemand", "a@b.at"],
                 ["set-role", "niemand", "admin"], ["remove-user", "niemand", "--yes"],
                 ["set-password", "niemand", "--password", PASSWORD]):
        result = cli(*args)
        assert result.exit_code != 0, args
        assert "nicht gefunden" in result.output, args


def test_cli_set_and_remove_email():
    add_user("anna")
    assert cli("set-email", "anna", "anna@schule.test").exit_code == 0
    assert users()[0][2] == "anna@schule.test"
    assert cli("set-email", "anna", "quatsch").exit_code != 0
    assert users()[0][2] == "anna@schule.test"
    result = cli("set-email", "anna")
    assert "entfernt" in result.output
    assert users()[0][2] == ""


def test_cli_rename_user():
    add_user("anna")
    add_user("bert")
    assert cli("rename-user", "anna", "Anna.M").exit_code == 0
    assert [u[0] for u in users()] == ["anna.m", "bert"]
    result = cli("rename-user", "bert", "anna.m")
    assert result.exit_code != 0
    assert "gibt es schon" in result.output


def test_cli_set_password(client):
    add_user("anna", password="altes-passwort-123")
    assert cli("set-password", "anna", "--password", "kurz").exit_code != 0
    assert cli("set-password", "anna", "--password", PASSWORD).exit_code == 0
    assert login_form(client, "anna", PASSWORD).status_code == 302


# ---------- last admin protection ----------

def test_cli_last_admin_cannot_be_demoted_or_removed():
    add_user("chef", role="admin")
    result = cli("set-role", "chef", "empfaenger")
    assert result.exit_code != 0
    assert "letzte Admin" in result.output
    result = cli("remove-user", "chef", "--yes")
    assert result.exit_code != 0
    assert users()[0][:2] == ("chef", "admin")


def test_cli_admin_can_be_removed_if_another_exists():
    add_user("chef", role="admin")
    add_user("vize", role="admin")
    assert cli("set-role", "chef", "empfaenger").exit_code == 0
    assert cli("remove-user", "vize", "--yes").exit_code != 0  # now vize is the last one
    assert cli("remove-user", "chef", "--yes").exit_code == 0
    assert [u[0] for u in users()] == ["vize"]


def test_cli_remove_user_asks_first():
    add_user("anna")
    assert cli("remove-user", "anna", input="n\n").exit_code != 0
    assert len(users()) == 1
    assert cli("remove-user", "anna", input="y\n").exit_code == 0
    assert users() == []


# ---------- stats ----------

def test_cli_stats():
    add_user("anna")
    add_message("sv", datum="2026-01-01")
    add_message("sozial", "Noch eine ganz andere Nachricht", datum="2026-03-15", status="erledigt")
    out = cli("stats").output
    assert "Nachrichten gesamt: 2" in out
    assert "an Schülervertretung: 1" in out
    assert "erledigt: 1" in out
    assert "Zeitraum: 2026-01-01 bis 2026-03-15" in out
    assert "Zugaenge: 1" in out


def test_cli_stats_empty():
    out = cli("stats").output
    assert "Nachrichten gesamt: 0" in out
    assert "Zeitraum" not in out


# ---------- delete-message / purge / clear-messages / reset-db ----------

def test_cli_delete_message_also_deletes_chat():
    mid = add_message()
    other = add_message(text="Bleibt bestehen, ganz sicher ja")
    add_chat(mid, "schueler")
    assert cli("delete-message", str(mid), "--yes").exit_code == 0
    assert message_ids() == [other]
    assert get_chat(mid) == []  # ON DELETE CASCADE


def test_cli_delete_message_unknown():
    result = cli("delete-message", "42", "--yes")
    assert result.exit_code != 0
    assert "nicht gefunden" in result.output


def test_cli_purge_by_age():
    old = (date.today() - timedelta(days=100)).isoformat()
    new = (date.today() - timedelta(days=10)).isoformat()
    add_message(datum=old)
    keep = add_message(text="Neuere Nachricht bleibt im System", datum=new)
    result = cli("purge", "--days", "30", "--yes")
    assert result.exit_code == 0, result.output
    assert "1 Nachricht(en) geloescht" in result.output
    assert message_ids() == [keep]


def test_cli_purge_only_done():
    old = (date.today() - timedelta(days=100)).isoformat()
    keep = add_message(datum=old, status="in Bearbeitung")
    add_message(text="Erledigte alte Nachricht hier drin", datum=old, status="erledigt")
    assert cli("purge", "--days", "30", "--only-done", "--yes").exit_code == 0
    assert message_ids() == [keep]


def test_cli_purge_nothing_to_do():
    add_message(datum=date.today().isoformat())
    assert "Keine passenden" in cli("purge", "--days", "30", "--yes").output
    assert len(message_ids()) == 1


def test_cli_purge_negative_days_rejected():
    assert cli("purge", "--days", "-1", "--yes").exit_code != 0


def test_cli_clear_messages_keeps_users():
    add_user("anna")
    add_message()
    assert cli("clear-messages", "--yes").exit_code == 0
    assert message_ids() == []
    assert len(users()) == 1


def test_cli_delete_commands_ask_first():
    """Without --yes, every delete command asks. 'n' keeps everything, 'y' deletes."""
    old = (date.today() - timedelta(days=100)).isoformat()
    for args in (["delete-message", "1"], ["purge", "--days", "30"], ["clear-messages"]):
        add_message(datum=old, text=f"Nachricht fuer den Befehl {args[0]} hier")
        assert cli(*args, input="n\n").exit_code != 0, args
        assert len(message_ids()) == 1, args
        result = cli(*args, input="y\n")
        assert result.exit_code == 0, (args, result.output)
        assert message_ids() == [], args


def test_cli_reset_db_needs_exact_confirmation():
    add_user("anna")
    add_message()
    assert cli("reset-db", input="ja\n").exit_code != 0
    assert len(users()) == 1
    assert cli("reset-db", input="LOESCHEN\n").exit_code == 0
    assert users() == [] and message_ids() == []


# ---------- backup ----------

def test_cli_backup(tmp_path):
    add_message()
    target = tmp_path / "sicherung.db"
    result = cli("backup", str(target))
    assert result.exit_code == 0, result.output
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600  # contains messages: owner only
    with closing(sqlite3.connect(target)) as c:
        assert c.execute("SELECT text FROM messages").fetchone()[0] == GOOD_TEXT


def test_cli_backup_does_not_overwrite(tmp_path):
    target = tmp_path / "sicherung.db"
    target.write_text("wichtig")
    result = cli("backup", str(target))
    assert result.exit_code != 0
    assert target.read_text() == "wichtig"


# ---------- send-notifications ----------

def test_cli_send_notifications_success(mail_server):
    add_user("anna", "anna@schule.test")
    add_message()
    result = cli("send-notifications")
    assert result.exit_code == 0, result.output
    assert "1 Mail(s) gesendet (1 Nachricht(en))" in result.output


def test_cli_send_notifications_dry_run(mail_server):
    add_user("anna", "anna@schule.test")
    add_message()
    result = cli("send-notifications", "--dry-run")
    assert "Schülervertretung: 1 an 1 Adresse(n)" in result.output
    assert mail_server.sent == []


def test_cli_test_mail_reports_server_error(mail_server):
    mail_server.fail = ConnectionRefusedError("Server nicht erreichbar")
    result = cli("test-mail", "anna@schule.test")
    assert result.exit_code != 0
    assert "nicht erreichbar" in result.output


# ========== Logging ==========

# ---------- audit() ----------

def test_audit_line_format(audit_lines):
    app.audit("msg_status", "7:erledigt", actor="anna")
    assert audit_lines == ["anna msg_status 7:erledigt"]


def test_audit_actor_is_cli_outside_requests(audit_lines):
    app.audit("reset_db")
    assert audit_lines == ["CLI reset_db -"]


def test_audit_actor_from_session(audit_lines):
    with app.app.test_request_context():
        app.session["username"] = "anna"
        app.audit("msg_reply", 3)
    assert audit_lines == ["anna msg_reply 3"]


def test_audit_actor_unknown_without_login(audit_lines):
    with app.app.test_request_context():
        app.audit("logout", "unbekannt")
    assert audit_lines == ["- logout unbekannt"]


def test_audit_log_goes_to_rotating_file_only():
    assert app.audit_log.propagate is False  # not mixed into the service log on stdout
    assert app._h.baseFilename == os.path.abspath(app.AUDIT_LOG)
    assert app._h.when == "MIDNIGHT"
    assert app._h.backupCount == 180
    app.audit("test_mail", "datei-test")
    app._h.flush()
    with open(app.AUDIT_LOG, encoding="utf-8") as f:
        assert "CLI test_mail datei-test" in f.read()


def test_werkzeug_access_log_stays_off():
    # werkzeug's request log contains client IPs
    assert not logging.getLogger("werkzeug").isEnabledFor(logging.INFO)


# ---------- web: login, logout, messages ----------

def test_audit_login_ok(client, audit_lines):
    add_user("anna", password=PASSWORD)
    login_form(client, " Anna ", PASSWORD)
    assert audit_lines == ["anna login_ok anna"]


def test_audit_login_fail_known_user(client, audit_lines):
    add_user("anna", password=PASSWORD)
    login_form(client, "anna", "falsch")
    assert audit_lines == ["- login_fail anna"]


def test_audit_login_fail_never_logs_typed_name(client, audit_lines):
    # People type their password into the username field; that must never end up in a log.
    login_form(client, PASSWORD, "egal")
    assert audit_lines == ["- login_fail unbekannt"]
    assert not any(PASSWORD in line for line in audit_lines)


def test_audit_lockout_logged_once(client, audit_lines):
    add_user("anna", password=PASSWORD)
    for _ in range(7):  # attempts 6 and 7 are blocked and not logged again
        login_form(client, "anna", "falsch")
    assert audit_lines.count("- login_fail anna") == 5
    assert audit_lines.count("- lockout anna") == 1
    assert audit_lines.index("- lockout anna") == 5  # right after the 5th failure


def test_audit_logout(client, audit_lines):
    add_user("anna", password=PASSWORD)
    login_form(client, "anna", PASSWORD)
    with client.session_transaction() as s:
        s["csrf"] = "csrf"  # login clears the session, including the old token
    client.post("/verwaltung/logout", data={"csrf": "csrf"})
    assert audit_lines == ["anna login_ok anna", "anna logout anna"]


def test_audit_message_reply_and_status(client, audit_lines):
    log_in(client, add_user("anna"))
    with client.session_transaction() as s:
        s["username"] = "anna"
    mid = add_message()
    client.post(f"/verwaltung/{mid}", data={"csrf": "csrf", "status": "in Bearbeitung",
                                            "antwort": "Geheime Antwort", "notiz": "Geheime Notiz"})
    assert audit_lines == [f"anna msg_reply {mid}", f"anna msg_status {mid}:in Bearbeitung"]
    assert not any("Geheim" in line for line in audit_lines)  # never content


def test_audit_message_note_only_not_logged(client, audit_lines):
    log_in(client, add_user("anna"))
    mid = add_message()
    client.post(f"/verwaltung/{mid}", data={"csrf": "csrf", "status": "neu", "notiz": "später"})
    assert audit_lines == []


def test_student_actions_are_not_logged(client, audit_lines, caplog, monkeypatch):
    monkeypatch.setattr(app, "MIN_SECONDS", 0)
    code = re.search(CODE_RE, html_of(send_form(client))).group()
    client.post("/status", data={"code": code})
    client.post("/status/schreiben", data={"code": code, "text": "Noch eine Frage"})
    assert audit_lines == []
    assert [r for r in caplog.records if r.name.startswith("postfach")] == []


# ---------- CLI ----------

@pytest.mark.parametrize("args, expected", [
    (["create-user", "Carl", "--password", PASSWORD], "CLI user_create carl"),
    (["set-sections", "Anna", "sv"], "CLI section_set anna"),
    (["set-password", "anna", "--password", PASSWORD], "CLI password_set anna"),
    (["rename-user", "Anna", "Anja"], "CLI user_rename anna->anja"),
    (["set-role", "anna", "empfaenger"], "CLI role_set anna:empfaenger"),
    (["remove-user", "anna", "--yes"], "CLI user_remove anna"),
    (["set-email", "anna", "anna@schule.test"], "CLI email_set anna"),
    (["delete-message", "1", "--yes"], "CLI msg_delete 1"),
    (["purge", "--days", "30", "--yes"], f"CLI purge 1<{(date.today() - timedelta(days=30)).isoformat()}"),
    (["clear-messages", "--yes"], "CLI clear_messages 1"),
    (["reset-db", "--yes"], "CLI reset_db -"),
])
def test_audit_cli_commands(audit_lines, args, expected):
    add_user("anna", role="admin")
    add_user("bert", role="admin")
    add_message(datum="2026-01-01")
    result = cli(*args)
    assert result.exit_code == 0, result.output
    assert audit_lines == [expected]


def test_audit_cli_failed_commands_not_logged(audit_lines):
    add_user("anna", role="admin")
    cli("set-role", "anna", "empfaenger")         # last admin
    cli("remove-user", "anna", input="n\n")       # aborted
    cli("set-email", "niemand", "x@schule.test")  # unknown user
    cli("delete-message", "99", "--yes")          # unknown message
    assert audit_lines == []


def test_audit_cli_backup_logs_file_name_only(audit_lines, tmp_path):
    ziel = tmp_path / "sicherung.db"
    assert cli("backup", str(ziel)).exit_code == 0
    assert audit_lines == ["CLI backup sicherung.db"]


def test_audit_cli_test_mail(mail_server, audit_lines):
    cli("test-mail", "anna@schule.test")
    assert audit_lines == ["CLI test_mail ok"]
    assert not any("anna@schule.test" in line for line in audit_lines)


# ---------- notifications ----------

def test_audit_digest_sent(mail_server, audit_lines):
    add_user("anna", "anna@schule.test")
    add_message("sv")
    add_message("sv", "Noch eine andere Nachricht an die SV")
    app.run_notifications()
    assert audit_lines == ["system digest_sent 1mail/2msg"]


def test_audit_digest_failed_logs_error_type_only(mail_server, audit_lines):
    add_user("anna", "anna@schule.test")
    add_message("sv")
    mail_server.fail = ConnectionRefusedError("smtp.test.invalid nicht erreichbar")
    with pytest.raises(RuntimeError):
        app.run_notifications()
    assert audit_lines == ["system digest_failed ConnectionRefusedError"]


def test_audit_digest_nothing_to_do_or_dry_run_not_logged(mail_server, audit_lines):
    app.run_notifications()
    add_user("anna", "anna@schule.test")
    add_message("sv")
    app.run_notifications(dry_run=True)
    assert audit_lines == []
