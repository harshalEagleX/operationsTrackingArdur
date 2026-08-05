# OpsTracking — Django + DRF + Channels + Celery
## Architecture & Real-Time Design

**Version:** 3.0
**Stack:** Python 3.12+ · Django 5.2 LTS · Django REST Framework · Django Channels (ASGI) · Celery · Redis · PostgreSQL (MySQL supported) · Jinja2 templates · vanilla JS/CSS

> **Scope of this document.** This is the architecture and design reference:
> what the pieces are, how they fit together, and why each decision was made
> the way it was. It is deliberately **hosting-agnostic** — it states what the
> runtime must provide, not which vendor provides it or what that costs. Choose
> the host separately; Part 14 lists the requirements any candidate has to meet.
>
> For getting the application running, see `README.md` and `docs/SETUP.md`.

---

# PART 0 — RUNTIME REQUIREMENTS (read this first)

Everything downstream assumes the runtime below. If a host cannot provide it,
the real-time half of this application does not work there — and that is a
property of the technology, not of any particular vendor.

## 0.1 What the application needs

| Requirement | Why | Non-negotiable? |
|---|---|---|
| **Long-running processes** | Daphne holds WebSocket connections open; Celery workers must stay alive indefinitely | Yes, for real-time and background work |
| **ASGI server** (Daphne or Uvicorn) | WSGI has no protocol slot for an HTTP `Upgrade: websocket` handshake | Yes, for WebSockets |
| **Redis** | Channels layer, Celery broker, cache | Yes |
| **PostgreSQL or MySQL** | Application data | Yes |
| **Loopback ports** | The web process, the socket process and Redis bind to `127.0.0.1` | Yes |
| **Reverse proxy that forwards the upgrade** | The `/ws/` path must reach the ASGI process with `Connection: Upgrade` intact | Yes, for WebSockets |
| **Writable storage outside the web root** | Uploads must not be reachable by URL | Yes |
| **TLS** | `wss://` requires a valid certificate | Yes in production |

Python 3.12 or newer, because Django 5.2 dropped 3.9.

## 0.2 The constraint that decides your host

**WSGI cannot carry WebSockets.** It is a request-in / response-out contract
with no concept of a persistent connection. Django has no native WebSocket
support either — it needs Django Channels, an ASGI server, and Redis as the
channel layer for anything running more than one process.

This is true of Django and equally true of FastAPI or anything else: the
runtime requirement is the framework's, not the framework's fault. Swapping web
frameworks does not remove it.

The practical consequence: **a host that only offers WSGI through a managed
Python-app panel cannot run the real-time features**, no matter how the
application is written.

Likewise, Celery needs a broker daemon and a worker process that stays alive.
The commonly suggested substitute — a cron job every minute running a
management command — is a batch runner, not Celery. It cannot do sub-second
notification fan-out and it cannot retry with backoff.

## 0.3 What still works without long-running processes

Should the real-time runtime be unavailable, roughly the following still runs
under plain WSGI:

- Django + DRF (all HTTP/JSON endpoints)
- Jinja2 pages
- The database and every business rule in the service layer
- Reports, though export generation would move back into the request

What does not: WebSockets, Redis, Celery, live presence, push notifications.
The application is built so this degrades rather than breaks — `publish()` is
the single realtime entry point and the durable outbox means events are still
recorded — but the user experience is materially worse, and any polling
fallback puts sustained request load on the web tier.

**Recommendation: run on something that gives you persistent processes.** The
feature set assumes it.

---

# PART 1 — RUNTIME TOPOLOGY

One public-facing reverse proxy terminates TLS and forwards to the local Python processes. Nothing else is reachable from the internet.

```
                         Internet  (HTTPS / WSS :443)
                                │
                    ┌───────────┴───────────┐
                    │    Reverse proxy      │
                    │    TLS termination    │
                    │    HTTP forwarding    │
                    │    WebSocket upgrade  │
                    │    static from disk   │
                    └───────────┬───────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │ /static/ /media-thumb/│                       │
        │  (served from disk)   │                       │
        │                       │                       │
   [ files ]        127.0.0.1:8001                 127.0.0.1:8002
                  ┌──────────────────┐          ┌──────────────────┐
                  │ Gunicorn (WSGI)  │          │  Daphne (ASGI)   │
                  │ Django + DRF     │          │ Django Channels  │
                  │ HTTP / JSON /    │          │ WebSocket only   │
                  │ Jinja2 pages     │          │ chat / presence  │
                  │ 3–5 gthread wkrs │          │ notify / typing  │
                  └────────┬─────────┘          └────────┬─────────┘
                           │                             │
                           └──────────┬──────────────────┘
                                      │
                             ┌────────┴────────┐
                             │   Redis :6379   │
                             │  db0 channels   │
                             │  db1 celery brk │
                             │  db2 celery res │
                             │  db3 cache/pres │
                             └────────┬────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
            ┌───────┴──────┐  ┌───────┴──────┐  ┌───────┴──────┐
            │ Celery worker│  │ Celery worker│  │ Celery beat  │
            │ queue:default│  │ queue:reports│  │  scheduler   │
            └───────┬──────┘  └───────┬──────┘  └───────┬──────┘
                    └─────────────────┼─────────────────┘
                                      │
                             ┌────────┴────────┐
                             │  MySQL :3306    │
                             └─────────────────┘

            <app-user-home>/storage/   ← uploads, OUTSIDE public_html
```

## 1.1 Why two Python processes instead of one

Django 5.2 can serve HTTP under ASGI, so a single Daphne could technically do everything. Do not do that.

- **DRF is synchronous.** Under ASGI every DRF view runs in a thread-pool via `sync_to_async`. You pay the overhead and gain nothing.
- **Deployment safety.** Restarting the API process during a deploy drops zero WebSocket connections, because the sockets live in a different process. If you merge them, every deploy disconnects every chat user.
- **Independent tuning.** Gunicorn wants worker recycling (`--max-requests`) to bound memory on report generation. Daphne wants long uptime and zero recycling.

Same codebase, same settings, two entry points — `opstracking/wsgi.py` and `opstracking/asgi.py`.

## 1.2 Port and process map

| Process | Binds | Managed by | Restart policy |
|---|---|---|---|
| Reverse proxy | `:80`, `:443` | host | always |
| Gunicorn (DRF + pages) | `127.0.0.1:8001` | supervisor | always |
| Daphne (Channels/WS) | `127.0.0.1:8002` | supervisor | always |
| Celery worker `default` | — | supervisor | always |
| Celery worker `reports` | — | supervisor | always |
| Celery beat | — | supervisor | always |
| Redis | `127.0.0.1:6379` | supervisor | always |
| Database | `127.0.0.1:5432` / `:3306` | host | always |

Nothing except the reverse proxy is reachable from the internet.

---

# PART 2 — TECH STACK & PINNED VERSIONS

Django 5.2 is the current **LTS**, security-supported to **April 2028**. Django 6.0 is the short-term release (support ends April 2027) and DRF added official 6.0 support in 3.17.0. **Use 5.2 LTS** — you want three years of quiet, not the newest features.

Django 4.2 LTS reached end of life in **April 2026**. Do not start there.

```txt
# requirements.txt

# --- core ---
Django==5.2.*
djangorestframework==3.16.*
django-environ==0.12.*
mysqlclient==2.2.*                 # C driver; faster than PyMySQL

# --- realtime ---
channels[daphne]==4.2.*
channels-redis==4.2.*

# --- background ---
celery==5.5.*
redis==5.2.*
django-celery-beat==2.7.*          # DB-backed schedule, editable at runtime
django-celery-results==2.5.*

# --- auth / security ---
bcrypt==4.2.*
django-cors-headers==4.6.*         # only if you ever split domains
django-ratelimit==4.1.*

# --- files / media ---
Pillow==11.*                       # thumbnails, EXIF strip
python-magic==0.4.*                # real MIME sniffing (libmagic)

# --- reports ---
openpyxl==3.1.*

# --- serving ---
gunicorn==23.*
whitenoise==6.8.*                  # optional; Apache can serve static directly

# --- ops ---
sentry-sdk==2.*                    # optional but recommended
```

System packages required on the host: `redis`, `libmagic`, `mysql-devel` (for `mysqlclient`), `gcc`, `python3.12-devel`.

---

# PART 3 — PROJECT STRUCTURE

Vertical slices. Each Django app owns its models, serializers, services, views, consumers and tasks. Cross-cutting code lives in `core/`. This is the OOP layering you had in the FastAPI plan (Router → Service → Repository → DB), mapped to Django idiom (ViewSet → Service → Manager/QuerySet → ORM).

