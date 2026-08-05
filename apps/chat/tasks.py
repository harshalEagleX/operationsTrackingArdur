"""Chat background tasks — NOT IMPLEMENTED.

Planned, and why each one is a task rather than inline work:

    fanout_chat_notifications(conversation_id, message_id, sender_emp_id)
        Notify participants who are offline or have the conversation muted.
        A 40-person group would otherwise make the sender's request wait on
        40 preference lookups and 40 pushes.

    recount_unread(conversation_id)
        Repair job for unread counters. The counter is maintained
        incrementally with an F() expression on send, which is fast but can
        drift if a message is hard-deleted. Run on demand, not on a schedule.

    prune_chat_retention(days)
        Delete messages past the retention window, if the business sets one.
        Attachments go through FileService so the bytes are removed too, not
        just the rows.

Routed to the ``default`` queue by settings.CELERY_TASK_ROUTES, which already
has an ``apps.chat.tasks.*`` entry waiting.
"""
