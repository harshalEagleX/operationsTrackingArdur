"""Cross-cutting infrastructure.

``core`` owns no business models. It provides the base classes every app
inherits from: BaseService, the permission classes, the exception hierarchy,
the single realtime publish() entry point, and the IST clock.

Dependency rule: apps import from core. core never imports from apps.
"""