```
<app-user-home>/
├── app/                                  # ← git repo root (NOT in public_html)
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env                              # chmod 600, never committed
│   │
│   ├── opstracking/                      # project package
│   │   ├── __init__.py                   # loads celery_app
│   │   ├── settings/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                   # everything shared
│   │   │   ├── dev.py
│   │   │   └── prod.py                   # DEBUG=False, secure cookies  ← FIXES C-6
│   │   ├── urls.py                       # root URLConf
│   │   ├── api_urls.py                   # /api/v1/ router registry
│   │   ├── wsgi.py                       # → Gunicorn  :8001
│   │   ├── asgi.py                       # → Daphne    :8002
│   │   ├── routing.py                    # Channels ProtocolTypeRouter
│   │   └── celery.py                     # Celery app + queue routing
│   │
│   ├── core/                             # cross-cutting, no models of its own
│   │   ├── __init__.py
│   │   ├── timezone.py                   # now_ist(), today_ist()  ← FIXES H-6
│   │   ├── exceptions.py                 # DomainError hierarchy
│   │   ├── exception_handler.py          # DRF handler → consistent envelope ← FIXES M-9, M-10
│   │   ├── permissions.py                # IsAdmin, IsAdminOrSupervisor, IsOwnerOrAdmin ← FIXES C-3, C-4
│   │   ├── authentication.py             # SessionAuth + WS ticket auth
│   │   ├── pagination.py                 # KeysetPagination, StandardPagination
│   │   ├── throttling.py                 # ChatBurst, UploadThrottle
│   │   ├── mixins.py                     # ServiceViewSetMixin, AuditMixin
│   │   ├── services.py                   # BaseService
│   │   ├── managers.py                   # SoftDeleteManager, ActiveManager
│   │   ├── validators.py                 # filename, mime, length
│   │   ├── middleware.py                 # RequestID, AccessLog, SecurityHeaders
│   │   ├── events.py                     # publish() — the ONLY realtime entry point
│   │   ├── cache.py                      # master-data cache helpers
│   │   └── hashers.py                    # LegacyBCryptHasher for existing passwords
│   │
│   ├── apps/
│   │   ├── accounts/                     # ot_users, ot_employees, login history
│   │   │   ├── models.py                 # User (AbstractBaseUser), Employee, LoginHistory
│   │   │   ├── managers.py               # UserManager
│   │   │   ├── serializers.py
│   │   │   ├── services.py               # AuthService, EmployeeService
│   │   │   ├── views.py                  # LoginView, LogoutView, EmployeeViewSet
│   │   │   ├── permissions.py
│   │   │   ├── urls.py
│   │   │   ├── tasks.py                  # welcome mail, password-reset mail
│   │   │   └── migrations/
│   │   │
│   │   ├── masters/                      # worktypes, projects, client codes, shifts
│   │   │   ├── models.py  serializers.py  services.py  views.py  urls.py
│   │   │   └── migrations/
│   │   │
│   │   ├── tracking/                     # work sessions + targets
│   │   │   ├── models.py                 # WorkSession, Target
│   │   │   ├── services.py               # WorkSessionService ← FIXES H-2
│   │   │   ├── serializers.py  views.py  urls.py
│   │   │   ├── signals.py                # session start/stop → presence + events
│   │   │   └── migrations/
│   │   │
│   │   ├── breaks/                       # aps_Break_Times
│   │   │   ├── models.py  serializers.py
│   │   │   ├── services.py               # BreakService ← FIXES H-3, H-4
│   │   │   ├── constants.py              # BREAK_ALLOWANCES (server-owned)
│   │   │   ├── views.py  urls.py  signals.py
│   │   │   └── migrations/
│   │   │
│   │   ├── allocations/                  # batch allocations + order history
│   │   │   ├── models.py  serializers.py  services.py  views.py  urls.py
│   │   │   ├── tasks.py                  # bulk import from uploaded sheet
│   │   │   └── migrations/
│   │   │
│   │   ├── feedback/                     # audit / quality feedback + images
│   │   │   ├── models.py  serializers.py
│   │   │   ├── services.py               # FeedbackService ← FIXES C-5
│   │   │   ├── views.py  urls.py
│   │   │   └── migrations/
│   │   │
│   │   ├── reports/                      # summary / productivity / break / audit
│   │   │   ├── selectors.py              # read-only query objects (no models)
│   │   │   ├── services.py               # ReportService
│   │   │   ├── exporters.py              # ExcelExporter, CsvExporter
│   │   │   ├── serializers.py  views.py  urls.py
│   │   │   ├── models.py                 # ReportJob (async export tracking)
│   │   │   ├── tasks.py                  # build_report_task  ← keeps web procs free
│   │   │   └── migrations/
│   │   │
│   │   ├── settings_app/                 # app settings, login history, shifts
│   │   │   └── models.py  serializers.py  services.py  views.py  urls.py
│   │   │
│   │   ├── chat/                         # ★ NEW
│   │   │   ├── models.py                 # Conversation, Participant, Message,
│   │   │   │                             #   Attachment, MessageReaction
│   │   │   ├── managers.py               # ConversationQuerySet.visible_to(user)
│   │   │   ├── serializers.py
│   │   │   ├── services.py               # ChatService (send/edit/delete/read)
│   │   │   ├── views.py                  # ConversationViewSet, MessageViewSet
│   │   │   ├── consumers.py              # ChatConsumer (read-side + typing)
│   │   │   ├── permissions.py            # IsConversationParticipant
│   │   │   ├── tasks.py                  # fan-out, unread recount, retention
│   │   │   ├── urls.py
│   │   │   └── migrations/
│   │   │
│   │   ├── presence/                     # ★ NEW — who is online / on break / working
│   │   │   ├── models.py                 # PresenceState (durable last-seen)
│   │   │   ├── services.py               # PresenceService (Redis + DB)
│   │   │   ├── serializers.py  views.py  urls.py
│   │   │   ├── consumers.py              # PresenceConsumer (heartbeat)
│   │   │   ├── tasks.py                  # reap_stale_presence (beat, every 30s)
│   │   │   └── migrations/
│   │   │
│   │   ├── notifications/                # ★ NEW
│   │   │   ├── models.py                 # Notification, NotificationPreference
│   │   │   ├── serializers.py
│   │   │   ├── services.py               # NotificationService.notify()
│   │   │   ├── views.py  urls.py
│   │   │   ├── consumers.py              # NotificationConsumer
│   │   │   ├── registry.py               # NotificationType catalogue
│   │   │   ├── tasks.py                  # deliver, digest, prune
│   │   │   └── migrations/
│   │   │
│   │   ├── files/                        # ★ NEW — one upload pipeline for everything
│   │   │   ├── models.py                 # StoredFile
│   │   │   ├── serializers.py
│   │   │   ├── services.py               # FileService (validate, store, thumb)
│   │   │   ├── storage.py                # PrivateStorage (outside webroot)
│   │   │   ├── views.py                  # upload + authenticated download
│   │   │   ├── scanners.py               # magic/extension/size gate
│   │   │   ├── tasks.py                  # make_thumbnail, virus scan hook
│   │   │   ├── urls.py
│   │   │   └── migrations/
│   │   │
│   │   └── realtime/                     # ★ NEW — transport plumbing only
│   │       ├── consumers.py              # BaseAuthedConsumer
│   │       ├── middleware.py             # TicketAuthMiddleware for ASGI
│   │       ├── groups.py                 # group-name constants + builders
│   │       ├── protocol.py               # envelope schema, opcodes
│   │       ├── tickets.py                # issue/redeem short-lived WS tickets
│   │       ├── views.py                  # POST /api/v1/realtime/ticket
│   │       │                             # GET  /api/v1/realtime/sync  (catch-up)
│   │       ├── models.py                 # OutboxEvent (replay / fallback)
│   │       └── urls.py
│   │
│   ├── pages/                            # server-rendered Jinja2 screens
│   │   ├── views.py                      # LoginPage, DashboardPage, UserDashboardPage…
│   │   ├── urls.py
│   │   └── context.py                    # inject current_user, feature flags, ws_url
│   │
│   ├── templates/                        # Jinja2 (NOT Django template language)
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── signup.html
│   │   ├── dashboard.html
│   │   ├── userdashboard.html
│   │   ├── settings.html
│   │   ├── chat.html                     # ★ NEW full-page chat
│   │   └── components/
│   │       ├── sidebar.html
│   │       ├── navbar.html               # + presence dot, bell, chat launcher
│   │       ├── modals.html
│   │       ├── tabs_employees.html
│   │       ├── tabs_masters.html
│   │       ├── tabs_reports.html
│   │       ├── tabs_allocations.html
│   │       ├── chat_panel.html           # ★ NEW dockable panel
│   │       ├── notification_center.html  # ★ NEW bell dropdown
│   │       ├── presence_list.html        # ★ NEW who's-online rail
│   │       └── toast_host.html           # ★ NEW  ← FIXES UI-1 (kills alert())
│   │
│   ├── static/
│   │   ├── css/
│   │   │   ├── app.css
│   │   │   ├── chat.css
│   │   │   └── toast.css
│   │   └── js/
│   │       ├── core/
│   │       │   ├── api.js                # fetch wrapper + CSRF + error envelope
│   │       │   ├── bus.js                # tiny pub/sub
│   │       │   ├── toast.js              # replaces alert()
│   │       │   └── store.js
│   │       ├── realtime/
│   │       │   ├── realtime-client.js    # ★ THE socket. one per tab.
│   │       │   ├── reconnect.js          # backoff + jitter
│   │       │   └── cursor.js             # per-topic last-seen ids
│   │       ├── features/
│   │       │   ├── chat.js
│   │       │   ├── chat-uploads.js
│   │       │   ├── notifications.js
│   │       │   ├── presence.js
│   │       │   ├── dashboard.js
│   │       │   ├── reports.js
│   │       │   ├── summary.js
│   │       │   ├── auditrep.js
│   │       │   ├── breakrep.js
│   │       │   ├── orderallocation.js
│   │       │   ├── projects.js
│   │       │   ├── clientcode.js
│   │       │   ├── worktypes.js
│   │       │   ├── feedback.js
│   │       │   └── settings.js
│   │       └── user/
│   │           ├── userdashboard.js
│   │           ├── userdashboard-work.js
│   │           ├── userdashboard-breaks.js
│   │           ├── userdashboard-feedback.js
│   │           ├── userdashboard-tasks.js
│   │           └── image-viewer.js
│   │
│   ├── scripts/
│   │   ├── deploy.sh
│   │   ├── migrate_password_hashes.py    # bcrypt → Django format (one-time)
│   │   ├── backup_db.sh
│   │   └── healthcheck.sh
│   └── tests/
│       ├── conftest.py
│       ├── test_auth.py                  # C-1, C-2
│       ├── test_permissions.py           # C-3, C-4, C-5
│       ├── test_timing.py                # H-2, H-6
│       ├── test_breaks.py                # H-3, H-4
│       ├── test_chat.py
│       └── test_realtime.py
│
├── storage/                              # ← NEVER inside public_html
│   ├── uploads/chat/YYYY/MM/
│   ├── uploads/feedback/YYYY/MM/
│   ├── uploads/allocations/
│   ├── thumbs/
│   └── exports/
├── logs/
│   ├── gunicorn.access.log  gunicorn.error.log
│   ├── daphne.log  celery.log  django.log
└── public_html/
    ├── static/                           # collectstatic target ONLY
    └── .htaccess                         # deny everything else
```

**Critical placement rule:** the only thing in the web root is `static/`. Application code, `.env`, and `storage/` live outside it, where the web server cannot reach them. If a misconfiguration ever exposes the document root, it exposes CSS — not your database credentials or your employees' uploaded files.

---

# PART 4 — DATABASE STRATEGY

## 4.1 Legacy tables stay exactly as they are

Your 14 existing tables are production data. Django must **read and write them without owning their schema**.

```python
# apps/tracking/models.py
class WorkSession(models.Model):
    id          = models.AutoField(primary_key=True)
    emp_id      = models.CharField(max_length=20, db_index=True)
    name        = models.CharField(max_length=100)
    project     = models.CharField(max_length=150)
    client_code = models.CharField(max_length=50)
    work_type   = models.CharField(max_length=100)
    batch       = models.CharField(max_length=100)
    work_units  = models.IntegerField(default=0)
    start_time  = models.DateTimeField()
    end_time    = models.DateTimeField(null=True, blank=True)
    total_time  = models.FloatField(null=True)
    average_time= models.FloatField(null=True)
    is_paused   = models.BooleanField(default=False)
    paused_at   = models.DateTimeField(null=True)
    paused_by   = models.CharField(max_length=20, blank=True)
    paused_elapsed = models.FloatField(default=0)
    allocation_id  = models.CharField(max_length=50, null=True, blank=True)
    is_started  = models.SmallIntegerField(default=0)  # 0=alloc 1=running 2=done

    class Meta:
        managed  = False              # ← Django will NEVER alter this table
        db_table = "ot_user_work_data"
        indexes  = []                 # declare in SQL, not migrations
```

Bootstrap them mechanically, then hand-correct:

```bash
python manage.py inspectdb ot_employees ot_users ot_worktypes ot_projects \
  ot_clientcode ot_shift_master ot_user_work_data aps_Break_Times \
  ot_user_login_history ot_feedbacks ot_feedback_images \
  ot_batch_allocations ot_orders_history ot_targets > _generated_models.py
```

`inspectdb` gets column types right and relationships wrong. Fix by hand: add `related_name`, convert bare `CharField` role/status columns to `choices`, set `db_index=True` where you actually query.

## 4.2 New tables are Django-managed

Chat, presence, notifications, files, outbox and report-jobs are new. `managed = True` (the default). Migrations create only these — `makemigrations` will not touch the legacy tables because they're `managed = False`.

Naming convention for new tables: **`ot_` prefix retained** so a DBA browsing the schema sees one coherent application.

## 4.3 One additive change to a legacy table

Django's `AbstractBaseUser` requires a `last_login` column. `ot_users` doesn't have one. Because the model is `managed = False`, Django will not add it. Run this once, manually:

```sql
ALTER TABLE ot_users
  ADD COLUMN last_login DATETIME NULL DEFAULT NULL AFTER password;
```

Additive, nullable, zero impact on the existing Flask app if you're running both during cutover.

## 4.4 New schema (DDL)

