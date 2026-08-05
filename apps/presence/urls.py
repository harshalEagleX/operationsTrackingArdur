from django.urls import path

from apps.presence.views import EmployeePresenceView, MyPresenceView, PresenceRosterView

app_name = "presence"

urlpatterns = [
    path("", PresenceRosterView.as_view(), name="roster"),
    path("me/", MyPresenceView.as_view(), name="me"),
    path("<str:emp_id>/", EmployeePresenceView.as_view(), name="detail"),
]
