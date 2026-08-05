from django.urls import path

from apps.realtime.views import SyncView, TicketView

app_name = "realtime"

urlpatterns = [
    path("ticket/", TicketView.as_view(), name="ticket"),
    path("sync/", SyncView.as_view(), name="sync"),
]