```sql
-- ─────────────────────────── CHAT ───────────────────────────
CREATE TABLE ot_chat_conversations (
  id             BIGINT AUTO_INCREMENT PRIMARY KEY,
  conv_type      ENUM('direct','group','project','announcement') NOT NULL,
  title          VARCHAR(150) NULL,
  project_id     VARCHAR(20)  NULL,
  created_by     VARCHAR(20)  NOT NULL,
  is_archived    TINYINT(1)   NOT NULL DEFAULT 0,
  last_message_id BIGINT      NULL,
  last_activity_at DATETIME   NOT NULL,
  created_at     DATETIME     NOT NULL,
  -- for direct chats: sorted "empA:empB" so a pair can only ever have one row
  direct_key     VARCHAR(45)  NULL,
  UNIQUE KEY uq_direct (direct_key),
  KEY ix_activity (last_activity_at DESC),
  KEY ix_project (project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ot_chat_participants (
  id                   BIGINT AUTO_INCREMENT PRIMARY KEY,
  conversation_id      BIGINT      NOT NULL,
  emp_id               VARCHAR(20) NOT NULL,
  role                 ENUM('member','moderator') NOT NULL DEFAULT 'member',
  joined_at            DATETIME    NOT NULL,
  left_at              DATETIME    NULL,
  last_read_message_id BIGINT      NOT NULL DEFAULT 0,
  unread_count         INT         NOT NULL DEFAULT 0,
  is_muted             TINYINT(1)  NOT NULL DEFAULT 0,
  UNIQUE KEY uq_conv_emp (conversation_id, emp_id),
  KEY ix_emp_active (emp_id, left_at),
  CONSTRAINT fk_part_conv FOREIGN KEY (conversation_id)
      REFERENCES ot_chat_conversations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ot_chat_messages (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  conversation_id BIGINT      NOT NULL,
  sender_emp_id   VARCHAR(20) NOT NULL,
  msg_type        ENUM('text','file','image','system') NOT NULL DEFAULT 'text',
  body            TEXT        NULL,
  reply_to_id     BIGINT      NULL,
  client_msg_id   CHAR(36)    NOT NULL,      -- UUID from browser → idempotency
  edited_at       DATETIME    NULL,
  deleted_at      DATETIME    NULL,
  created_at      DATETIME    NOT NULL,
  UNIQUE KEY uq_client_msg (conversation_id, client_msg_id),
  KEY ix_conv_id (conversation_id, id DESC),   -- keyset pagination
  CONSTRAINT fk_msg_conv FOREIGN KEY (conversation_id)
      REFERENCES ot_chat_conversations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ────────────────────────── FILES ───────────────────────────
CREATE TABLE ot_stored_files (
  id             BIGINT AUTO_INCREMENT PRIMARY KEY,
  uuid           CHAR(36)     NOT NULL UNIQUE,
  owner_emp_id   VARCHAR(20)  NOT NULL,
  context        ENUM('chat','feedback','allocation','export') NOT NULL,
  original_name  VARCHAR(255) NOT NULL,
  stored_path    VARCHAR(500) NOT NULL,       -- relative to storage root
  thumb_path     VARCHAR(500) NULL,
  mime_type      VARCHAR(120) NOT NULL,       -- sniffed, not client-supplied
  size_bytes     BIGINT       NOT NULL,
  sha256         CHAR(64)     NOT NULL,
  scan_status    ENUM('pending','clean','blocked') NOT NULL DEFAULT 'pending',
  created_at     DATETIME     NOT NULL,
  KEY ix_owner (owner_emp_id),
  KEY ix_sha (sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ot_chat_attachments (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  message_id  BIGINT NOT NULL,
  file_id     BIGINT NOT NULL,
  KEY ix_msg (message_id),
  CONSTRAINT fk_att_msg  FOREIGN KEY (message_id) REFERENCES ot_chat_messages(id) ON DELETE CASCADE,
  CONSTRAINT fk_att_file FOREIGN KEY (file_id)    REFERENCES ot_stored_files(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ───────────────────────── PRESENCE ─────────────────────────
CREATE TABLE ot_presence (
  emp_id           VARCHAR(20) PRIMARY KEY,
  status           ENUM('online','idle','busy','on_break','working','offline')
                     NOT NULL DEFAULT 'offline',
  status_source    ENUM('socket','work_session','break','manual') NOT NULL DEFAULT 'socket',
  custom_status    VARCHAR(80) NULL,
  connection_count SMALLINT    NOT NULL DEFAULT 0,
  last_seen_at     DATETIME    NOT NULL,
  last_heartbeat_at DATETIME   NULL,
  updated_at       DATETIME    NOT NULL,
  KEY ix_status (status, last_seen_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ─────────────────────── NOTIFICATIONS ──────────────────────
CREATE TABLE ot_notifications (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  recipient_emp_id VARCHAR(20) NOT NULL,
  notif_type    VARCHAR(60)  NOT NULL,      -- see registry.py
  title         VARCHAR(150) NOT NULL,
  body          VARCHAR(500) NULL,
  payload       JSON         NULL,
  link_url      VARCHAR(255) NULL,
  priority      ENUM('low','normal','high','critical') NOT NULL DEFAULT 'normal',
  actor_emp_id  VARCHAR(20)  NULL,
  read_at       DATETIME     NULL,
  created_at    DATETIME     NOT NULL,
  expires_at    DATETIME     NULL,
  KEY ix_inbox (recipient_emp_id, read_at, id DESC),
  KEY ix_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ot_notification_prefs (
  id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  emp_id     VARCHAR(20) NOT NULL,
  notif_type VARCHAR(60) NOT NULL,
  in_app     TINYINT(1)  NOT NULL DEFAULT 1,
  email      TINYINT(1)  NOT NULL DEFAULT 0,
  UNIQUE KEY uq_pref (emp_id, notif_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ──────────────── OUTBOX (replay & polling fallback) ────────
CREATE TABLE ot_realtime_outbox (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  topic       VARCHAR(80)  NOT NULL,        -- e.g. chat.conv.41
  audience    VARCHAR(80)  NOT NULL,        -- group name
  event_type  VARCHAR(60)  NOT NULL,
  payload     JSON         NOT NULL,
  created_at  DATETIME     NOT NULL,
  KEY ix_topic_id (topic, id),
  KEY ix_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ──────────────── ASYNC REPORT EXPORTS ──────────────────────
CREATE TABLE ot_report_jobs (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  requested_by  VARCHAR(20) NOT NULL,
  report_key    VARCHAR(60) NOT NULL,
  params        JSON        NOT NULL,
  status        ENUM('queued','running','done','failed') NOT NULL DEFAULT 'queued',
  file_id       BIGINT      NULL,
  error_message VARCHAR(500) NULL,
  created_at    DATETIME    NOT NULL,
  finished_at   DATETIME    NULL,
  KEY ix_user (requested_by, id DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**Why `ot_realtime_outbox` exists.** Redis pub/sub is fire-and-forget: if a user's socket is down for eight seconds, those events are gone forever. The outbox is the durable log. On reconnect the client sends its last-seen id per topic and `GET /api/v1/realtime/sync` replays the gap from MySQL. This is what makes the chat *correct* rather than merely *fast*. Prune it nightly via Celery beat (keep 7 days).

## 4.5 Index checklist

Run these against the legacy tables — most are probably missing and they are the difference between a 40 ms and a 4 s report.

```sql
ALTER TABLE ot_user_work_data ADD INDEX ix_emp_start (emp_id, start_time);
ALTER TABLE ot_user_work_data ADD INDEX ix_started   (is_started, start_time);
ALTER TABLE ot_user_work_data ADD INDEX ix_project   (project, start_time);
ALTER TABLE aps_Break_Times   ADD INDEX ix_user_open (user_id, end_time);
ALTER TABLE ot_user_login_history ADD INDEX ix_emp_date (emp_id, date);
ALTER TABLE ot_feedbacks      ADD INDEX ix_emp_created (emp_id, created_at);
ALTER TABLE ot_batch_allocations ADD INDEX ix_emp_status (employee_id, status);
```

Take a `mysqldump` before touching a production table. On tables over ~1M rows use `ALTER TABLE ... ALGORITHM=INPLACE, LOCK=NONE`.

---

# PART 5 — AUTH, SESSIONS & THE C-1 FIX

## 5.1 Custom user model on the legacy table

```python
# apps/accounts/models.py
from django.contrib.auth.models import AbstractBaseUser
from django.db import models
from core.timezone import now_ist


class UserManager(models.Manager):
    def get_by_natural_key(self, emp_id):
        return self.get(emp_id=emp_id, status="active")


class User(AbstractBaseUser):
    """Maps onto the existing ot_users table. No PermissionsMixin —
    that would demand auth_group / auth_permission M2M tables we don't want.
    Role comes from ot_employees, which is the business source of truth."""

    id         = models.AutoField(primary_key=True)
    emp_id     = models.CharField(max_length=20, unique=True)
    name       = models.CharField(max_length=100)
    password   = models.CharField(max_length=255)      # inherited name, existing column
    status     = models.CharField(max_length=10, default="active")
    session_id = models.CharField(max_length=64, null=True, blank=True)
    last_login = models.DateTimeField(null=True, blank=True)   # added by ALTER (§4.3)

    USERNAME_FIELD = "emp_id"
    objects = UserManager()

    class Meta:
        managed  = False
        db_table = "ot_users"

    # -- role is derived, never stored twice --
    _employee_cache = None

    @property
    def employee(self):
        if self._employee_cache is None:
            from apps.accounts.models import Employee
            self._employee_cache = Employee.objects.filter(
                employee_id=self.emp_id).first()
        return self._employee_cache

    @property
    def role(self):
        return (self.employee.role if self.employee else "employee").lower()

    @property
    def is_admin(self):        return self.role == "admin"
    @property
    def is_supervisor(self):   return self.role in ("admin", "supervisor")
    @property
    def is_active(self):       return self.status == "active"

    # Django admin compatibility without PermissionsMixin
    @property
    def is_staff(self):        return self.is_admin
    def has_perm(self, perm, obj=None):   return self.is_admin
    def has_module_perms(self, app_label): return self.is_admin
```

Set in `settings/base.py` **before your first `migrate`**:

```python
AUTH_USER_MODEL = "accounts.User"
```

## 5.2 Migrating existing bcrypt hashes

Your Flask app stores raw bcrypt (`$2b$12$...`). Django expects an algorithm-prefixed string (`bcrypt$$2b$12$...`). Two options — take option A.

**Option A — one-time prefix migration (recommended).**

```python
# scripts/migrate_password_hashes.py
"""Run ONCE. Idempotent — re-running is safe."""
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "opstracking.settings.prod")
django.setup()

from django.db import connection

with connection.cursor() as c:
    c.execute("""
        UPDATE ot_users
           SET password = CONCAT('bcrypt$', password)
         WHERE password LIKE '$2%'
    """)
    print(f"prefixed {c.rowcount} hashes")
```

```python
# settings/base.py
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",  # new passwords
    "django.contrib.auth.hashers.BCryptPasswordHasher",        # legacy, plain bcrypt
]
```

Django auto-upgrades a user's hash to the first hasher on their next successful login. Within a few weeks everyone is on the stronger scheme with zero password resets.

**Option B — custom hasher** that reads the bare `$2b$` format. Keeps the DB untouched but leaves you maintaining crypto code forever. Don't.

## 5.3 Sessions — this is the C-1 fix, for free

Django's session framework is server-side by default: the cookie holds only an opaque key, the state lives in `django_session`. `django.contrib.auth.logout()` **deletes that row**. A replayed cookie after logout resolves to nothing and the request is anonymous. C-1 disappears as a category, not as a patch.

```python
# settings/prod.py
SESSION_ENGINE            = "django.contrib.sessions.backends.cached_db"   # Redis + MySQL
SESSION_COOKIE_NAME       = "opstrack_sid"
SESSION_COOKIE_HTTPONLY   = True
SESSION_COOKIE_SECURE     = True
SESSION_COOKIE_SAMESITE   = "Lax"
SESSION_COOKIE_AGE        = 60 * 60 * 12          # one shift
SESSION_SAVE_EVERY_REQUEST = True                 # sliding expiry

