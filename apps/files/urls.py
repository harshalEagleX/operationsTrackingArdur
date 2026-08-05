from django.urls import path

from apps.files.views import (
    FileDeleteView,
    FileDownloadView,
    FileThumbnailView,
    FileUploadView,
)

app_name = "files"

urlpatterns = [
    path("", FileUploadView.as_view(), name="upload"),
    path("<uuid:file_uuid>/", FileDownloadView.as_view(), name="download"),
    path("<uuid:file_uuid>/thumb/", FileThumbnailView.as_view(), name="thumbnail"),
    path("<uuid:file_uuid>/delete/", FileDeleteView.as_view(), name="delete"),
]
