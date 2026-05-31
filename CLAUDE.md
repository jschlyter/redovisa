# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Redovisa** is a FastAPI web application for expense reporting. Users authenticate via OIDC, fill in an expense form, and submit receipts. The app exports reports via SMTP email (with a merged PDF attachment) and optionally to a Google Sheet.

## Commands

```bash
# Run tests
uv run pytest

# Run a single test file
uv run pytest tests/test_session.py

# Lint
uv run ruff check

# Format
uv run ruff format
uv run ruff check --select I --fix

# Run the server
uv run redovisa
uv run redovisa --debug --port 8080
```

Pre-commit hooks run `ruff-check` and `ruff-format` automatically on commit.

## Architecture

### Startup and configuration

`redovisa/server.py` contains both the `Redovisa` class (a `FastAPI` subclass) and the `main()` CLI entry point. The app is assembled in `__init__`: settings are loaded, middleware is stacked, exporters are configured, and the router is mounted.

Configuration is loaded **exclusively from `redovisa.toml`** — there is no env-var fallback (see `settings_customise_sources` in `redovisa/settings.py`). The example config is `redovisa.exempel.toml`. Key sections: `[oidc]`, `[smtp]`, `[google]`, `[redis]`, `[users]`, `[context]`.

`[context]` is a free-form dict injected into every Jinja2 template render. `[context.accounts]` maps account numbers to display names for the expense form.

### OIDC middleware (`redovisa/oidc/`)

`OidcMiddleware` is an ASGI middleware that intercepts every request before it reaches the router:

- **`/login`** → redirects to the OIDC provider's authorization endpoint
- **`/callback`** → exchanges the auth code for an ID token, validates it, creates a session, and redirects
- **`/logout`** → deletes the session cookie and Redis entry
- All other paths → checks for a valid session cookie; redirects to login if absent

The session is stored in Redis using `SessionHandler` (`oidc/session.py`). When Redis is not configured, `fakeredis.FakeRedis()` is used for in-memory storage (sessions lost on restart).

The OIDC `state` parameter is a compact **JWE token** (not a plain nonce), encoded by `StateHandler` (`oidc/state.py`) using `jwcrypto`. It carries `session_id` and the `next` redirect path. If `state_secret` is not set in config, a random key is generated each run (state won't survive restarts).

JWK sets from the OIDC issuer are fetched at startup and refreshed lazily based on the HTTP `Expires` header, clamped to `[60s, 24h]`.

### Request flow after authentication

The middleware sets `scope["state"]["session"]` to a `Session` object. Views access it via `request.state.session`. The logger bound to the request is at `request.state.logger`.

### Exporters (`redovisa/export.py`)

Two exporters implement `ExpenseExporter.export()`:

- **`SmtpExpenseExporter`**: renders the Jinja2 `mail.j2` template as HTML, builds a `PdfRenderer` (report HTML + receipt images/PDFs merged), and sends via SMTP. Set `smtp.test = true` to print to stdout instead of sending.
- **`GoogleSheetExpenseExporter`**: appends rows to two worksheets (reports summary + line items) using a Google service account.

Multiple exporters can be active simultaneously. They are called sequentially in `views.py:submit_expense`.

### PDF generation (`redovisa/pdf.py`)

`PdfRenderer` accumulates pages from HTML (via `xhtml2pdf`/`pisa`), images (via `reportlab`+`PIL`, respecting EXIF orientation), and raw PDFs, then merges them into a single PDF using `pypdf.PdfWriter`.

### Users allowlist (`redovisa/users.py`)

`UsersCollection` loads a JSON file (array of email strings) with a configurable TTL cache. If `[users] file` is not set, all authenticated users are allowed.

### Templates

Jinja2 templates use `.j2` extension and live in `redovisa/templates/`. The `mail.j2` template is also used for the email body. Template directory can be overridden in `[paths]`.
