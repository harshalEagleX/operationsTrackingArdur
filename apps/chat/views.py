"""Chat views — NOT IMPLEMENTED.

Intended surface:

    GET    /api/v1/chat/conversations/                   list
    POST   /api/v1/chat/conversations/                   create group
    POST   /api/v1/chat/conversations/direct/            get-or-create 1:1
    GET    /api/v1/chat/conversations/{id}/messages/     keyset paginated
    POST   /api/v1/chat/conversations/{id}/messages/     send  (throttle: chat_send)
    POST   /api/v1/chat/conversations/{id}/read/         advance read pointer
    PATCH  /api/v1/chat/messages/{id}/                   edit
    DELETE /api/v1/chat/messages/{id}/                   soft delete

Every one of these is HTTP. The WebSocket carries pushes only — see
apps/chat/README.md for why.
"""

from __future__ import annotations

from rest_framework.views import APIView

from core.exceptions import NotImplementedYetError
from core.permissions import IsAuthenticatedEmployee


class ChatUnavailableView(APIView):
    """Placeholder that answers 501 for any chat route.

    Not routed by default. It exists so that if someone wires up
    ``/api/v1/chat/`` before the feature is finished, the frontend gets a
    documented 501 with the standard error envelope rather than a 404 that
    looks like a deployment problem.
    """

    permission_classes = [IsAuthenticatedEmployee]

    def get(self, request, *args, **kwargs):
        raise NotImplementedYetError("Chat is not available on this deployment.")

    post = put = patch = delete = get
