"""Vertical slices.

Each package under ``apps/`` owns its own models, serializers, services,
views, tasks and (where relevant) consumers. A feature is added by creating a
directory, not by editing eight shared files.

Business domain
    accounts      users, employees, login history, authentication
    masters       work types, projects, client codes, shifts
    tracking      work sessions and daily targets
    breaks        break records and server-owned allowances
    allocations   batch allocations and order history
    feedback      quality / audit feedback
    reports       read-only selectors, exporters, async export jobs
    settings_app  application settings

Platform
    files         one upload/download pipeline for every app
    realtime      WebSocket transport: gateway, tickets, outbox
    presence      who is online / working / on break
    notifications the in-app notification inbox

Deferred
    chat          scaffolded only — see apps/chat/README.md
"""