CSRF_COOKIE_SECURE   = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = ["https://<your-host>"]

SECURE_SSL_REDIRECT       = True
SECURE_PROXY_SSL_HEADER   = ("HTTP_X_FORWARDED_PROTO", "https")   # set by the proxy
SECURE_HSTS_SECONDS       = 31536000
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS           = "DENY"
DEBUG = False                                                      # ← FIXES C-6
```

Keep writing `ot_users.session_id` in `AuthService.login/logout` for one release cycle so any residual Flask-era code stays consistent, then drop the column.

## 5.4 Logout must also kill the WebSocket

A subtlety the FastAPI plan didn't cover: invalidating the HTTP session does **not** close an already-open WebSocket. The socket authenticated once, at handshake. Left alone, a logged-out user keeps receiving chat messages.

```python
# apps/accounts/services.py
class AuthService(BaseService):

    def logout(self, request):
        emp_id = request.user.emp_id
        session_key = request.session.session_key

        LoginHistory.objects.filter(
            emp_id=emp_id, logout_time__isnull=True
        ).update(logout_time=now_ist())

        User.objects.filter(pk=request.user.pk).update(session_id=None)

        django_logout(request)                       # deletes django_session row

        # kick every live socket for this session   ← the missing half of C-1
        publish(group=f"user.{emp_id}",
                event="session.revoked",
                data={"session_key": session_key})

        PresenceService().force_offline(emp_id)
```

`BaseAuthedConsumer` handles `session.revoked` by closing with code `4401`, and the browser client treats 4401 as "redirect to /login" rather than "reconnect".

---

# PART 6 — SERVICE LAYER (the OOP core)

Views are thin. Serializers validate. **Services own business rules.** Models own persistence. Nothing outside a service writes to the database.

```python
# core/services.py
class BaseService:
    def __init__(self, actor=None):
        self.actor = actor                      # the User performing the action

    def require(self, condition, message, code="forbidden"):
        if not condition:
            raise DomainError(message, code=code)
```

## 6.1 WorkSessionService — server-side timing (H-2, H-6)

```python
# apps/tracking/services.py
class WorkSessionService(BaseService):

    @transaction.atomic
    def end_session(self, session_id, work_units, review=None, pages=None):
        session = (WorkSession.objects
                   .select_for_update()
                   .filter(pk=session_id, end_time__isnull=True)
                   .first())
        self.require(session, "No open session found", code="not_found")

        # Only the owner, or an admin/supervisor, may close it
        self.require(
            session.emp_id == self.actor.emp_id or self.actor.is_supervisor,
            "Not your session")

        end = now_ist()                                    # ← server clock. ← H-2, H-6
        elapsed = (end - session.start_time).total_seconds()
        total   = max(elapsed - (session.paused_elapsed or 0), 0)

        session.end_time     = end
        session.work_units   = work_units
        session.total_time   = round(total, 2)
        session.average_time = round(total / work_units, 2) if work_units else None
        session.is_started   = 2
        session.is_paused    = False
        session.save(update_fields=[
            "end_time", "work_units", "total_time",
            "average_time", "is_started", "is_paused"])

        transaction.on_commit(lambda: self._announce(session))
        return session

    def _announce(self, session):
        PresenceService().recompute(session.emp_id)
        publish(group=f"user.{session.emp_id}",
                event="work.session.completed",
                data={"id": session.id, "total_time": session.total_time})
```

The client may still *send* an `end_time` — the serializer simply discards it. The browser clock is never trusted for anything that lands in a report.

## 6.2 BreakService — server-owned allowances (H-3, H-4)

```python
# apps/breaks/constants.py
BREAK_ALLOWANCES = {          # seconds — server owns these, client never sends them
    "Tea break 1": 300,
    "Meal break": 2100,
    "Tea break 2": 300,
}

# apps/breaks/services.py
class BreakService(BaseService):

    @transaction.atomic
    def start_break(self, break_type):
        allowance = BREAK_ALLOWANCES.get(break_type)
        self.require(allowance, "Unknown break type", code="validation_error")

        already_open = (BreakTime.objects
                        .select_for_update()
                        .filter(user_id=self.actor.emp_id, end_time__isnull=True)
                        .exists())
        self.require(not already_open, "A break is already running")   # ← H-4

        brk = BreakTime.objects.create(
            user_id       = self.actor.emp_id,
            break_type    = break_type,
            start_time    = now_ist(),
            allotted_time = allowance,                                 # ← H-3
        )
        transaction.on_commit(
            lambda: PresenceService().set_status(
                self.actor.emp_id, "on_break", source="break"))
        return brk
```

Note `select_for_update()` on the existence check. Without the row lock, two clicks 40 ms apart on a flaky connection both see "no open break" and both insert. H-4 is a race condition, and only the database can arbitrate it.

## 6.3 DRF permission classes (C-2, C-3, C-4, C-5)

```python
# core/permissions.py
class IsAuthenticatedEmployee(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_active)

class IsAdmin(IsAuthenticatedEmployee):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_admin

class IsAdminOrSupervisor(IsAuthenticatedEmployee):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_supervisor

class IsOwnerOrSupervisor(IsAuthenticatedEmployee):
    """Object-level ownership. Set `owner_field` on the ViewSet."""
    def has_object_permission(self, request, view, obj):
        if request.user.is_supervisor:
            return True
        return getattr(obj, getattr(view, "owner_field", "emp_id")) == request.user.emp_id
```

The global default is the important line — **deny by default, opt out explicitly**, so a forgotten decorator can never again produce C-2:

```python
# settings/base.py
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "core.permissions.IsAuthenticatedEmployee",          # ← FIXES C-2 globally
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "core.exception_handler.handle",    # ← FIXES M-9, M-10
    "DEFAULT_THROTTLE_RATES": {
        "chat_send": "30/min",
        "upload":    "20/min",
        "login":     "10/min",
    },
}
```

Add one test that walks the URLConf and asserts every route either requires auth or appears on a short explicit allowlist (`/login`, `/health`, static). That test is what stops C-2 from ever coming back.

## 6.4 Consistent error envelope (M-9, M-10)

```python
# core/exception_handler.py
def handle(exc, context):
    if isinstance(exc, DomainError):
        return Response({"ok": False, "error": {"code": exc.code,
                                                "message": str(exc)}},
                        status=exc.http_status)

    response = drf_exception_handler(exc, context)
    if response is not None:
        response.data = {"ok": False,
                         "error": {"code": _code_for(response.status_code),
                                   "message": _flatten(response.data)}}
        return response

    # Unhandled: log the real thing, show the user nothing.   ← FIXES M-10
    logger.exception("unhandled", extra={"path": context["request"].path})
    return Response({"ok": False,
                     "error": {"code": "server_error",
                               "message": "Something went wrong. "
                                          "Reference: " + get_request_id()}},
                    status=500)
```

A stack trace or raw `str(e)` never reaches a browser. The request id ties the user's screenshot to your log line.

---

# PART 7 — REAL-TIME LAYER (Channels)

## 7.1 The one rule that keeps this simple

> **Writes go over HTTP. Pushes come over WebSocket.**
> Exceptions: `typing` and `heartbeat` — ephemeral, high-frequency, never persisted.

Sending a chat message is `POST /api/v1/chat/conversations/{id}/messages/`. Not a WebSocket frame.

Why this is right:
- One validation path (the DRF serializer), one permission path, one throttle, one audit trail.
- HTTP gives you a status code. A dropped WS frame gives you silence.
- Idempotency via `client_msg_id` + a unique index is trivial over HTTP and awkward over a socket.
- Debugging is `curl`, not a socket client.

The extra round-trip is ~30 ms and invisible behind optimistic UI.

## 7.2 ASGI wiring

```python
# opstracking/asgi.py
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "opstracking.settings.prod")

from django.core.asgi import get_asgi_application
django_asgi_app = get_asgi_application()          # must come before app imports

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.sessions import SessionMiddlewareStack
from apps.realtime.middleware import TicketAuthMiddleware
from opstracking.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,          # Daphne can serve HTTP too; the proxy won't route it there
    "websocket": TicketAuthMiddleware(
        SessionMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
```

```python
# opstracking/routing.py
from django.urls import path
from apps.realtime.consumers import GatewayConsumer

websocket_urlpatterns = [
    path("ws/gateway/", GatewayConsumer.as_asgi()),
]
```

**One socket per tab, not one per feature.** A single `GatewayConsumer` multiplexes chat, presence and notifications over topic-tagged frames. Three sockets per user × 150 users = 450 connections and three reconnect storms every time the wifi blips. One socket = 150 connections and one reconnect.

## 7.3 Channel layer

```python
# settings/base.py
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [{"address": "redis://:PASSWORD@127.0.0.1:6379/0"}],
            "capacity": 1500,
            "expiry": 20,
            "group_expiry": 86400,
        },
    },
}
```

## 7.4 Group naming

```python
# apps/realtime/groups.py
def user_group(emp_id: str) -> str:      return f"user.{emp_id}"
def conv_group(conv_id: int) -> str:     return f"chat.conv.{conv_id}"
def presence_group() -> str:             return "presence.all"
def project_group(project_id) -> str:    return f"project.{project_id}"
def role_group(role: str) -> str:        return f"role.{role}"
```

Every socket joins `user.{emp_id}` and `presence.all` at connect. It joins `chat.conv.{id}` for each active conversation.

## 7.5 Authentication at handshake

Two paths, both supported. The session cookie is sent on a same-origin WebSocket handshake, so `SessionMiddlewareStack` alone usually works. The **ticket** is the robust path — it survives proxy quirks, cookie-partitioning changes and any future move to a separate subdomain.

```python
# apps/realtime/tickets.py
TICKET_TTL = 60          # seconds
TICKET_PREFIX = "wsticket:"

class TicketService:
    def issue(self, user, session_key):
        token = secrets.token_urlsafe(32)
        cache.set(TICKET_PREFIX + token,
                  {"emp_id": user.emp_id, "session_key": session_key},
                  timeout=TICKET_TTL)
        return token

    def redeem(self, token):
        key = TICKET_PREFIX + token
        data = cache.get(key)
        cache.delete(key)          # single use — a replayed ticket is dead
        return data
```

```python
# apps/realtime/middleware.py
class TicketAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        qs = parse_qs(scope.get("query_string", b"").decode())
        token = (qs.get("ticket") or [None])[0]
        if token:
            data = await sync_to_async(TicketService().redeem)(token)
            if data:
                scope["user"] = await get_user_by_emp_id(data["emp_id"])
                scope["session_key"] = data["session_key"]
        return await super().__call__(scope, receive, send)
