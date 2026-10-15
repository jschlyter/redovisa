# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Redovisa** is a FastAPI web application for expense reporting. Users authenticate via OIDC, fill in an expense form, and submit receipts. The app exports reports via SMTP email (with a merged PDF attachment) and optionally to a Google Sheet. When a report has a negative total (the user owes money), the confirmation page can show a Swish payment link and QR code.

## Commands

```bash
# Run tests (tests/ covers models, OIDC middleware, session, state, PDF, Swish)
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

Configuration is loaded **exclusively from `redovisa.toml`** — there is no env-var fallback (see `settings_customise_sources` in `redovisa/settings.py`). The example config is `redovisa.exempel.toml`. Key sections: `[oidc]`, `[smtp]`, `[google]`, `[swish]`, `[redis]`, `[users]`, `[csrf]`, `[cookies]`, `[http]`, `[context]`. `smtp`, `google`, `swish` and `redis` are optional; each feature is disabled when its section is absent.

`[context]` is a free-form dict injected into every Jinja2 template render. `[context.accounts]` maps account numbers to display names for the expense form.

### OIDC middleware (`redovisa/oidc/`)

`OidcMiddleware` is an ASGI middleware that intercepts every request before it reaches the router:

- **`/login`** → redirects to the OIDC provider's authorization endpoint
- **`/callback`** → exchanges the auth code for an ID token, validates it, creates a session, and redirects
- **`/logout`** → deletes the session cookie and Redis entry
- All other paths → checks for a valid session cookie; redirects to login if absent

The session is stored in Redis using `SessionHandler` (`oidc/session.py`). When Redis is not configured, `fakeredis.FakeRedis()` is used for in-memory storage (sessions lost on restart).

The OIDC `state` parameter is a compact **JWE token** (not a plain nonce), encoded by `StateHandler` (`oidc/state.py`) using `jwcrypto`. It carries `session_id`, the `next` redirect path (validated by `verify_next` to be a same-origin relative path), and the PKCE `code_verifier` when PKCE is used. `StateHandler.decode` raises on invalid input; the middleware's `callback` turns that into a 400. If `state_secret` is not set in config, a random key is generated each run (state won't survive restarts).

PKCE (S256) is controlled by `oidc.pkce`: `true`/`false` forces it, unset auto-detects from the OP's `code_challenge_methods_supported`.

The users allowlist is enforced in `callback`: a non-allowed user is redirected to the forbidden page without a session being created.

HTTP calls to the OP use `httpx2` (sync client at startup, async client at runtime, HTTP/2 enabled).

JWK sets from the OIDC issuer are fetched at startup and refreshed lazily based on the HTTP `Expires` header, clamped to `[60s, 24h]`.

### Request flow after authentication

The middleware sets `scope["state"]["session"]` to a `Session` object. Views access it via `request.state.session`. The logger bound to the request is at `request.state.logger`.

The expense form (`views.py`) is protected with `fastapi-csrf-protect`: the GET view issues a token and cookie, `submit_expense` validates it. `ExpenseReport.from_form` (`models.py`) parses the form; a recipient bank account is required unless the total is negative. The recipient account is remembered in a cookie (`cookies.recipient_account`).

### Exporters (`redovisa/export.py`)

Two exporters implement `ExpenseExporter.export()`:

- **`SmtpExpenseExporter`**: renders the Jinja2 `mail.j2` template as HTML, builds a `PdfRenderer` (report HTML + receipt images/PDFs merged), and sends via SMTP. Set `smtp.test = true` to print to stdout instead of sending.
- **`GoogleSheetExpenseExporter`**: appends rows to two worksheets (reports summary + line items) using a Google service account.

Multiple exporters can be active simultaneously. They are called sequentially in `views.py:submit_expense`.

### Swish (`redovisa/swish.py`)

When `[swish]` is configured and the report total is negative, `submit_expense` renders `submitted.j2` with a Swish app deep link and a QR code. The payment message is `swish.message` followed by `ExpenseReport.get_short_id()` (last 12 chars of the report id). The QR code is served by `/swish/qrcode.png`, which proxies Swish's prefilled-QR API.

### PDF generation (`redovisa/pdf.py`)

`PdfRenderer` accumulates pages from HTML (via `xhtml2pdf`/`pisa`), images (via `reportlab`+`PIL`, respecting EXIF orientation), and raw PDFs, then merges them into a single PDF using `pypdf.PdfWriter`.

### Users allowlist (`redovisa/users.py`)

`UsersCollection` loads a JSON file (array of email strings) with a configurable TTL cache. If `[users] file` is not set, all authenticated users are allowed.

### Templates

Jinja2 templates use `.j2` extension and live in `redovisa/templates/`. The `mail.j2` template is also used for the email body. Template directory can be overridden in `[paths]`.
