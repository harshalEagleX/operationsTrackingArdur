# Concurrent-user load test

Simulates a floor of up to 500 employees continuously logged in and working —
starting/pausing/ending work sessions, taking breaks, picking up, progressing
and completing allocated batches — spread across 50 projects and 15 client
codes, plus a roster of supervisors who keep the pipeline fed with new
allocations ("orders"), reassign and occasionally cancel them, and set
targets. Order throughput is tunable up to a literal ~3000/day.

It runs against the real HTTP API (session cookie + CSRF, exactly like a
browser), not in-process service calls, because the thing worth measuring is
whether the deployed stack holds up — DB connections, row locks, WSGI worker
capacity — not whether the Python is fast.

## Why a separate conda env

`locust` is not in `requirements-dev.txt` — it pulls in Flask, gevent and a
handful of other packages this application has no other use for, and the
project's pinned dependency list is a deliberate, reviewed surface (see
`requirements.txt`'s header comment). Keep it out of `.venv`:

```bash
conda create -n ops-loadtest python=3.12
conda activate ops-loadtest
pip install locust requests
```

## 1. Provision accounts (in the project's own venv)

```bash
source .venv/bin/activate
export DJANGO_SETTINGS_MODULE=opstracking.settings.dev
python manage.py seed_load_test --employees 520 --supervisors 15
```

Idempotent, and namespaced under the `LOADT_` emp_id prefix so it never
collides with `seed_dev`'s demo accounts. Tear it down any time with:

```bash
python manage.py cleanup_load_test
```

## 2. Size Postgres and run the app the way it's actually deployed

**Do not point this at `manage.py runserver`.** The dev server spawns one
thread per connection with no cap and no connection pooling — at ~140
concurrent users it already exhausts Postgres's default `max_connections=100`
and every request starts failing with `OperationalError`. That is a
dev-server artifact, not a finding about the application; measure against the
documented process split instead, sized for the concurrency you intend to run:

```bash
# Postgres: give real headroom over max(workers × threads) across every
# process that touches the DB (web, worker, beat, admin connections). For a
# 500-user run with the gunicorn sizing below, 400+ is comfortable.
#   max_connections = 400   # postgresql.conf, then restart

# WSGI — DRF + pages. 8 workers × 16 threads = 128 concurrent request slots;
# comfortably bounded under Postgres's ceiling. Extra concurrent users queue
# at the socket backlog rather than opening unbounded DB connections — that
# queuing is the correct, intended backpressure behaviour of a real deploy.
.venv/bin/gunicorn opstracking.wsgi:application --bind 127.0.0.1:8001 \
    -w 8 --worker-class gthread --threads 16 --timeout 30

# ASGI — only needed if you also want to exercise the websocket gateway
.venv/bin/daphne -b 127.0.0.1 -p 8002 opstracking.asgi:application
```

## 3. Run the load test

```bash
conda activate ops-loadtest
locust -f scripts/load_test/locustfile.py --host http://127.0.0.1:8001 \
    --headless -u 500 -r 25 -t 5m \
    --csv scripts/load_test/results/run --html scripts/load_test/results/run.html
```

- `-u 500` concurrent users (≈486 employees + ≈14 supervisors at the default
  35:1 weighting — close to the provisioned 520/15 split).
- `-r 25` ramp-up rate (20s to full concurrency — real shifts don't start in
  the same second either, but this stays inside a short test run).
- `-t 5m` run length. Locust prints a live table and writes CSV + an HTML
  report with latency percentiles per endpoint on exit.

Env vars the scenario reads:

| Variable | Default | Meaning |
|---|---|---|
| `LOCUST_N_EMPLOYEES` | 520 | Must match `--employees` passed to `seed_load_test` |
| `LOCUST_N_SUPERVISORS` | 15 | Must match `--supervisors` |
| `LOCUST_ORDER_WAIT_SECONDS` | 8 | See scaling note below |

## Scaling to a literal "3000 orders/day"

`SupervisorUser.create_order` fires roughly once every `order_wait` seconds
per active supervisor. With `S` supervisors, to average `R` orders/day:

```
order_wait ≈ S * 86400 / R
```

For S=15, R=3000 → `order_wait ≈ 432s`. The 8s default is deliberately much
faster, so a multi-minute smoke run produces observable throughput instead of
a handful of orders total. For a true 24h-equivalent soak run at the real
rate:

```bash
LOCUST_ORDER_WAIT_SECONDS=432 locust -f scripts/load_test/locustfile.py \
    --host http://127.0.0.1:8001 --headless -u 500 -r 25 -t 24h \
    --csv scripts/load_test/results/soak
```

## What "success" means here

Business-rule conflicts (409, and 404 on a session/break/order another
concurrent request already closed or reassigned) are counted as successes in
the Locust stats — under real concurrency those are the system behaving
correctly, not a defect. Only 5xx and unexpected 4xx count as failures. After
a run, also check invariants directly against the database — a request can
return 200 on both sides of a race and still leave bad data behind, which
HTTP status codes alone won't show:

```bash
source .venv/bin/activate
export DJANGO_SETTINGS_MODULE=opstracking.settings.dev
python manage.py shell -c "
from django.db.models import Count
from apps.tracking.models import WorkSession, SessionState
dupes = (WorkSession.objects.filter(end_time__isnull=True, is_started=SessionState.RUNNING)
         .values('emp_id').annotate(n=Count('id')).filter(n__gt=1))
print('employees with >1 open session:', list(dupes))
"
```

That query should always return `[]`. If it doesn't, the one-open-session
guarantee has regressed — see `tests/test_concurrency.py`.
