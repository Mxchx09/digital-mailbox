# AGENTS.md

Guidance for AI coding agents working on this repository. Human-facing setup and
CLI docs live in `README.md` (German).

**Project:** Schul-Postfach – an anonymous mailbox where students send messages to
school contacts (student council, social work, direction) and fetch replies with a
random code. Flask + SQLite, deployed with Docker behind the school's reverse proxy.

## Workflow rules

- **Never commit, push or open pull requests on your own.** Leave changes in the
  working tree for the user to review. Only run `git commit` / `git push` / `gh pr create`
  when the user explicitly asks for it in the current request.
- Run `pytest` before reporting a change as done, and say so if tests fail.
- Keep changes small and in the existing style; don't add dependencies, frameworks,
  build steps or new files/modules without asking.

## Anonymity rules (most important – do not break these)

Anonymity is the core feature. Any change must preserve:

- **No identifying data is stored or logged:** no IP addresses, user agents,
  device info or time of day. Messages and chat entries store only `date.today()`.
- `ProxyFix` must stay **without `x_for`** – the app must never see a client IP.
- The `werkzeug` logger stays disabled; gunicorn runs with `--access-logfile /dev/null`.
  Don't add logging that includes request data, message text or codes.
- The reply code is stored **only as a SHA-256 hash** (`hash_code`). The plain code
  must never appear in a URL, log or DB. That's why `/senden` and `/status/schreiben`
  render the result page directly instead of redirecting – keep it that way.
- **No cookies for students.** The session/CSRF cookie is only used under `/verwaltung`
  (the footer promises "setzt keine Cookies"). Don't call `session` or `csrf_token()`
  on public pages.
- Rate limiting (`_recent`) and duplicate detection (`_seen`) are global, in RAM and
  never keyed by client. Don't make them per-IP or persistent.
- Notification mails never contain message content, categories or codes – only counts
  per section and a link.
- Access control: a user only sees messages whose `empfaenger` is in their `sections`.
  Messages from other sections return **404, not 403** (their existence must not leak).
- No third-party requests, analytics, fonts or CDNs.

## Architecture

- Everything server-side is in **`app.py`** (single file, intentionally). Plain
  `sqlite3`, no ORM.
- `templates/` – Jinja templates, all extend `base.html`. `static/` – CSS, small
  vanilla JS files, icons.
- **One gunicorn worker with threads** (see `Dockerfile`): `_recent`, `_seen` and
  `_fails` (login lockout) are shared in-memory state. Don't switch to multiple workers.
- The daily notification scheduler (`start_scheduler`) only starts under gunicorn,
  not for `flask` CLI commands.
- Configuration comes **only from environment variables** read at import time.
  Never hard-code secrets or put them in the repo.

### Database

- Schema changes go into **both** `SCHEMA` and `migrate()`. Migrations must work on
  existing production DBs (add columns with defaults, never drop data silently).
- **Never rename keys in `RECIPIENTS`** once messages exist – they're stored in
  `messages.empfaenger` and `users.sections`. Labels, hints and topics may change.
- `messages.mail_gesendet` has three states: `0` = not notified, `2` = claimed by a
  running notification job, `1` = notified. Claiming must stay a single atomic
  `UPDATE ... RETURNING`, so concurrent runs never send twice.
- Connections use `PRAGMA foreign_keys=ON` (chat cascades with its message) and
  `PRAGMA secure_delete=ON`. Delete commands run `VACUUM` afterwards.

### Admin features

- Account and data management is done via **Flask CLI commands** (`flask --app app <cmd>`),
  not a web UI. New admin features should follow that pattern.
- Destructive commands ask for confirmation and offer `--yes`; keep the
  "last admin can't be removed/demoted" checks.
- All POSTs under `/verwaltung` are CSRF-checked in `protect_admin_posts`; forms there
  need `<input type="hidden" name="csrf" value="{{ csrf_token() }}">`.

## Frontend

- CSP is `default-src 'self'`: **no inline `<script>`, no inline `style=` or `<style>`,
  no external resources.** JS goes into a file in `static/`, loaded with `defer`.
- Pages must work **without JavaScript** (e.g. topics are shown grouped by recipient
  as a fallback; `empfaenger.js` only enhances).
- Pass data to JS via `data-*` attributes (see `data-topics` in `index.html`).
- Keep the JS dependency-free and small. Design tokens are CSS variables in
  `static/style.css` `:root`. Layout must work on phones.

## Language and conventions

- **User-facing text is German** (with umlauts: ä, ö, ü, ß), addressing students
  informally ("du").
- Code comments and CLI output in `app.py` are German **without umlauts**
  (`ae`, `oe`, `ue`, `ss`) – follow the surrounding style.
- Tests, commit messages and this file are in English.
- Route names and DB columns are German (`senden`, `empfaenger`, `datum` …); keep
  new names consistent with that.

## Testing

```bash
source .venv/bin/activate        # with requirements-dev.txt installed
pytest                           # all tests
pytest -k validate               # by name
```

- `tests/conftest.py` already gives each test a fresh temp DB, clears in-memory
  state (`client` fixture) and **blocks real SMTP**. Use the `mail_server` fixture to
  test mail; it records sent messages.
- Submitting the form in tests needs a valid `zt` token (`app.make_token()`) and
  `monkeypatch.setattr(app, "MIN_SECONDS", 0)` to skip the bot delay.
- Add tests for new behaviour, especially anything touching anonymity, access control
  or notifications.

## Keep docs in sync

- New or changed **environment variable** → update the table in `README.md`,
  `.env.example` and `docker-compose.yml`.
- New or changed **CLI command** → update the command list in `README.md`.
- Don't reference local, untracked files (personal scripts, `.env`, local DBs) in
  shared docs or code.
