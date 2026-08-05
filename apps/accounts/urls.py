from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.views import (
    CurrentUserView,
    EmployeeViewSet,
    LoginHistoryViewSet,
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetView,
)

app_name = "accounts"

router = DefaultRouter()
router.register("employees", EmployeeViewSet, basename="employee")
router.register("login-history", LoginHistoryViewSet, basename="login-history")

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", CurrentUserView.as_view(), name="me"),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("password/reset/", PasswordResetView.as_view(), name="password-reset"),
    path("", include(router.urls)),
]
