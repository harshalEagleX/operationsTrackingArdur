"""File serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.files.models import FileContext, StoredFile


class StoredFileSerializer(serializers.ModelSerializer):
    download_url = serializers.CharField(read_only=True)
    thumbnail_url = serializers.CharField(read_only=True)
    size_display = serializers.CharField(read_only=True)
    is_image = serializers.BooleanField(read_only=True)

    class Meta:
        model = StoredFile
        fields = [
            "id", "uuid", "original_name", "mime_type", "size_bytes",
            "size_display", "context", "scan_status", "is_image",
            "download_url", "thumbnail_url", "created_at",
        ]
        # Everything is read-only: files are created by upload, never by JSON.
        read_only_fields = fields


class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    context = serializers.ChoiceField(
        choices=FileContext.choices, default=FileContext.MISC
    )

    def validate_context(self, value: str) -> str:
        # Exports are produced by the server; nobody uploads into that context.
        if value == FileContext.EXPORT:
            raise serializers.ValidationError("Files cannot be uploaded as exports.")
        return value
