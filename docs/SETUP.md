# Setup

## Requirements

| Thing | Version | Notes |
|---|---|---|
| Python | 3.12 or newer | Django 5.2 dropped 3.9. `python3 --version` |
| PostgreSQL | 14+ | Or MySQL 8 — `DATABASE_URL` picks the backend |
| Redis | 6+ | Channel layer, Celery broker, cache |
| libmagic | any | Upload validation. `brew install libmagic` / `dnf install file-devel` |

Docker is optional; it is only used to run Postgres and Redis locally.

---

## First run

```bash
make setup      # .venv, dependencies, .env from the template
make infra      # Postgres + Redis containers
make migrate
make seed       # demo master data and four accounts
make run
```

Open http://localhost:8000 and sign in as `ADMIN01` / `opstracking123`.

### Without Docker

If you already run Postgres and Redis locally, skip `make infra` and create the
database by hand:

```bash
psql -d postgres -c "CREATE ROLE opstracking LOGIN PASSWORD 'opstracking' CREATEDB;"
psql -d postgres -c "CREATE DATABASE opstracking OWNER opstracking;"
```

`CREATEDB` on the role matters — pytest creates and drops `test_opstracking`
on every run, and without it the whole suite errors at setup.

Then point `.env` at them:

```ini
DATABASE_URL=postgres://opstracking:opstracking@127.0.0.1:5432/opstracking
REDIS_URL=redis://127.0.0.1:6379
```

### Using MySQL instead

Uncomment `mysqlclient` in `requirements.txt`, reinstall, and set:

```ini
DATABASE_URL=mysql://user:password@127.0.0.1:3306/opstracking
```

`STRICT_TRANS_TABLES` is applied automatically. It is what turns a silent
truncation into a loud error, so do not remove it.

---

## Environment

`.env` is created from `.env.example` by `make setup`. It is `chmod 600` and
git-ignored. The settings that matter:

| Variable | Purpose |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `opstracking.settings.dev` / `.prod` |
| `SECRET_KEY` | 50+ random characters. `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DATABASE_URL` | Selects the backend as well as the connection |
| `REDIS_URL` | db0 channels · db1 broker · db2 results · db3 cache |
| `LEGACY_TABLES_MANAGED` | `True` locally, `False` against a live legacy schema |
| `PRIVATE_STORAGE_ROOT` | Uploads. **Must be outside the web root.** |
| `FEATURE_CHAT` | Leave `False` — chat is not implemented |

`prod.py` reads `SECRET_KEY` and `ALLOWED_HOSTS` with no defaults, so a
misconfigured deployment fails loudly instead of running insecurely. `DEBUG` is
assigned `False` literally there — a stray `DEBUG=True` in a deployed `.env`
cannot switch it back on.

---

## Running the pieces

```bash
make run             # HTTP: DRF + pages on :8000
make run-ws          # Daphne: websockets on :8002
make worker          # Celery, default queue
make worker-reports  # Celery, reports queue
make beat            # Celery scheduler
```

In development you normally only need `make run` — the dev server speaks ASGI,
and Celery runs eagerly so tasks execute inline. Start the others when you are
working on consumers or want to watch the queue.

---

## Tests

```bash
make test    # pytest
make cov     # with coverage
make lint    # ruff
```

The suite needs no infrastructure: locmem cache, in-memory channel layer, eager
tasks, MD5 password hashing. It does need permission to create a test database
(see `CREATEDB` above).

The suite covers the boundaries that matter — authentication and session
invalidation, role permissions, cross-employee data access, server-side timing,
break allowances and races, the error envelope, and an audit that walks the
URLConf asserting every route requires auth.

---

## Database notes

### Legacy tables

Models keep the original table names so both applications can run side by side
during a cutover. `LEGACY_TABLES_MANAGED` decides whether Django owns their
schema.

Adopting existing production tables:

```bash
python manage.py migrate --fake-initial
```

That records the migrations as applied without running the DDL. **Never run
`makemigrations` in production** — with `LEGACY_TABLES_MANAGED=False` it will
try to generate an `AlterModelOptions` migration for tables Django does not own.

`AbstractBaseUser` needs a `last_login` column that `ot_users` does not have.
Add it once, by hand — additive, nullable, no impact on the Flask app:

```sql
ALTER TABLE ot_users ADD COLUMN last_login DATETIME NULL DEFAULT NULL AFTER password;
```

### Indexes

