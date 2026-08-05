from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.reports.views import (
    DashboardMetricsView,
    ReportCatalogueView,
    ReportExportView,
    ReportJobViewSet,
    ReportRunView,
)

app_name = "reports"

router = DefaultRouter()
router.register("jobs", ReportJobViewSet, basename="report-job")

urlpatterns = [
    path("", ReportCatalogueView.as_view(), name="catalogue"),
    path("run/", ReportRunView.as_view(), name="run"),
    path("export/", ReportExportView.as_view(), name="export"),
    path("metrics/", DashboardMetricsView.as_view(), name="metrics"),
    path("", include(router.urls)),
]
