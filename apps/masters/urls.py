from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.masters.views import (
    ClientCodeViewSet,
    MasterBundleView,
    ProjectViewSet,
    ShiftViewSet,
    WorkTypeViewSet,
)

app_name = "masters"

router = DefaultRouter()
router.register("worktypes", WorkTypeViewSet, basename="worktype")
router.register("projects", ProjectViewSet, basename="project")
router.register("clientcodes", ClientCodeViewSet, basename="clientcode")
router.register("shifts", ShiftViewSet, basename="shift")

urlpatterns = [
    path("bundle/", MasterBundleView.as_view(), name="bundle"),
    path("", include(router.urls)),
]
