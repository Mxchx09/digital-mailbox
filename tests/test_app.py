"""First tests for app.py.

How pytest works, in short:
- It finds files named test_*.py and runs every function whose name starts with test_.
- Inside a test you use plain `assert`. If the assert is false, the test fails and
  pytest shows you what the values were.
- Run all tests:            pytest
- Run one file, verbose:    pytest -v tests/test_app.py
- Run tests matching a name: pytest -k validate
"""
import re

import app


# ---------- validate(): pure function, easiest kind of test ----------
# Pure = same input always gives same output, no database, no web request.
# So we just call it and check the result.

GOOD_TEXT = "Im Klassenzimmer ist es immer viel zu kalt"


def test_validate_accepts_good_message():
    assert app.validate("sv", "Unterricht", GOOD_TEXT) is None  # None means "no error"


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


# ---------- hash_code(): also pure ----------
# The code a student gets is stored only as a hash. The student may type it back
# with lowercase letters, spaces or without dashes, and it must still match.

def test_hash_code_ignores_case_and_dashes():
    assert app.hash_code("abcd-efgh-jkmn-pqrs") == app.hash_code("ABCDEFGHJKMNPQRS")


def test_hash_code_does_not_contain_the_code():
    code = app.new_code()
    assert code.replace("-", "") not in app.hash_code(code)


# ---------- /senden: a real request through the app ----------
# This uses the `client` fixture from conftest.py (a fake browser).

def test_send_message_and_look_it_up(client, monkeypatch):
    # The form refuses submissions faster than MIN_SECONDS (bot protection).
    # monkeypatch temporarily changes a value just for this test, then puts it back.
    monkeypatch.setattr(app, "MIN_SECONDS", 0)

    response = client.post("/senden", data={
        "empfaenger": "sv",
        "kategorie": "Unterricht",
        "text": GOOD_TEXT,
        "zt": app.make_token(),
    })
    assert response.status_code == 200

    # The thank-you page shows the code. Pull it out of the HTML.
    html = response.get_data(as_text=True)
    code = re.search(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", html).group()

    # Anonymity: the code must not end up in a URL (no redirect to e.g. /danke?code=...)
    assert "Location" not in response.headers

    # Looking the code up on the status page must find the message again.
    status = client.post("/status", data={"code": code})
    assert GOOD_TEXT in status.get_data(as_text=True)
