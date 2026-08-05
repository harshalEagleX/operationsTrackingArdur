"""Chat serializers — NOT IMPLEMENTED.

Notes for the implementation:

  * ``MessageSerializer`` returns ``body`` as the raw stored string. JSON is
    not HTML, so no escaping happens at this layer; the client escapes at
    render with ``textContent``.
  * ``client_msg_id`` is required on write and echoed on read — the client
    uses it to reconcile its optimistic row with the server's, and to
    deduplicate the HTTP response against the WebSocket echo.
  * Attachments serialise through ``apps.files.serializers.StoredFileSerializer``
    so a chat file and a feedback image have identical shapes on the wire.
"""
