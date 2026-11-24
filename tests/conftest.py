"""Shared test setup."""
import os
import sqlite3
import sys
import tempfile
from contextlib import closing

import pytest

_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")
os.environ["SECRET_KEY"] = "test-secret"

# Make `import app` work no matter which folder you start pytest from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module  # noqa: E402  (must come after setting DB_PATH)


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    # In-memory rate limit and duplicate check would otherwise leak between tests.
    app_module._recent.clear()
    app_module._seen.clear()
    app_module._fails.clear()  # login lockouts
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    monkeypatch.setattr(app_module, "DB_PATH", path)
    with closing(sqlite3.connect(path)) as c:
        app_module.migrate(c)
        c.commit()


# ========== E-Mail ==========

@pytest.fixture(autouse=True)
def no_real_mail(monkeypatch):
    """SMTP settings come from the environment at import time; make sure no test can
    send real mail, even if they are set in the shell. Use `mail_server` to test mail."""
    for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.setattr(app_module, name, "")
    monkeypatch.setattr(app_module, "SMTP_SECURITY", "starttls")

    def refuse(*args, **kwargs):
        raise AssertionError("Test tried to open a real SMTP connection. Use the `mail_server` fixture.")

    monkeypatch.setattr(app_module.smtplib, "SMTP", refuse)
    monkeypatch.setattr(app_module.smtplib, "SMTP_SSL", refuse)


class FakeConnection:
    """Stands in for smtplib.SMTP / SMTP_SSL and records calls and messages."""

    def __init__(self, kind, host, port, **kwargs):
        self.kind = kind  # "plain" (SMTP) or "ssl" (SMTP_SSL)
        self.host = host
        self.port = port
        self.calls = []
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.sent.append(msg)


class FakeMailServer:
    def __init__(self):
        self.connections = []
        self.fail = None  # exception to raise on connect

    def connect(self, kind, host, port, **kwargs):
        if self.fail:
            raise self.fail
        conn = FakeConnection(kind, host, port, **kwargs)
        self.connections.append(conn)
        return conn

    @property
    def sent(self):
        return [m for c in self.connections for m in c.sent]


@pytest.fixture
def mail_server(no_real_mail, monkeypatch):
    """Fake SMTP settings and server. Depends on `no_real_mail` so it runs after it."""
    server = FakeMailServer()
    monkeypatch.setattr(app_module, "SMTP_HOST", "smtp.test.invalid")
    monkeypatch.setattr(app_module, "SMTP_PORT", 587)
    monkeypatch.setattr(app_module, "SMTP_FROM", "postfach@test.invalid")
    monkeypatch.setattr(app_module, "BASE_URL", "http://postfach.test")
    monkeypatch.setattr(app_module.smtplib, "SMTP", lambda *a, **kw: server.connect("plain", *a, **kw))
    monkeypatch.setattr(app_module.smtplib, "SMTP_SSL", lambda *a, **kw: server.connect("ssl", *a, **kw))
    return server
