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
    SignupView,
    CheckEmployeeView,
    ForceLogoutView,
)

app_name = "accounts"

router = DefaultRouter()
router.register("employees", EmployeeViewSet, basename="employee")
router.register("login-history", LoginHistoryViewSet, basename="login-history")

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("signup/", SignupView.as_view(), name="signup"),
    path("check-employee/", CheckEmployeeView.as_view(), name="check-employee"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("force-logout/<str:emp_id>/", ForceLogoutView.as_view(), name="force-logout"),
    path("me/", CurrentUserView.as_view(), name="me"),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("password/reset/", PasswordResetView.as_view(), name="password-reset"),
    path("", include(router.urls)),
]
