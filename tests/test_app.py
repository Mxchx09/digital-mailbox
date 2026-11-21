"""
How to run tests:
- Activate the venv (with requirements-dev.txt installed): source .venv/bin/activate
- Run all tests:            pytest
- Run one file, verbose:    pytest -v tests/test_app.py
- Run tests matching a name: pytest -k validate
"""

import re

import pytest

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


# ========== HTTP requests ==========

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


# ========== E-Mail tests ==========

def add_user(username, email="", sections=("sv",), role="empfaenger"):
    with app.cli_db() as c:
        c.execute("INSERT INTO users (username, pw_hash, role, email, sections) VALUES (?,?,?,?,?)",
                  (username, "x", role, email, ",".join(sections)))


def add_message(empfaenger="sv", text=GOOD_TEXT):
    with app.cli_db() as c:
        c.execute("INSERT INTO messages (code_hash, empfaenger, kategorie, text, datum) "
                  "VALUES (?, ?, 'Sonstiges', ?, '2026-01-01')",
                  (app.hash_code(app.new_code()), empfaenger, text))


def mail_flags():
    """mail_gesendet per message: 0 = not reported yet, 1 = reported."""
    with app.cli_db() as c:
        return [r[0] for r in c.execute("SELECT mail_gesendet FROM messages ORDER BY id")]


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