The migrations declare the indexes the reports depend on. If you are pointing
at an existing database, confirm these exist — they are the difference between
a 40 ms and a 4 second report:

```sql
CREATE INDEX ix_work_emp_start   ON ot_user_work_data (emp_id, start_time);
CREATE INDEX ix_work_started     ON ot_user_work_data (is_started, start_time);
CREATE INDEX ix_work_project     ON ot_user_work_data (project, start_time);
CREATE INDEX ix_break_user_open  ON aps_Break_Times (user_id, end_time);
CREATE INDEX ix_login_emp_date   ON ot_user_login_history (emp_id, date);
CREATE INDEX ix_fb_emp_created   ON ot_feedbacks (emp_id, created_at);
CREATE INDEX ix_alloc_emp_status ON ot_batch_allocations (employee_id, status);
```

Take a dump first. On tables over about a million rows, MySQL wants
`ALTER TABLE ... ALGORITHM=INPLACE, LOCK=NONE`.

### Password hashes

The Flask app stored bare bcrypt (`$2b$...`); Django expects an algorithm
prefix. Run once:

```bash
python scripts/migrate_password_hashes.py          # dry run — reports only
python scripts/migrate_password_hashes.py --apply  # writes
```

It is idempotent. Everyone keeps their existing password, and Django
transparently upgrades each hash to BCryptSHA256 on their next successful
login — so within a few weeks the table is on the stronger scheme with zero
password resets.

---

## Deployment

Any host that gives you long-running processes will do. You need:

- a process supervisor for the four services (HTTP, WebSocket, two Celery
  workers, plus beat)
- Redis reachable on loopback, with a password
- a reverse proxy that terminates TLS, serves `/static/` from disk, and
  forwards `/ws/` with the WebSocket upgrade preserved
- `PRIVATE_STORAGE_ROOT` outside the document root

`scripts/deploy.sh` runs the sequence — pull, install, migrate, collectstatic,
deploy checks, reload, verify — and takes the restart commands from
`RELOAD_API_CMD`, `RESTART_WORKER_CMD` and `RESTART_WS_CMD` so it adapts to
whatever supervises the processes.

Restart the WebSocket process only when consumer code changed. Every restart
disconnects every user at once; the client backs off with jitter so they do not
all return in the same instant, but it is still churn worth avoiding.

### Verifying the WebSocket path

The reverse proxy has to pass the upgrade through:

```bash
curl -i -N \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  https://your-host/ws/gateway/
```

`101 Switching Protocols` is correct. A `200`, `400` or `502` means the proxy
is not upgrading — check the module is loaded and that the `/ws/` rule is
matched before the catch-all.

### Health and backups

```bash
./scripts/healthcheck.sh          # exits non-zero if anything is down
./scripts/backup_db.sh            # nightly via cron
```

A host snapshot protects the machine. It does not give you a point-in-time
table restore when someone truncates the wrong thing at 4pm. Keep both, and
restore a backup into a scratch database on a schedule — a backup you have
never restored is a hypothesis.

---

## Troubleshooting

**`permission denied to create database` when running tests**
The database role needs `CREATEDB`:
`psql -d postgres -c "ALTER ROLE opstracking CREATEDB;"`

**`'__proxy__' object is not callable` in a template**
Django's Jinja2 backend injects `csrf_input` and `csrf_token` as lazy *values*.
Write `{{ csrf_input }}`, not `{{ csrf_input(request) }}`.

**Every POST returns 403**
DRF's `SessionAuthentication` enforces CSRF. The fetch wrapper in
`static/js/core/api.js` sends `X-CSRFToken` automatically — if you are calling
with `curl`, send the header and a `Referer`.

**Uploads fail with "File uploads are unavailable"**
`libmagic` is missing. `brew install libmagic` or `dnf install file-devel`.
The upload path refuses to fall back to trusting `content_type`, because that
value comes from the browser, which comes from the attacker.

**WebSocket connects then immediately closes with 4401**
The session is gone or the handshake ticket expired. Tickets are single-use and
live 60 seconds. The client treats 4401 as "go to /login" rather than
"reconnect", which is deliberate — otherwise a signed-out tab loops forever.

**Presence stays green after someone closes their laptop**
That is what `reap_stale_presence` is for — it runs every 30 seconds on Celery
beat. If beat is not running, presence will not self-correct.

**Reports are slow**
Check the indexes above exist, and prefer exporting over rendering: the inline
run caps at 5,000 rows precisely so a large query cannot hold a web worker.
