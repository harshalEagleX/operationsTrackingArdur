"""Chat services — NOT IMPLEMENTED.

The intended interface, so callers can be written against it before the
implementation exists.
"""

from __future__ import annotations

from core.exceptions import NotImplementedYetError
from core.services import BaseService


class ChatService(BaseService):
    """Send, edit, delete and read messages.

    Every method raises until chat is built. Raising ``NotImplementedYetError``
    rather than ``NotImplementedError`` means a caller gets a clean 501 with
    the standard error envelope instead of a 500 with a stack trace.
    """

    def get_or_create_direct(self, other_emp_id: str):
        """Return the 1:1 conversation between the actor and another employee.

        Must use ``get_or_create`` on the ``direct_key`` unique index — the
        sorted pair, e.g. "E1042:E1088" — so two simultaneous clicks produce
        one conversation rather than two.
        """
        raise NotImplementedYetError("Chat is not available on this deployment.")

    def send(self, conversation_id: int, body: str = "", client_msg_id: str | None = None,
             file_ids: list[int] | None = None, reply_to_id: int | None = None):
        """Post a message.

        Required behaviour:
          * verify the actor is a participant who has not left
          * return the existing row if ``client_msg_id`` was already used
            (idempotent retry, not a duplicate)
          * bump ``last_activity_at`` and every other participant's
            ``unread_count`` in one UPDATE, not one per participant
          * publish ``chat.message.created`` from ``transaction.on_commit``
        """
        raise NotImplementedYetError("Chat is not available on this deployment.")

    def mark_read(self, conversation_id: int, up_to_message_id: int):
        """Advance the read pointer. One integer per participant, not a row
        per message per reader."""
        raise NotImplementedYetError("Chat is not available on this deployment.")

    def edit(self, message_id: int, body: str):
        raise NotImplementedYetError("Chat is not available on this deployment.")

    def delete(self, message_id: int):
        """Soft delete — set ``deleted_at``. A message that vanishes from the
        middle of a thread makes the conversation unreadable."""
        raise NotImplementedYetError("Chat is not available on this deployment.")

    def can_access(self, conversation_id: int) -> bool:
        """Is the actor a current participant?

        This is the answer ``apps.realtime.groups.can_subscribe()`` needs for
        ``chat.conv.*`` topics, and the answer
        ``FileAccessPolicy._can_read_chat_file()`` needs for attachments.
        """
        return False
