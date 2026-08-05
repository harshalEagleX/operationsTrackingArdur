from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.breaks.views import BreakTypeListView, BreakViewSet

app_name = "breaks"

router = DefaultRouter()
router.register("", BreakViewSet, basename="break")

urlpatterns = [
    path("types/", BreakTypeListView.as_view(), name="types"),
    path("", include(router.urls)),
]
