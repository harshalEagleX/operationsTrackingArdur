"""Chat models — NOT IMPLEMENTED.

Left empty on purpose. Half-written models would be picked up by
``makemigrations`` the moment someone adds this app to INSTALLED_APPS, and a
migration for tables nobody has designed yet is worse than no file at all.

The intended schema is documented in apps/chat/README.md and specified in full
in docs/OpsTracking_DRF_Realtime_Architecture.md §4.4:

    Conversation   ot_chat_conversations   direct_key UNIQUE dedupes 1:1 chats
    Participant    ot_chat_participants    (conversation, emp_id) UNIQUE,
                                           last_read_message_id pointer
    Message        ot_chat_messages        (conversation, client_msg_id) UNIQUE
                                           for idempotent retries
    Attachment     ot_chat_attachments     joins Message → files.StoredFile

Notes for whoever builds this:

  * ``Message.body`` is TEXT and stores the raw string. Escaping happens at
    render, never at write.
  * The read index is ``(conversation_id, id DESC)`` — keyset pagination
    only, no OFFSET.
  * ``Conversation.last_activity_at`` is denormalised so the conversation
    list sorts without touching the messages table.
"""
