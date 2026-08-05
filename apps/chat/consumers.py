"""Chat consumer — NOT IMPLEMENTED, AND PROBABLY NOT NEEDED.

Chat does **not** get its own WebSocket. ``apps.realtime.GatewayConsumer``
already multiplexes topics over one socket per tab, and chat becomes another
topic prefix (``chat.conv.{id}``) on that same connection.

Three sockets per user x 150 users is 450 connections and three reconnect
storms every time the office wifi blips. One socket is 150 and one storm.

What actually needs writing when chat lands:

  1. ``apps.realtime.groups.can_subscribe()`` — answer "is this user a
     participant?" for ``chat.conv.*`` topics. Without it, any authenticated
     user can send ``{"op":"sub","data":{"topic":"chat.conv.999"}}`` and read
     a conversation they are not in.
  2. ``GatewayConsumer._handle_typing()`` — currently returns 501. Typing is
     one of only two things that legitimately travel client→server over the
     socket: ephemeral, high-frequency, never persisted.
  3. Join the user's active conversation groups in ``GatewayConsumer.connect``.

This file stays as a signpost so nobody adds a second socket by reflex.
"""
