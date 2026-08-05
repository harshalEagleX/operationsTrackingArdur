"""Upload and authenticated download.

Downloads never bypass Django. The permission check runs, then the bytes are
streamed — or handed to Apache via X-Sendfile when that module is available,
which keeps the check but hands the transfer to a web server that is better
at it than Python is.
"""

from __future__ import annotations

from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.utils.encoding import escape_uri_path
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from apps.files.models import ScanStatus, StoredFile
from apps.files.serializers import FileUploadSerializer, StoredFileSerializer
from apps.files.services import FileAccessPolicy, FileService
from core.exceptions import NotFoundError, PermissionDeniedError
from core.mixins import EnvelopeMixin
from core.permissions import IsAuthenticatedEmployee
from core.throttling import UploadThrottle


class FileUploadView(EnvelopeMixin, APIView):
    """POST /api/v1/files/ (multipart)

    Step one of the two-step upload: store the bytes, return an id. Step two
    is the owning record referencing that id.

    Binary over the websocket would be the alternative and it is a trap — no
    resumability, no progress events, and a 25 MB frame stalls every other
    subscriber on that consumer.
    """

    permission_classes = [IsAuthenticatedEmployee]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [UploadThrottle]

    def post(self, request):
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        stored = FileService(actor=request.user).store(
            serializer.validated_data["file"],
            context=serializer.validated_data["context"],
        )
        return self.ok(StoredFileSerializer(stored).data, status=201)


class FileDownloadView(APIView):
    """GET /api/v1/files/<uuid>/ — permission-checked download."""

    permission_classes = [IsAuthenticatedEmployee]
    thumbnail = False

    def get(self, request, file_uuid):
        stored = StoredFile.objects.filter(uuid=file_uuid).first()
        if stored is None:
            raise NotFoundError("That file does not exist.")

        if stored.scan_status != ScanStatus.CLEAN:
            raise PermissionDeniedError("That file has not been cleared for download.")

        if not FileAccessPolicy(request.user).can_read(stored):
            # 404 rather than 403: a 403 confirms the file exists, which is
            # itself information the caller has not earned.
            raise NotFoundError("That file does not exist.")

        if self.thumbnail and stored.thumb_path:
            path, disposition = stored.absolute_thumb_path, "inline"
        else:
            path, disposition = stored.absolute_path, "attachment"

        if not path or not path.exists():
            raise NotFoundError("That file is no longer available.")

        response = self._respond(path, stored, disposition)
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, max-age=0, no-store"
        response["Content-Disposition"] = (
            f'{disposition}; filename="{escape_uri_path(stored.original_name)}"'
        )
        return response

    @staticmethod
    def _respond(path, stored, disposition) -> HttpResponse:
        """Hand off to Apache when mod_xsendfile is enabled.

        Django still decides who may read the file; Apache just moves the
        bytes, which frees the worker immediately instead of holding it for
        the length of a 20 MB download.
        """
        if getattr(settings, "USE_X_SENDFILE", False):
            response = HttpResponse(content_type=stored.mime_type)
            response["X-Sendfile"] = str(path)
            return response

        return FileResponse(open(path, "rb"), content_type=stored.mime_type)


class FileThumbnailView(FileDownloadView):
    """GET /api/v1/files/<uuid>/thumb/ — same checks, smaller image."""

    thumbnail = True


class FileDeleteView(EnvelopeMixin, APIView):
    """DELETE /api/v1/files/<uuid>/delete/"""

    permission_classes = [IsAuthenticatedEmployee]

    def delete(self, request, file_uuid):
        stored = StoredFile.objects.filter(uuid=file_uuid).first()
        if stored is None:
            raise NotFoundError("That file does not exist.")

        FileService(actor=request.user).delete(stored)
        return self.ok({"detail": "File removed."})
