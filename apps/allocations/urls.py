from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.allocations.views import AllocationViewSet, OrderHistoryViewSet

app_name = "allocations"

router = DefaultRouter()
router.register("history", OrderHistoryViewSet, basename="order-history")
router.register("", AllocationViewSet, basename="allocation")

urlpatterns = [path("", include(router.urls))]