```

The ticket is single-use and expires in 60 s, so even if it leaks into a proxy access log it is worthless by the time anyone reads it.

## 7.6 Wire protocol

Every frame, both directions, is the same envelope:

```jsonc
{
  "v":     1,
  "op":    "event",              // hello | ready | ping | pong | sub | unsub |
                                 // event | ack | error | resume
  "topic": "chat.conv.41",
  "type":  "chat.message.created",
  "seq":   918233,               // outbox id — the client's replay cursor
  "ts":    "2026-08-05T14:22:11+05:30",
  "data":  { }
}
```

Client → server ops are deliberately few: `ping`, `sub`, `unsub`, `resume`, `typing`, `presence.set`. Everything else is HTTP.

## 7.7 The gateway consumer

```python
# apps/realtime/consumers.py
class GatewayConsumer(AsyncJsonWebsocketConsumer):

    HEARTBEAT_GRACE = 45          # seconds; client pings every 20

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.emp_id      = user.emp_id
        self.session_key = self.scope.get("session_key")
        self.groups_joined = set()

        await self.accept()
        await self._join(user_group(self.emp_id))
        await self._join(presence_group())
        for conv_id in await get_active_conversation_ids(self.emp_id):
            await self._join(conv_group(conv_id))

        await PresenceService.aconnect(self.emp_id)

        await self.send_json({
            "v": 1, "op": "ready",
            "data": {
                "emp_id": self.emp_id,
                "server_time": now_ist().isoformat(),
                "heartbeat_interval": 20,
                "cursors": await get_topic_cursors(self.emp_id),
            },
        })

    async def disconnect(self, code):
        if hasattr(self, "emp_id"):
            await PresenceService.adisconnect(self.emp_id)

    # ── inbound ──────────────────────────────────────────────
    async def receive_json(self, content, **kw):
        op = content.get("op")
        if op == "ping":
            await self.send_json({"v": 1, "op": "pong",
                                  "ts": now_ist().isoformat()})
            await PresenceService.aheartbeat(self.emp_id)

        elif op == "typing":
            conv_id = content["data"]["conversation_id"]
            if conv_group(conv_id) in self.groups_joined:
                await self.channel_layer.group_send(conv_group(conv_id), {
                    "type": "fanout",
                    "payload": {"v": 1, "op": "event",
                                "topic": conv_group(conv_id),
                                "type": "chat.typing",
                                "data": {"emp_id": self.emp_id,
                                         "conversation_id": conv_id}},
                    "exclude": self.emp_id,
                })

        elif op == "sub":
            topic = content["data"]["topic"]
            if await can_subscribe(self.emp_id, topic):     # authorise every join
                await self._join(topic)

        elif op == "resume":
            # client reports its cursors; replay the gap from the outbox
            for topic, last_id in content["data"]["cursors"].items():
                for ev in await replay_outbox(topic, last_id, self.emp_id):
                    await self.send_json(ev)

    # ── outbound (called by channel_layer.group_send) ────────
    async def fanout(self, message):
        if message.get("exclude") == self.emp_id:
            return
        await self.send_json(message["payload"])

    async def session_revoked(self, message):
        if message.get("session_key") in (None, self.session_key):
            await self.close(code=4401)

    async def _join(self, group):
        await self.channel_layer.group_add(group, self.channel_name)
        self.groups_joined.add(group)
```

`can_subscribe()` is not optional. Without it any authenticated user can send `{"op":"sub","data":{"topic":"chat.conv.999"}}` and read a conversation they aren't in — the WebSocket equivalent of C-5.

## 7.8 The single publish entry point

Nothing in the codebase calls `channel_layer` directly except this function. That gives you one place to add the outbox write, one place to instrument, one place to change transport later.

```python
# core/events.py
def publish(*, group: str, event: str, data: dict,
            durable: bool = True, exclude: str | None = None) -> int | None:
    """Fan an event out to a Channels group. Returns the outbox seq if durable."""
    seq = None
    if durable:
        seq = OutboxEvent.objects.create(
            topic=group, audience=group, event_type=event,
            payload=data, created_at=now_ist()).id

    async_to_sync(get_channel_layer().group_send)(group, {
        "type": "fanout",
        "exclude": exclude,
        "payload": {"v": 1, "op": "event", "topic": group,
                    "type": event, "seq": seq,
                    "ts": now_ist().isoformat(), "data": data},
    })
    return seq
```

**Always call it inside `transaction.on_commit()`.** Publishing before commit means a subscriber can fetch a row that doesn't exist yet, or worse, see an event for a transaction that then rolls back.

---

# PART 8 — CHAT

## 8.1 Sending a message

```python
# apps/chat/services.py
class ChatService(BaseService):

    @transaction.atomic
    def send(self, conversation_id, body=None, client_msg_id=None,
             file_ids=None, reply_to_id=None):

        conv = (Conversation.objects
                .select_for_update()
                .filter(pk=conversation_id, is_archived=False)
                .first())
        self.require(conv, "Conversation not found", code="not_found")

        me = Participant.objects.filter(
            conversation=conv, emp_id=self.actor.emp_id, left_at__isnull=True
        ).first()
        self.require(me, "You are not in this conversation")

        self.require(body or file_ids, "Message is empty", code="validation_error")

        # Idempotency: a retried request returns the original message
        existing = Message.objects.filter(
            conversation=conv, client_msg_id=client_msg_id).first()
        if existing:
            return existing

        msg = Message.objects.create(
            conversation   = conv,
            sender_emp_id  = self.actor.emp_id,
            msg_type       = "file" if file_ids else "text",
            body           = (body or "").strip()[:4000],
            reply_to_id    = reply_to_id,
            client_msg_id  = client_msg_id or str(uuid4()),
            created_at     = now_ist(),
        )

        if file_ids:
            files = FileService(self.actor).claim(file_ids, context="chat")
            Attachment.objects.bulk_create(
                [Attachment(message=msg, file=f) for f in files])
            msg.msg_type = "image" if all(
                f.mime_type.startswith("image/") for f in files) else "file"
            msg.save(update_fields=["msg_type"])

        Conversation.objects.filter(pk=conv.pk).update(
            last_message_id=msg.id, last_activity_at=msg.created_at)

        # unread counters for everyone except the sender — one UPDATE, no N+1
        Participant.objects.filter(
            conversation=conv, left_at__isnull=True
        ).exclude(emp_id=self.actor.emp_id).update(
            unread_count=F("unread_count") + 1)

        transaction.on_commit(lambda: self._after_send(conv, msg))
        return msg

    def _after_send(self, conv, msg):
        payload = MessageSerializer(msg).data
        publish(group=conv_group(conv.id),
                event="chat.message.created",
                data=payload)
        # notify only participants who are offline or have the conv muted-off
        fanout_chat_notifications.delay(conv.id, msg.id, self.actor.emp_id)
```

## 8.2 Reading — keyset pagination, never OFFSET

```python
# apps/chat/views.py
class MessageViewSet(viewsets.ModelViewSet):
    serializer_class   = MessageSerializer
    permission_classes = [IsConversationParticipant]
    throttle_scope     = "chat_send"

    def get_queryset(self):
        conv_id = self.kwargs["conversation_id"]
        qs = (Message.objects
              .filter(conversation_id=conv_id, deleted_at__isnull=True)
              .select_related("conversation")
              .prefetch_related("attachments__file")
              .order_by("-id"))
        before = self.request.query_params.get("before")
        if before:
            qs = qs.filter(id__lt=int(before))       # keyset — constant time at page 400
        return qs[:50]
```

`LIMIT ... OFFSET 20000` makes MySQL walk 20,000 rows before returning 50. `WHERE id < ? ORDER BY id DESC LIMIT 50` is an index seek. In a chat that accumulates messages forever, this is the difference between a product and a complaint.

## 8.3 Read receipts

Store a **pointer** (`last_read_message_id`), not a row per message per reader. 150 users × 500 messages/day = 75,000 rows/day with per-message receipts, versus 150 updated integers.

```python
def mark_read(self, conversation_id, up_to_message_id):
    Participant.objects.filter(
        conversation_id=conversation_id, emp_id=self.actor.emp_id
    ).update(last_read_message_id=up_to_message_id, unread_count=0)

    publish(group=conv_group(conversation_id),
            event="chat.read",
            data={"emp_id": self.actor.emp_id, "up_to": up_to_message_id},
            durable=False)          # transient; no value in replaying it
```

## 8.4 Direct conversations can't be duplicated

The `direct_key` unique index makes this structurally impossible:

```python
def direct_key(a: str, b: str) -> str:
    return ":".join(sorted([a, b]))

def get_or_create_direct(self, other_emp_id):
    key = direct_key(self.actor.emp_id, other_emp_id)
    conv, created = Conversation.objects.get_or_create(
        direct_key=key,
        defaults={"conv_type": "direct", "created_by": self.actor.emp_id,
                  "last_activity_at": now_ist(), "created_at": now_ist()},
    )
    if created:
        Participant.objects.bulk_create([
            Participant(conversation=conv, emp_id=e, joined_at=now_ist())
            for e in (self.actor.emp_id, other_emp_id)])
    return conv
```

Two people clicking "message" on each other at the same instant get one conversation, because the database says so.

## 8.5 XSS

Message bodies are stored **raw** and escaped **at render**. Never the other way round — storing escaped text corrupts the data (an employee legitimately typing `<3` or a code snippet), and double-escaping bugs are endemic.

- Server: DRF returns the raw string in JSON. JSON is not HTML; no escaping needed at that layer.
- Client: build with `textContent`, never `innerHTML`. If you must render links, run a whitelist linkifier that escapes first and injects anchors second.
- Enforce a CSP header: `default-src 'self'; script-src 'self'; object-src 'none'`.

---

# PART 9 — PRESENCE

## 9.1 Presence is derived, not declared

"Online" for an ops floor means more than "has a socket". Your app already knows whether someone is in a work session or on a break. Fold that in.

Precedence, highest wins:

| Priority | Status | Derived from |
|---|---|---|
| 1 | `on_break` | open row in `aps_Break_Times` |
| 2 | `working` | open row in `ot_user_work_data` (`is_started=1`, not paused) |
| 3 | `busy` | user set it manually |
| 4 | `online` | ≥1 socket, heartbeat within 45 s |
| 5 | `idle` | socket alive but no heartbeat for 5 min |
| 6 | `offline` | zero sockets, or heartbeat older than 45 s |

```python
# apps/presence/services.py
KEY   = "presence:{emp_id}"
CONNS = "presence:conns:{emp_id}"
TTL   = 45

class PresenceService:

    def recompute(self, emp_id) -> str:
        if BreakTime.objects.filter(user_id=emp_id, end_time__isnull=True).exists():
            status, source = "on_break", "break"
        elif WorkSession.objects.filter(
                emp_id=emp_id, is_started=1, is_paused=False,
                end_time__isnull=True).exists():
            status, source = "working", "work_session"
        elif cache.get(CONNS.format(emp_id=emp_id), 0) > 0:
            status, source = "online", "socket"
        else:
            status, source = "offline", "socket"

        self._store(emp_id, status, source)
        return status

    def _store(self, emp_id, status, source):
        previous = cache.get(KEY.format(emp_id=emp_id), {}).get("status")
        cache.set(KEY.format(emp_id=emp_id),
                  {"status": status, "source": source,
                   "at": now_ist().isoformat()}, timeout=TTL * 2)

        PresenceState.objects.update_or_create(
            emp_id=emp_id,
            defaults={"status": status, "status_source": source,
                      "last_seen_at": now_ist(), "updated_at": now_ist()})

        if previous != status:                       # only broadcast real changes
            publish(group=presence_group(),
                    event="presence.changed",
                    data={"emp_id": emp_id, "status": status},
                    durable=False)
```

The `previous != status` guard matters. Without it, every 20-second heartbeat from every user broadcasts to every user: 150 × 150 / 20 s ≈ **1,125 messages per second** of pure noise. With it, you broadcast only on actual transitions — a few dozen per hour.

## 9.2 Reaping the dead

A browser tab closed by force-quit, a laptop lid slammed shut, a train tunnel — none of these fire `disconnect`. Redis TTL plus a beat task cleans up:

```python
# apps/presence/tasks.py
@shared_task
def reap_stale_presence():
    cutoff = now_ist() - timedelta(seconds=PresenceService.TTL)
    stale = PresenceState.objects.filter(
        last_seen_at__lt=cutoff).exclude(status="offline")
    for row in stale.iterator():
        if not cache.get(PresenceService.KEY.format(emp_id=row.emp_id)):
            PresenceService().force_offline(row.emp_id)
