"""Page views.

Thin by design: render a shell, hand it the bootstrap context, and let the
JavaScript fetch its data from /api/v1/. No queryset ever reaches a template.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import TemplateView

from pages.context import base_context


class BasePage(LoginRequiredMixin, TemplateView):
    """Every page except login requires a session."""

    login_url = "/login/"
    page_title = "OpsTracking"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(base_context(self.request, page_title=self.page_title))
        return context


class LoginPage(TemplateView):
    """GET /login/ — the only unauthenticated page."""

    template_name = "login.html"

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(_home_for(request.user))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            base_context(
                self.request,
                page_title="Sign in",
                reason=self.request.GET.get("reason", ""),
                next_url=self.request.GET.get("next", ""),
            )
        )
        return context


class SignupPage(TemplateView):
    """GET /signup/ — registration page."""

    template_name = "signup.html"

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(_home_for(request.user))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            base_context(
                self.request,
                page_title="Sign Up",
            )
        )
        return context


class HomeRedirect(LoginRequiredMixin, TemplateView):
    """GET / — send people to the right dashboard for their role."""

    login_url = "/login/"

    def get(self, request, *args, **kwargs):
        return HttpResponseRedirect(_home_for(request.user))


class DashboardPage(BasePage):
    """Supervisor and admin dashboard."""

    template_name = "dashboard.html"
    page_title = "Dashboard"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_supervisor:
            return redirect(reverse("pages:userdashboard"))
        return super().dispatch(request, *args, **kwargs)


class UserDashboardPage(BasePage):
    """The employee's own screen: work timer, breaks, tasks, feedback."""

    template_name = "userdashboard.html"
    page_title = "User Dashboard"

    def get_context_data(self, **kwargs):
        from datetime import date
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["username"] = getattr(user, "name", "") or getattr(user, "emp_id", "") or str(user)
        context["role"] = getattr(user, "role", "employee")
        context["current_date"] = date.today().strftime("%Y-%m-%d")
        context["emp_id"] = getattr(user, "emp_id", "")
        return context


class SettingsPage(BasePage):
    """Application settings. Admin only."""

    template_name = "settings.html"
    page_title = "Settings"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_admin:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["username"] = getattr(user, "name", "") or getattr(user, "emp_id", "") or str(user)
        context["role"] = getattr(user, "role", "admin")
        context["emp_id"] = getattr(user, "emp_id", "")
        return context


class ChatPage(BasePage):
    """Chat — reachable only when FEATURE_CHAT is on.

    Returns 404 rather than a "coming soon" page: an unfinished feature should
    be invisible, not advertised.
    """

    template_name = "chat.html"
    page_title = "Chat"

    def dispatch(self, request, *args, **kwargs):
        if not settings.FEATURE_CHAT:
            raise Http404
        return super().dispatch(request, *args, **kwargs)


def _home_for(user) -> str:
    return reverse("pages:dashboard") if user.is_supervisor else reverse("pages:userdashboard")
