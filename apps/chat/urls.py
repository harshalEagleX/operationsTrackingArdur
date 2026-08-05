"""Chat URLs — NOT WIRED UP.

``opstracking/api_urls.py`` does not include this module. When chat is built,
uncomment the block there and replace the catch-all below with the real
router.
"""

from django.urls import re_path

from apps.chat.views import ChatUnavailableView

app_name = "chat"

urlpatterns = [
    re_path(r"^.*$", ChatUnavailableView.as_view(), name="unavailable"),
]