```

Scheduled every 30 seconds via `django-celery-beat`.

## 9.3 Presence bootstrap

Page load fetches the full roster once — `GET /api/v1/presence/` returns every employee's current status in one request — then applies `presence.changed` deltas over the socket. Never poll presence.

---

# PART 10 — NOTIFICATIONS

## 10.1 A registry, not scattered strings

```python
# apps/notifications/registry.py
@dataclass(frozen=True)
class NotificationType:
    key: str
    title_template: str
    default_in_app: bool = True
    default_email: bool = False
    priority: str = "normal"

REGISTRY = {t.key: t for t in [
    NotificationType("allocation.assigned",
                     "New order {task_id} assigned to you", priority="high"),
    NotificationType("allocation.sla_breach",
                     "SLA breach risk on {task_id}", priority="critical",
                     default_email=True),
    NotificationType("feedback.received",
                     "Quality feedback on {order_batch_id}", priority="high"),
    NotificationType("chat.mention",
                     "{actor_name} mentioned you"),
    NotificationType("chat.message",
                     "New message from {actor_name}", priority="low"),
    NotificationType("break.overrun",
                     "Your {break_type} has exceeded {allotted} minutes"),
    NotificationType("work.target_met",
                     "Daily target met for {project}", priority="low"),
    NotificationType("report.ready",
                     "Your {report_key} export is ready"),
]}
```

## 10.2 One call site

```python
# apps/notifications/services.py
class NotificationService:

    def notify(self, recipients, notif_type, context, link=None, actor=None):
        spec = REGISTRY[notif_type]
        rows = []
        for emp_id in set(recipients):
            if emp_id == getattr(actor, "emp_id", None):
                continue                                # never notify the actor
            if not self._wants(emp_id, notif_type, "in_app"):
                continue
            rows.append(Notification(
                recipient_emp_id=emp_id,
                notif_type=notif_type,
                title=spec.title_template.format(**context),
                body=context.get("body", "")[:500],
                payload=context,
                link_url=link,
                priority=spec.priority,
                actor_emp_id=getattr(actor, "emp_id", None),
                created_at=now_ist(),
            ))
        created = Notification.objects.bulk_create(rows)

        for n in created:
            publish(group=user_group(n.recipient_emp_id),
                    event="notification.created",
                    data=NotificationSerializer(n).data)

        email_targets = [n for n in created
                         if self._wants(n.recipient_emp_id, notif_type, "email")]
        if email_targets:
            send_notification_emails.delay([n.id for n in email_targets])
        return created
```

Always fire from `transaction.on_commit`, and for large audiences push the whole thing to Celery so the HTTP request returns immediately.

## 10.3 Notification triggers to wire up

| Event | Recipients | Type |
|---|---|---|
| Allocation assigned | assignee | `allocation.assigned` |
| SLA within 2 h (beat) | assignee + supervisors | `allocation.sla_breach` |
| Feedback created | subject employee | `feedback.received` |
| `@name` in chat | mentioned users | `chat.mention` |
| Chat message, recipient offline | offline participants | `chat.message` |
| Break exceeds allowance (beat) | employee + supervisor | `break.overrun` |
| Report export finished | requester | `report.ready` |

---

# PART 11 — FILE SHARING

## 11.1 Two-step upload

1. `POST /api/v1/files/` (multipart) → validate, store, return `{uuid, id, thumb_url}`
2. `POST .../messages/` with `file_ids: [id]` → message + attachment rows

Binary over WebSocket is a trap: no resumability, no progress events, head-of-line blocking on the control channel, and 25 MB frames that stall every other subscriber on that consumer.

## 11.2 Validation gate — order matters

```python
# apps/files/scanners.py
ALLOWED = {
    "image/jpeg": [".jpg", ".jpeg"], "image/png": [".png"],
    "image/webp": [".webp"], "image/gif": [".gif"],
    "application/pdf": [".pdf"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    "text/csv": [".csv"], "text/plain": [".txt"],
}
MAX_BYTES = 25 * 1024 * 1024

def validate(uploaded) -> str:
    if uploaded.size > MAX_BYTES:
        raise DomainError("File exceeds 25 MB", code="file_too_large")

    head = uploaded.read(2048); uploaded.seek(0)
    sniffed = magic.from_buffer(head, mime=True)      # real bytes, not the header
    if sniffed not in ALLOWED:
        raise DomainError("File type not permitted", code="file_type_blocked")

    ext = Path(uploaded.name).suffix.lower()
    if ext not in ALLOWED[sniffed]:                   # .exe renamed to .jpg dies here
        raise DomainError("Extension does not match content", code="file_type_blocked")
    return sniffed
```

Trusting `uploaded.content_type` is trusting the browser, which is trusting the attacker.

## 11.3 Storage

```python
# apps/files/services.py
class FileService(BaseService):

    def store(self, uploaded, context):
        mime = validate(uploaded)
        digest = hashlib.sha256()
        for chunk in uploaded.chunks():
            digest.update(chunk)
        uploaded.seek(0)

        file_uuid = uuid4()
        rel = f"uploads/{context}/{now_ist():%Y/%m}/{file_uuid}{Path(uploaded.name).suffix.lower()}"
        abs_path = Path(settings.PRIVATE_STORAGE_ROOT) / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        with open(abs_path, "wb") as fh:
            for chunk in uploaded.chunks():
                fh.write(chunk)
        os.chmod(abs_path, 0o640)

        row = StoredFile.objects.create(
            uuid=str(file_uuid), owner_emp_id=self.actor.emp_id, context=context,
            original_name=Path(uploaded.name).name[:255],       # strips any path
            stored_path=rel, mime_type=mime, size_bytes=uploaded.size,
            sha256=digest.hexdigest(), scan_status="clean", created_at=now_ist())

        if mime.startswith("image/"):
            make_thumbnail.delay(row.id)         # Celery: strips EXIF, caps at 480px
        return row
```

Non-negotiables in that function:
- **Filename is a UUID.** The user's name is metadata only. Path traversal has nowhere to go.
- **Stored outside `public_html`.** No URL can reach the bytes directly.
- **Mode `0640`.** The web server's user cannot read it; only the app user can.
- **SHA-256 recorded.** Free deduplication and a tamper check.

## 11.4 Authenticated download

```python
class FileDownloadView(APIView):
    permission_classes = [IsAuthenticatedEmployee]

    def get(self, request, file_uuid):
        stored = get_object_or_404(StoredFile, uuid=file_uuid, scan_status="clean")

        if not FileAccessPolicy(request.user).can_read(stored):
            raise PermissionDenied()                 # ← the IDOR guard

        path = Path(settings.PRIVATE_STORAGE_ROOT) / stored.stored_path
        response = FileResponse(open(path, "rb"), content_type=stored.mime_type)
        response["Content-Disposition"] = (
            f'attachment; filename="{escape_uri_path(stored.original_name)}"')
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, max-age=0, no-store"
        return response
```

`can_read` for a chat attachment means: *is this user a participant in the conversation that this attachment's message belongs to?* Same principle as C-5, applied to bytes instead of rows.

For throughput, enable your web server's sendfile support and return `X-Sendfile` instead of streaming through Python. Django still checks permissions; the web server just moves the bytes.

## 11.5 Fix the feedback-image BLOB while you're here

`ot_feedback_images.image_data` stores images inside MySQL. That bloats every backup, blows the InnoDB buffer pool, and makes `mysqldump` unusable. Migrate them into `ot_stored_files` with a one-off management command during a maintenance window. Your DB size will likely drop by an order of magnitude.

---

# PART 12 — CELERY

## 12.1 Configuration

```python
# opstracking/celery.py
app = Celery("opstracking")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# settings/base.py
CELERY_BROKER_URL         = env("REDIS_URL") + "/1"
CELERY_RESULT_BACKEND     = "django-db"
CELERY_TIMEZONE           = "Asia/Kolkata"
CELERY_ENABLE_UTC         = False
CELERY_TASK_ACKS_LATE     = True          # survive a worker OOM mid-task
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1     # long tasks must not hog the queue
CELERY_TASK_TIME_LIMIT    = 600
CELERY_TASK_SOFT_TIME_LIMIT = 540
CELERY_TASK_ROUTES = {
    "apps.reports.tasks.*":       {"queue": "reports"},
    "apps.files.tasks.*":         {"queue": "default"},
    "apps.notifications.tasks.*": {"queue": "default"},
    "apps.chat.tasks.*":          {"queue": "default"},
}
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
```

Two queues, two workers. A 90-second Excel export must never sit in front of a notification fan-out.

## 12.2 Task inventory

| Task | Queue | Trigger | Purpose |
|---|---|---|---|
| `build_report_task` | reports | on request | Excel/CSV generation → `StoredFile` → notify |
| `bulk_import_allocations` | reports | on upload | parse sheet, validate rows, insert |
| `make_thumbnail` | default | after upload | Pillow resize, strip EXIF |
| `fanout_chat_notifications` | default | after send | notify offline participants |
| `send_notification_emails` | default | after notify | SMTP |
| `reap_stale_presence` | default | beat / 30 s | mark dead sockets offline |
| `check_break_overruns` | default | beat / 1 min | alert on exceeded allowance |
| `check_sla_breaches` | default | beat / 15 min | allocation SLA warnings |
| `prune_outbox` | default | beat / daily 02:00 | delete outbox rows > 7 days |
| `prune_notifications` | default | beat / daily 02:15 | delete read notifications > 60 days |
| `nightly_summary_email` | reports | beat / daily 20:00 | supervisor digest |

## 12.3 Async report exports — the pattern that saves your web workers

Generating a 50,000-row Excel file inside a request holds a Gunicorn worker for 60–120 seconds. Five concurrent exports and the whole application is unresponsive.

```python
# apps/reports/views.py
class ReportExportView(APIView):
    permission_classes = [IsAdminOrSupervisor]

    def post(self, request):
        job = ReportJob.objects.create(
            requested_by=request.user.emp_id,
            report_key=request.data["report_key"],
            params=request.data.get("params", {}),
            created_at=now_ist())
        build_report_task.delay(job.id)
        return Response({"ok": True, "job_id": job.id}, status=202)
```

The browser gets `202` instantly. When the task finishes it writes a `StoredFile` and calls `NotificationService.notify(..., "report.ready", link=download_url)` — which arrives over the WebSocket as a toast with a download link. **This is the single highest-leverage performance change in the whole migration.**

---

# PART 13 — FRONTEND

## 13.1 Jinja2 in Django

Django ships a Jinja2 backend; you keep your existing templates.

```python
# settings/base.py
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {"environment": "opstracking.jinja2_env.environment"},
    },
    {   # keep DTL for DRF's browsable API and admin
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ]},
    },
]
```

```python
# opstracking/jinja2_env.py
def environment(**options):
    env = Environment(autoescape=True, **options)     # autoescape ON. always.
    env.globals.update({
        "static": static,
        "url": reverse,
        "csrf_input": csrf_input,
        "now_ist": now_ist,
    })
    return env
```

Template migration from Flask is nearly mechanical:

| Flask | Django + Jinja2 |
|---|---|
| `url_for('auth.login')` | `url('accounts:login')` |
| `session.get('role')` | `current_user.role` (from context processor) |
| `{{ form.csrf_token }}` | `{{ csrf_input(request) }}` |
| `render_template('x.html', v=1)` | `render(request, 'x.html', {'v': 1})` |
| `get_flashed_messages()` | `messages` (django.contrib.messages) |

## 13.2 The realtime client

One file, one socket, one event bus. Every feature subscribes to it.

```javascript
// static/js/realtime/realtime-client.js
class RealtimeClient {
  constructor({ url, onEvent }) {
    this.url = url;
    this.onEvent = onEvent;
    this.ws = null;
    this.attempt = 0;
    this.cursors = {};              // topic -> last seq seen
    this.pending = [];              // frames queued while offline
    this.state = "idle";
    this.heartbeatTimer = null;
    this.pongDeadline = null;
  }

