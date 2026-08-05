from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.settings_app.views import AppSettingViewSet

app_name = "settings_app"

router = DefaultRouter()
router.register("", AppSettingViewSet, basename="setting")

urlpatterns = [path("", include(router.urls))]
