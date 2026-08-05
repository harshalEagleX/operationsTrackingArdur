# apps/chat — scaffolded, not implemented

Chat is **deliberately deferred**. This directory holds the shape of the
feature so that building it later is filling in files that already exist,
rather than re-deciding the architecture.

Nothing here is wired up:

- `apps.chat` is **not** in `INSTALLED_APPS` (see `opstracking/settings/base.py`)
- `/api/v1/chat/` is **not** routed (see `opstracking/api_urls.py`)
- `FEATURE_CHAT` defaults to `False`
- `can_subscribe()` refuses every `chat.*` topic (`apps/realtime/groups.py`)
- `FileAccessPolicy._can_read_chat_file()` returns `False`

Each of those is a one-line change, and all five are marked with a comment
pointing back here.

## What is already built that chat will use

Chat does not need new infrastructure. The platform pieces it depends on are
finished and in production use by presence and notifications:

| Need | Already exists |
|---|---|
| WebSocket transport | `apps/realtime/consumers.py` — `GatewayConsumer` multiplexes topics over one socket |
| Event fan-out | `core/events.py` — `publish()` |
| Replay after reconnect | `apps/realtime/models.py` — `OutboxEvent` + the `resume` op |
| Handshake auth | `apps/realtime/tickets.py` |
| Topic authorisation | `apps/realtime/groups.py` — `can_subscribe()` |
| File attachments | `apps/files/` — the whole upload/download pipeline |
| Notifications for offline recipients | `apps/notifications/` — `chat.mention` and `chat.message` are already in the registry |
| Rate limiting | `core/throttling.py` — `ChatBurstThrottle`, scope `chat_send` |

## Turning it on

1. Fill in the modules in this directory (they exist with the intended
   docstrings and `NotImplementedError` bodies).
2. Add `"apps.chat"` to `LOCAL_APPS` in `opstracking/settings/base.py`.
3. Uncomment the chat block in `opstracking/api_urls.py`.
4. Teach `can_subscribe()` to answer *"is this user a participant in this
   conversation?"* for `chat.conv.*` topics.
5. Implement `FileAccessPolicy._can_read_chat_file()` with the same rule.
6. `python manage.py makemigrations chat && python manage.py migrate`
7. Set `FEATURE_CHAT=True`.

## Design decisions already made

These are settled — they are why the scaffolding looks the way it does.

**Writes go over HTTP, pushes come over the WebSocket.** Sending a message is
`POST /api/v1/chat/conversations/{id}/messages/`, not a socket frame. That
gives one validation path, one permission path, one throttle, one audit trail,
and a status code instead of silence when something fails. The extra ~30 ms is
invisible behind optimistic UI. The only exception is `typing`, which is
ephemeral and never persisted.

**Idempotency via `client_msg_id`.** The browser generates a UUID per message;
a unique index on `(conversation_id, client_msg_id)` makes a retried request
return the original row instead of a duplicate. The sender receives the
message twice — once as the HTTP response, once over the socket — and
deduplicates on this id. Without it, every message you send appears twice,
which is the single most common bug in hand-rolled chat.

**Keyset pagination, never OFFSET.** `WHERE id < ? ORDER BY id DESC LIMIT 50`.
Use `core.pagination.KeysetPagination`. A chat accumulates messages forever,
and `OFFSET 20000` makes the database walk 20,000 rows to return 50.

**Read receipts are a pointer, not a row per reader per message.** Store
`last_read_message_id` on the participant. 150 users x 500 messages/day is
75,000 rows/day the other way, versus 150 updated integers.

**Direct conversations are deduplicated by the database.** A `direct_key`
column holding the sorted pair (`"E1042:E1088"`) with a unique index. Two
people clicking "message" on each other simultaneously get one conversation,
because the schema makes two impossible.

**Message bodies are stored raw and escaped at render.** Storing escaped text
corrupts the data — someone legitimately types `<3` or pastes a code snippet —
and double-escaping bugs are endemic. The client builds with `textContent`,
never `innerHTML`, and the CSP in `core/middleware.py` is the backstop.

## Schema sketch

Four tables, all `ot_`-prefixed to match the rest of the schema:

- `ot_chat_conversations` — `conv_type` (direct/group/project/announcement),
  `direct_key` UNIQUE, `last_message_id`, `last_activity_at`
- `ot_chat_participants` — `(conversation_id, emp_id)` UNIQUE,
  `last_read_message_id`, `unread_count`, `is_muted`, `left_at`
- `ot_chat_messages` — `(conversation_id, client_msg_id)` UNIQUE,
  index on `(conversation_id, id DESC)` for keyset reads
- `ot_chat_attachments` — joins a message to `ot_stored_files`

Full DDL is in `docs/OpsTracking_DRF_Realtime_Architecture.md` §4.4.
