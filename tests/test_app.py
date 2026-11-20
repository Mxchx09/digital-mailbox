"""
How to run tests:
- Activate the venv (with requirements-dev.txt installed): source .venv/bin/activate
- Run all tests:            pytest
- Run one file, verbose:    pytest -v tests/test_app.py
- Run tests matching a name: pytest -k validate
"""

import re

import app

# ========== Pure functions ==========

# ---------- validate() ----------
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
# These take `client` only so conftest.py clears the memory of seen messages first.
# That way every test starts fresh and works alone or in any order.

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
# This uses the `client` fixture from conftest.py (a fake browser)
def test_send_message_and_look_it_up(client, monkeypatch):
    # The form refuses submissions faster than MIN_SECONDS (bot protection).
    # monkeypatch temporarily changes a value just for this test, then puts it back.
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

    # The thank-you page shows the code. Pull it out of the HTML.
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
    assert response.status_code == 302  # redirect...
    assert response.headers["Location"].endswith("/verwaltung/login")  # ...to the login page