  async connect() {
    if (this.state === "connecting" || this.state === "open") return;
    this.state = "connecting";

    let ticket;
    try {
      const r = await fetch("/api/v1/realtime/ticket/", {
        method: "POST",
        headers: { "X-CSRFToken": getCsrfToken() },
        credentials: "same-origin",
      });
      if (r.status === 401) return this._sessionExpired();
      ticket = (await r.json()).ticket;
    } catch {
      return this._scheduleReconnect();       // API down: back off, keep trying
    }

    const scheme = location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(`${scheme}://${location.host}/ws/gateway/?ticket=${ticket}`);

    this.ws.onopen = () => {
      this.state = "open";
      this.attempt = 0;
      this._send({ v: 1, op: "resume", data: { cursors: this.cursors } });
      this.pending.splice(0).forEach(f => this._send(f));
      this._startHeartbeat();
      bus.emit("realtime:open");
    };

    this.ws.onmessage = (e) => {
      const frame = JSON.parse(e.data);
      if (frame.op === "pong") { this.pongDeadline = null; return; }
      if (frame.op === "ready") { bus.emit("realtime:ready", frame.data); return; }
      if (frame.seq && frame.topic) this.cursors[frame.topic] = frame.seq;
      this.onEvent(frame);
    };

    this.ws.onclose = (evt) => {
      this.state = "closed";
      this._stopHeartbeat();
      bus.emit("realtime:closed");
      if (evt.code === 4401) return this._sessionExpired();
      this._scheduleReconnect();
    };

    this.ws.onerror = () => this.ws && this.ws.close();
  }

  send(frame) {
    if (this.state === "open") this._send(frame);
    else this.pending.push(frame);            // replayed on reconnect
  }

  _send(frame) { this.ws.send(JSON.stringify(frame)); }

  _startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      if (this.pongDeadline && Date.now() > this.pongDeadline) {
        this.ws.close();                      // zombie socket: force a reconnect
        return;
      }
      this.pongDeadline = Date.now() + 10000;
      this._send({ v: 1, op: "ping" });
    }, 20000);
  }

  _stopHeartbeat() { clearInterval(this.heartbeatTimer); this.pongDeadline = null; }

  _scheduleReconnect() {
    this.attempt += 1;
    const base  = Math.min(1000 * 2 ** this.attempt, 30000);
    const delay = base * (0.5 + Math.random());        // jitter: no thundering herd
    setTimeout(() => this.connect(), delay);
  }

  _sessionExpired() {
    this.state = "expired";
    bus.emit("realtime:expired");
    window.location.href = "/login?reason=session_expired";
  }
}
```

Four details that are easy to skip and expensive to skip:

1. **Jitter on backoff.** If the websocket process restarts, 150 browsers reconnect. Without jitter they arrive in the same 50 ms window and knock Daphne over on its first breath.
2. **Ping/pong with a deadline.** A TCP connection can be dead while `readyState` still reads `OPEN` — mobile networks and captive portals do this routinely. Only an unanswered ping detects it.
3. **Cursors + `resume`.** This is what makes a tunnel-induced 30-second gap invisible to the user.
4. **`pending` queue.** A typing indicator sent while offline should be dropped; a `sub` should not. Queue, replay on open.

## 13.3 Optimistic send

```javascript
// static/js/features/chat.js
async function sendMessage(convId, text, fileIds = []) {
  const clientMsgId = crypto.randomUUID();

  renderMessage({                      // paint immediately
    client_msg_id: clientMsgId, body: text,
    sender_emp_id: CURRENT_USER.emp_id,
    created_at: new Date().toISOString(),
    _pending: true,
  });

  try {
    const msg = await api.post(`/api/v1/chat/conversations/${convId}/messages/`, {
      body: text, client_msg_id: clientMsgId, file_ids: fileIds,
    });
    reconcileMessage(clientMsgId, msg);        // swap in the server row
  } catch (err) {
    markMessageFailed(clientMsgId, err);       // show a retry affordance
  }
}

// the WebSocket echo arrives too — dedupe on client_msg_id
bus.on("chat.message.created", (data) => {
  if (document.querySelector(`[data-cmid="${data.client_msg_id}"]`)) {
    reconcileMessage(data.client_msg_id, data);
    return;
  }
  renderMessage(data);
  if (!isConversationVisible(data.conversation_id)) bumpUnread(data.conversation_id);
});
```

The sender receives the message twice — once as the HTTP response, once over the socket. `client_msg_id` collapses them. Without it every message you send appears twice, and that is the single most common bug in hand-rolled chat.

## 13.4 Toasts replace `alert()` — this is UI-1

```javascript
// static/js/core/toast.js
export const toast = {
  show(msg, { type = "info", timeout = 5000, action = null } = {}) { /* ... */ },
  success(m, o) { this.show(m, { ...o, type: "success" }); },
  error(m, o)   { this.show(m, { ...o, type: "error", timeout: 8000 }); },
};

// api.js routes every non-2xx envelope here
if (!res.ok) {
  const { error } = await res.json();
  toast.error(error.message);
  throw new ApiError(error);
}
```

Then delete every `alert()` in the codebase. Copy guidance for the messages themselves: say what happened and what to do next, in the interface's voice. *"Couldn't save the project — a project with this ID already exists."* Not *"Error!"* and not *"Sorry, something went wrong."*

## 13.5 Presence rendering

```javascript
bus.on("presence.changed", ({ emp_id, status }) => {
  document.querySelectorAll(`[data-presence="${emp_id}"]`)
    .forEach(el => { el.dataset.status = status; el.title = LABELS[status]; });
});
```

```css
[data-presence]::before {
  content: ""; width: .5rem; height: .5rem; border-radius: 50%;
  display: inline-block; margin-right: .4rem;
  background: var(--dot-offline);
  transition: background .18s ease;
}
[data-presence][data-status="online"]::before   { background: var(--dot-online); }
[data-presence][data-status="working"]::before  { background: var(--dot-working); }
[data-presence][data-status="on_break"]::before { background: var(--dot-break); }
[data-presence][data-status="idle"]::before     { background: var(--dot-idle); }
@media (prefers-reduced-motion: reduce) { [data-presence]::before { transition: none; } }
```

Attribute-driven, so a status change is one dataset write and zero DOM rebuilds.

## 13.6 CSRF with session auth

DRF `SessionAuthentication` enforces CSRF on unsafe methods. Your fetch wrapper must send the header or every POST returns 403:

```javascript
function getCsrfToken() {
  return document.cookie.split("; ")
    .find(c => c.startsWith("csrftoken="))?.split("=")[1] ?? "";
}

export const api = {
  async post(url, body) {
    const res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify(body),
    });
    return handle(res);
  },
};
```

---
# PART 14 — DEPLOYMENT

Written against requirements rather than a vendor. Anything that satisfies
Part 0 will run this; the specifics below are the shape the deployment takes,
whatever supplies it.

## 14.1 What you are deploying

Five long-running processes plus a reverse proxy:

| Process | Binds | Restart policy |
|---|---|---|
| Reverse proxy (TLS termination) | `:80`, `:443` | always |
| Gunicorn — DRF + pages (WSGI) | `127.0.0.1:8001` | always |
| Daphne — WebSockets (ASGI) | `127.0.0.1:8002` | always |
| Celery worker, `default` queue | — | always |
| Celery worker, `reports` queue | — | always |
| Celery beat scheduler | — | always |
| Redis | `127.0.0.1:6379` | always |
| PostgreSQL / MySQL | `127.0.0.1:5432` / `:3306` | always |

**Nothing except the reverse proxy is reachable from the internet.**

## 14.2 Layout on disk

The only thing under the web root is `static/`. Application code, `.env` and
`storage/` live outside it.

```
<app-user-home>/
├── app/                  ← the git repo
│   ├── manage.py
│   └── .env              ← chmod 600, never committed
├── .venv/
├── storage/              ← uploads. NEVER under the web root.
├── logs/
└── <web-root>/
    └── static/           ← collectstatic target ONLY
```

That placement rule is the whole point: if a misconfiguration ever exposes the
document root, it exposes CSS — not database credentials and not employees'
uploaded files.

## 14.3 First deployment

```bash
git clone <repo> app && cd app
python3.12 -m venv ../.venv
../.venv/bin/pip install -U pip wheel
../.venv/bin/pip install -r requirements.txt

cp .env.example .env && chmod 600 .env && $EDITOR .env

../.venv/bin/python manage.py migrate --settings=opstracking.settings.prod
../.venv/bin/python manage.py collectstatic --noinput --settings=opstracking.settings.prod
../.venv/bin/python manage.py bootstrap_storage --settings=opstracking.settings.prod
```

Against an existing legacy database, set `LEGACY_TABLES_MANAGED=False` and use
`migrate --fake-initial` so Django adopts the tables without issuing DDL. Run
`scripts/migrate_password_hashes.py --apply` once.

System packages: Redis, `libmagic`, a database client library, and a compiler
if any dependency needs to build.

## 14.4 Process supervision

Use whatever the host provides — systemd, supervisord, a container
orchestrator, a platform's process model. The commands are the same:

```bash
# HTTP (DRF + Jinja2 pages)
gunicorn opstracking.wsgi:application \
    --bind 127.0.0.1:8001 \
    --workers 3 --threads 4 --worker-class gthread \
    --timeout 120 --graceful-timeout 30 \
    --max-requests 1000 --max-requests-jitter 100

# WebSockets
daphne -b 127.0.0.1 -p 8002 --proxy-headers opstracking.asgi:application

# Background work
celery -A opstracking worker -Q default -c 4 -l INFO --max-tasks-per-child=200
celery -A opstracking worker -Q reports -c 2 -l INFO
celery -A opstracking beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

The two web processes are tuned differently on purpose. Gunicorn recycles
workers (`--max-requests`) to bound memory growth during report generation.
Daphne wants long uptime and no recycling, because every restart drops every
open socket.

## 14.5 Redis

Bound to loopback, password-protected, never exposed:

```conf
bind 127.0.0.1 -::1
protected-mode yes
requirepass <long random string>
maxmemory 512mb
maxmemory-policy allkeys-lru
appendonly no
```

`allkeys-lru` is right here: everything Redis holds for this application —
presence, cache, channel groups — is reconstructible. The durable record lives
in the database.

## 14.6 Reverse proxy

Three rules, and **the order matters** because proxies match first-wins:

1. `/static/` — served from disk, never proxied. Far-future `Expires`;
   filenames are content-hashed so a year-long cache is still correct.
2. `/ws/` — proxied to `127.0.0.1:8002` **with the WebSocket upgrade
   preserved** and a long timeout (3600s).
3. Everything else — proxied to `127.0.0.1:8001`.

Set `X-Forwarded-Proto: https` so Django's `SECURE_PROXY_SSL_HEADER` sees the
real scheme; without it, `request.is_secure()` is false behind the proxy and
secure cookies are never set.

Verify the upgrade actually happens — this is the single most common thing to
get wrong:

```bash
curl -i -N \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  https://<host>/ws/gateway/
```

`HTTP/1.1 101 Switching Protocols` means it works. A `200`, `400` or `502`
means the proxy is not upgrading: check the module is loaded and that the
`/ws/` rule is matched before the catch-all.

## 14.7 Subsequent deployments

`scripts/deploy.sh` runs the sequence: pull, install, migrate, collectstatic,
`check --deploy`, reload, health check. It takes the restart commands from
`RELOAD_API_CMD`, `RESTART_WORKER_CMD` and `RESTART_WS_CMD`, so it adapts to
whatever supervises the processes.

