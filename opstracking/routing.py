"""Channels WebSocket routes.

One socket per browser tab, not one per feature. A single GatewayConsumer
multiplexes presence, notifications and (later) chat over topic-tagged frames.

Three sockets per user x 150 users is 450 connections and three reconnect
storms every time the wifi blips. One socket is 150 and one storm.
"""

from django.urls import path

from apps.realtime.consumers import GatewayConsumer

websocket_urlpatterns = [
    path("ws/gateway/", GatewayConsumer.as_asgi()),
]
