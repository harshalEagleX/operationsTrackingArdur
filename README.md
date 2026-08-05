# OpsTracking

Operations tracking for a data-processing floor: work sessions, breaks, batch
allocations, quality feedback and reporting — with live presence and in-app
notifications over WebSockets.

**Stack:** Python 3.12+ · Django 5.2 LTS · Django REST Framework · Django
Channels (ASGI) · Celery · Redis · PostgreSQL (MySQL supported) · Jinja2 ·
vanilla JS

---

## Quick start

```bash
git clone git@github.com:harshalEagleX/operationsTrackingArdur.git
cd operationsTrackingArdur

make setup      # virtualenv + dependencies + .env
make infra      # PostgreSQL + Redis via docker compose
make migrate
make seed
make run        # http://localhost:8000
```

Sign in with any of the seeded accounts (password `opstracking123`):

| Account   | Role       | What it shows |
|-----------|------------|---------------|
| `ADMIN01` | Admin      | Everything, including master data and settings |
| `SUP01`   | Supervisor | Floor view, allocations, reports, feedback |
| `EMP01`   | Employee   | Own work timer, breaks, tasks and feedback |

If Docker is not available, point `DATABASE_URL` and `REDIS_URL` at local
installs instead — see [docs/SETUP.md](docs/SETUP.md).

---

## What runs where

Three processes, because they have genuinely different needs:

```
                    ┌──────────────────────────┐
   HTTP / JSON ────▶│ Gunicorn (WSGI) :8001    │  DRF + Jinja2 pages
                    │ opstracking.wsgi         │  recycled to bound memory
                    └──────────────────────────┘
                    ┌──────────────────────────┐
   WebSocket ──────▶│ Daphne (ASGI) :8002      │  Channels consumers
                    │ opstracking.asgi         │  long uptime, no recycling
                    └──────────────────────────┘
                    ┌──────────────────────────┐
   Background ─────▶│ Celery: default, reports │  exports, fan-out, beat
                    └──────────────────────────┘
                              │
                    Redis (channels · broker · cache)
                    PostgreSQL / MySQL
```

DRF is synchronous. Running it under ASGI puts every view through a thread
pool for no gain, so HTTP stays on WSGI. Keeping the socket in its own process
also means a deploy that restarts the API drops zero WebSocket connections.

In development `make run` serves everything on `:8000`; you only need
`make run-ws` when you are working on consumers.

---

## Layout

```
opstracking/          project package — settings/, urls, wsgi, asgi, celery
core/                 cross-cutting: BaseService, permissions, events,
                      exceptions, IST clock, middleware. Owns no models.
apps/
  accounts/           users, employees, auth, login history
  masters/            work types, projects, client codes, shifts
  tracking/           work sessions and daily targets
  breaks/             break records, server-owned allowances
  allocations/        batch allocations and order history
  feedback/           quality and audit feedback
  reports/            selectors, exporters, async export jobs
  settings_app/       runtime-editable application settings
  files/              one upload/download pipeline for every app
  realtime/           WebSocket gateway, tickets, durable outbox
  presence/           who is online / working / on break
  notifications/      the in-app inbox
  chat/               scaffolded only — see apps/chat/README.md
pages/                Jinja2 page views
templates/  static/   the frontend shell
scripts/              deploy, backup, health check, hash migration
tests/                pytest suite
```

### The layering rule

```
ViewSet      transport — parse, call one service, render
Serializer   validation and shape
Service      business rules and transactions
Manager      reusable queries
Model        persistence
```

**Nothing outside a service writes to the database.** A view that calls
`Model.objects.create()` is a bug, because the next caller — a Celery task, a
management command, an import script — will not get the same rules applied.

Services take the acting user in their constructor rather than reaching for a
thread-local request, which is what lets the same code run in a worker.

---

## Design decisions worth knowing

**Deny by default.** `DEFAULT_PERMISSION_CLASSES` is
`IsAuthenticatedEmployee`, so a view that forgets its `permission_classes` is
closed, not open. `tests/test_url_auth_audit.py` walks the URLConf and fails
the build if any route becomes public without being added to an explicit
allowlist.

**List endpoints scope their querysets.** An object-level permission only runs
on `get_object()`. Protecting per-employee data needs both — see
`ScopedQuerysetMixin` and `OwnedQuerySet.visible_to()`.

**Time comes from the server.** `core.timezone.now_ist()` is the only
sanctioned clock; a ruff rule bans bare `datetime.now()`. The client may send
`end_time`; the serializer has no such field and it is discarded. Anything
derived from a browser clock ends up in a report someone is paid against.

**Break allowances are server constants.** They live in
`apps/breaks/constants.py` and are never accepted from a request. One open
break per employee is guaranteed by a `select_for_update()` check *and* a
partial unique index, because that is a race and only the database can settle
it.

