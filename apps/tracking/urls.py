from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.tracking.views import DashboardSummaryView, MonthlyAttendanceView, TargetViewSet, WorkSessionViewSet

app_name = "tracking"

router = DefaultRouter()
router.register("sessions", WorkSessionViewSet, basename="worksession")
router.register("targets", TargetViewSet, basename="target")

urlpatterns = [
    path("summary/", DashboardSummaryView.as_view(), name="summary"),
    path("attendance-history/", MonthlyAttendanceView.as_view(), name="attendance-history"),
    path("", include(router.urls)),
]