Reload the HTTP process gracefully — in-flight requests finish and nobody sees
a 502. Restart the WebSocket process **only when consumer code changed**: every
restart disconnects every user at once. The client backs off with jitter so
they do not all return in the same instant, but it is still churn worth
avoiding.

## 14.8 Backups

```bash
./scripts/backup_db.sh    # nightly, via cron
```

Dumps the database, mirrors `storage/`, prunes beyond the retention window.

Host-level snapshots protect the machine. They do not give you a point-in-time
table restore when someone truncates the wrong thing at 4 pm. Keep both — and
restore a backup into a scratch database on a schedule, because a backup you
have never restored is a hypothesis, not a backup.

## 14.9 Operational checks

```bash
./scripts/healthcheck.sh
```

- `/health/` — liveness. Touches no dependency, so a Redis outage does not
  cause the supervisor to restart a healthy web process.
- `/ready/` — readiness. Checks the database and cache, returns 503 if either
  is down.

Also confirm: all processes come back after a reboot; logs rotate and the disk
does not fill; the TLS certificate renews.

---

# PART 15 — SECURITY FIX MATRIX

How the architecture closes every issue from your testing report — structurally, not by patching.

| ID | Issue | Fix | Where |
|---|---|---|---|
| C-1 | Logout doesn't invalidate | Django server-side sessions delete the row; `session.revoked` closes live sockets | §5.3, §5.4 |
| C-2 | Unauthenticated data access | `DEFAULT_PERMISSION_CLASSES` deny-by-default + URLConf audit test | §6.3 |
| C-3 | Employee deletes master data | `IsAdmin` on masters ViewSets | §6.3 |
| C-4 | Employee creates allocations | `IsAdminOrSupervisor` on allocations | §6.3 |
| C-5 | Cross-employee feedback read | `IsOwnerOrSupervisor` object permission + `can_subscribe` on WS topics | §6.3, §7.7 |
| C-6 | Debug mode on in production | `settings/prod.py` `DEBUG=False`; dev settings never deployed | §3, §5.3 |
| H-1 | Dead endpoints (delete/pause/resume) | Implemented in `WorkSessionService` | §6.1 |
| H-2 | Timing computed client-side | `end_session()` uses `now_ist()`; client value discarded | §6.1 |
| H-3 | Break allowance from client | `BREAK_ALLOWANCES` server constant; not a serializer field | §6.2 |
| H-4 | Multiple simultaneous breaks | `select_for_update()` existence check | §6.2 |
| H-6 | UTC dates in 26 places | `core/timezone.now_ist()`; a lint rule bans bare `datetime.now()` | §3 |
| M-1 | Success on missing record | ORM `.first()` + `require()` → 404; `update()` rowcount checked | §6.1 |
| M-2 | Blank / duplicate names | Serializer `min_length` + `UniqueValidator` + DB unique index | §6, §4.4 |
| M-3 | Long text silently truncated | Serializer `max_length` matched to column width | §6 |
| M-6 | Missing frontend endpoints | Built or explicitly `501` with a logged TODO | §6 |
| M-9 | Errors returned as HTTP 200 | Central DRF exception handler → correct status codes | §6.4 |
| M-10 | DB errors shown to users | Handler logs the exception, returns a request-id reference | §6.4 |
| UI-1 | `alert()` popups | Toast system; every `alert()` removed | §13.4 |

**New surface introduced by real-time — do not skip these:**

| Risk | Mitigation |
|---|---|
| Unauthorised WS topic subscription | `can_subscribe()` gate on every `sub` op | §7.7 |
| Socket outlives logout | `session.revoked` → close 4401 | §5.4 |
| Malicious file upload | magic-byte sniff + extension match + UUID name + storage outside webroot + `0640` | §11.2, §11.3 |
| Attachment IDOR | `FileAccessPolicy.can_read()` on every download | §11.4 |
| Stored XSS in messages | store raw, escape at render, `textContent` only, CSP | §8.5 |
| Chat spam / flood | DRF throttle `chat_send: 30/min`, typing rate-limited client-side | §6.3 |
| Presence broadcast storm | change-only broadcast (`previous != status`) | §9.1 |
| WS ticket replay | single-use, 60 s TTL, deleted on redeem | §7.5 |

---

# PART 16 — PERFORMANCE

## 16.1 Ranked by impact

1. **Move Excel exports to Celery.** Removes 60–120 s worker locks. Biggest single win. (§12.3)
2. **Add the missing indexes.** Report queries drop from seconds to tens of milliseconds. (§4.5)
3. **Keyset pagination in chat.** Constant-time regardless of history depth. (§8.2)
4. **Change-only presence broadcast.** ~1,100 msg/s → a few dozen per hour. (§9.1)
5. **Cache master data in Redis.** Worktypes/projects/client codes change hourly at most; they're read on every page.
6. **Move feedback images out of MySQL BLOBs.** Shrinks backups and frees the buffer pool. (§11.5)
7. **`select_related` / `prefetch_related` everywhere.** Django's N+1 is silent until it isn't.
8. **`CONN_MAX_AGE = 60`.** Stop opening a MySQL connection per request.
9. **Compression + far-future `Expires` on `/static/` at the proxy.**
10. **Hashed static filenames** via `ManifestStaticFilesStorage` so you can cache for a year and still ship changes.

## 16.2 Capacity at your scale

150 concurrent WebSocket connections is not a lot. One Daphne process handles several thousand. Do not shard, do not add a second WS node, do not reach for Kubernetes. The bottleneck will be MySQL on report queries, and the fix is indexes.

```python
# settings/prod.py
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME"), "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"), "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}
```

`STRICT_TRANS_TABLES` is what turns M-3 (silent truncation) from a data-corruption bug into a loud error.

---

# PART 17 — PHASED PLAN

| Phase | Deliverable | Gate |
|---|---|---|
| **0** | Provision the runtime: processes, Redis, database, reverse proxy. Deploy a `/health/` endpoint end to end. | `curl` returns 101 on `/ws/` |
| **1** | Django project, settings split, `core/` package, custom User, password-hash migration, session auth. | Login/logout works; replayed cookie → 401 |
| **2** | Legacy models (`managed=False`), verified against production data. | Read-only parity vs Flask on all 14 tables |
| **3** | Serializers + services + ViewSets for accounts, masters, tracking, breaks. **All security fixes land here.** | C-1…C-6, H-2, H-3, H-4, H-6 tests pass |
| **4** | Allocations, feedback, settings. Reports moved to Celery. | Excel export returns 202 + notification |
| **5** | Templates → Jinja2, static reorganised, `api.js`, `toast.js`. Every `alert()` gone. | All screens render identically |
| **6** | Channels: gateway consumer, tickets, `publish()`, outbox, `realtime-client.js`. | Two browsers exchange a test event; kill wifi 30 s → resume replays |
| **7** | Presence: service, consumer, reaper, UI dots. | Break start flips the dot within 1 s across all clients |
| **8** | Notifications: registry, service, consumer, bell UI, triggers. | Allocation assign → toast on assignee's screen |
| **9** | Chat: models, service, ViewSets, upload pipeline, chat UI. | 1:1 + group + file share + read receipts + reconnect |
| **10** | Hardening: rate limits, CSP, load test at 200 sockets, backups, runbook. | Sign-off checklist below |

Phases 0–5 are the migration; 6–10 are the new capability. Ship phases 0–5 and
run them for a week before starting 6 — do not debug a framework migration and
a WebSocket layer at the same time.

## 17.1 Current status

The repository implements phases 1 and 3–8. Specifically:

| Built | Where |
|---|---|
| Project skeleton, settings split, `core/` package | `opstracking/`, `core/` |
| Custom user on the legacy table, session auth, hash migration | `apps/accounts/`, `scripts/migrate_password_hashes.py` |
| Legacy models with preserved table names | `apps/*/models.py` |
| Services, serializers and ViewSets for the business apps | `apps/accounts,masters,tracking,breaks,allocations,feedback,settings_app/` |
| Reports moved to Celery, returning 202 | `apps/reports/` |
| Jinja2 templates, `api.js`, `toast.js`, no `alert()` | `templates/`, `static/js/` |
| Channels gateway, tickets, `publish()`, durable outbox, client | `apps/realtime/`, `static/js/realtime/` |
| Presence: service, reaper, UI dots | `apps/presence/` |
| Notifications: registry, service, bell UI, triggers | `apps/notifications/` |
| Upload/download pipeline | `apps/files/` |

**Deferred: phase 9 (chat).** `apps/chat/` holds the design decisions and the
file layout, but nothing is implemented and the app is not wired in. See
`apps/chat/README.md`.

**Outstanding: phase 2 verification** against real production data, and phase
10 hardening — a load test at 200 sockets, and a restore drill.

## 17.2 Go-live checklist

**Security**
- [ ] `DEBUG = False`; `ALLOWED_HOSTS` explicit
- [ ] Every route requires auth except a written allowlist (automated test)
- [ ] Employee account cannot `DELETE /api/v1/masters/projects/{id}/` → 403
- [ ] Employee cannot read another employee's feedback → 403
- [ ] Employee cannot `sub` to a conversation they're not in
- [ ] Logout: old cookie → 401 **and** the open socket closes
- [ ] `.env` is `0600` and outside the web root
- [ ] `storage/` is outside the web root; a direct URL → 404
- [ ] `.exe` renamed `.jpg` is rejected on upload
- [ ] Redis has `requirepass` and binds to loopback only

**Real-time**
- [ ] `curl` upgrade test returns `101`
- [ ] Message appears on the other browser in < 500 ms
- [ ] Kill wifi for 30 s → reconnect replays missed messages exactly once
- [ ] Two tabs → one message, not two (dedupe works)
- [ ] Restart the websocket process → all clients reconnect within 30 s, staggered
- [ ] Presence flips to `on_break` when a break starts
- [ ] Force-quit browser → user shows offline within 45 s

**Correctness**
- [ ] `total_time` computed server-side; a tampered client `end_time` is ignored
- [ ] Two rapid break-start clicks create one row
- [ ] All timestamps IST
- [ ] Over-length input returns 400, not a truncated row
- [ ] DB error → generic message + request id; stack trace in log only

**Operations**
- [ ] All processes are supervised and survive a reboot
- [ ] `deploy.sh` runs clean from a fresh clone
- [ ] Nightly `mysqldump` verified by an actual restore into a scratch DB
- [ ] Logs rotate (`logrotate`); disk does not fill
- [ ] TLS certificate renewal confirmed

---

# APPENDIX A — CHANGES FROM THE FASTAPI PLAN

| FastAPI plan | Django/DRF equivalent | Note |
|---|---|---|
| Pydantic `XxxCreate/Update/Response` | DRF `Serializer` (+ separate read/write serializers) | Same validation boundary |
| `repositories/*.py` raw SQL | Model `Manager` / `QuerySet` classes | `managed=False` keeps legacy schema |
| `services/*.py` | `apps/*/services.py` | Unchanged — this layer ports directly |
| `routers/*.py` | `views.py` ViewSets + DRF router | Thin, same role |
| `Depends(require_admin)` | `permission_classes = [IsAdmin]` | Deny-by-default globally |
| `core/dependencies.py` | `core/permissions.py` + `core/authentication.py` | |
| FastAPI native WebSockets | Django Channels consumers | **Requires ASGI + Redis either way** |
| `aiomysql` async pool | `mysqlclient` + `CONN_MAX_AGE` | DRF is sync; async pooling buys nothing |
| No background jobs | Celery + beat | New capability |
| `main.py` app factory | `wsgi.py` + `asgi.py` | Two processes by design |

The service layer — the part you actually designed — is unchanged. The framework swap is a rewrite of the transport shell around it.

---