**Writes go over HTTP; pushes come over the WebSocket.** One validation path,
one permission path, one throttle, one audit trail — and a status code instead
of silence. The exceptions are `ping` and `typing`, which are ephemeral.

**One socket per tab.** A single `GatewayConsumer` multiplexes presence,
notifications and work events over topic-tagged frames. Three sockets per user
across 150 users is 450 connections and three reconnect storms every time the
wifi blips.

**Redis pub/sub is fire-and-forget, so there is a durable outbox.** Every
`publish()` writes `ot_realtime_outbox` first. On reconnect the client sends
its last-seen sequence per topic and the server replays the gap, which is what
makes a 30-second tunnel invisible rather than lossy.

**Presence broadcasts only on change.** Without that guard, 150 users
heartbeating every 20 seconds would produce over a thousand messages a second
of pure noise.

**Exports are asynchronous.** A 50,000-row Excel build holds a web worker for
a minute or more. `POST /api/v1/reports/export/` returns `202` immediately and
the finished file arrives as a notification with a download link.

**Uploads are validated by content, not by filename.** Magic-byte sniffing,
extension-must-match, UUID storage names, files kept outside the web root at
mode `0640`, and every download permission-checked.

---

## API

Everything lives under `/api/v1/`. One success shape, one error shape:

```jsonc
{"ok": true,  "data": {...}, "meta": {...}}
{"ok": false, "error": {"code": "validation_error", "message": "...", "details": {}}}
```

An error is never returned with HTTP 200, and a stack trace never reaches a
browser — the user gets a request id that matches a log line.

| Area | Base path |
|---|---|
| Auth, employees, login history | `/api/v1/auth/` |
| Master data (+ `bundle/`) | `/api/v1/masters/` |
| Work sessions, targets, summary | `/api/v1/tracking/` |
| Breaks (+ `types/`) | `/api/v1/breaks/` |
| Allocations and history | `/api/v1/allocations/` |
| Feedback | `/api/v1/feedback/` |
| Reports, exports, metrics | `/api/v1/reports/` |
| Application settings | `/api/v1/settings/` |
| Upload and download | `/api/v1/files/` |
| WebSocket ticket and catch-up | `/api/v1/realtime/` |
| Presence roster | `/api/v1/presence/` |
| Notification inbox | `/api/v1/notifications/` |

Health probes are `/health/` (liveness — touches nothing) and `/ready/`
(readiness — checks the database and cache, returns 503 if either is down).

---

## Chat

Not implemented, deliberately. `apps/chat/` holds the shape of the feature and
the decisions already made, so building it later is filling in files rather
than re-deciding the architecture.

It is inert: not in `INSTALLED_APPS`, not routed, `FEATURE_CHAT=False`,
`can_subscribe()` refuses every `chat.*` topic, and chat attachments are
unreadable. Each of those is a one-line change, and all five carry a comment
pointing at [apps/chat/README.md](apps/chat/README.md).

The infrastructure chat needs — socket transport, event fan-out, replay on
reconnect, handshake auth, the file pipeline, notifications, throttling — is
already built and in use by presence and notifications.

---

## Development

```bash
make test         # pytest
make cov          # with a coverage report
make lint         # ruff
make fmt          # ruff format + autofix
make check        # Django deploy checks
make worker       # Celery default queue
make beat         # Celery scheduler
make shell        # Django shell
```

Celery runs eagerly in development (`CELERY_TASK_ALWAYS_EAGER`), so you can
click through the whole app without a worker. Start one when you want to
exercise the queue itself.

The test suite needs no infrastructure — it uses locmem caching, an in-memory
channel layer and eager tasks.

---

## Database

Local development is PostgreSQL. Production may run against the legacy MySQL
schema; `DATABASE_URL` selects the backend and the models carry the original
table names (`ot_users`, `ot_user_work_data`, `aps_Break_Times`, …) either way.

`LEGACY_TABLES_MANAGED` controls whether Django owns the schema of the
inherited tables:

- `True` (local) — migrations create them, so a fresh clone has a working database.
- `False` (production) — Django reads and writes but never issues DDL against
  tables that hold live data. Adopt them once with `migrate --fake-initial`.

New tables (files, presence, notifications, outbox, report jobs) are always
Django-managed and keep the `ot_` prefix so the schema reads as one
application.

Migrating from the Flask app: `scripts/migrate_password_hashes.py` prefixes the
stored bcrypt hashes so Django can read them. Everyone keeps their password,
and Django upgrades each hash to BCryptSHA256 on their next login.

---

## Further reading

- [docs/SETUP.md](docs/SETUP.md) — detailed setup, troubleshooting, deployment
- [OpsTracking_DRF_Realtime_Architecture.md](OpsTracking_DRF_Realtime_Architecture.md) — full architecture reference
- [apps/chat/README.md](apps/chat/README.md) — the deferred chat feature
