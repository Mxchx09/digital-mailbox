"""Shared setup for all tests. pytest loads this file automatically before any test runs."""
import os
import sys
import tempfile

import pytest

_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")
os.environ["SECRET_KEY"] = "test-secret"

# Make `import app` work no matter which folder you start pytest from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module  # noqa: E402  (must come after setting DB_PATH)


@pytest.fixture
def client():
    """A fake browser that talks to the app without starting a server.

    A test gets it simply by having a parameter named `client`; pytest sees the name
    and calls this function for it ("fixture").
    """
    app_module.app.config["TESTING"] = True
    # The app keeps a few things in memory (rate limit, duplicate check). Clear them so
    # one test can't affect the next.
    app_module._recent.clear()
    app_module._seen.clear()
    with app_module.app.test_client() as c:
        yield c
