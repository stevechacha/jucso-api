import logging
import mimetypes
import os
import re
import uuid
from typing import BinaryIO

from django.conf import settings

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx"}
MAX_UPLOAD_BYTES = getattr(settings, "FILE_UPLOAD_MAX_MEMORY_SIZE", 5 * 1024 * 1024)


class StorageError(Exception):
    pass


class SupabaseStorage:
    """Upload and sign URLs via Supabase Storage (service role)."""

    def __init__(self) -> None:
        self.url = getattr(settings, "SUPABASE_URL", "").rstrip("/")
        self.key = getattr(settings, "SUPABASE_SERVICE_ROLE_KEY", "")
        self.bucket = getattr(settings, "SUPABASE_STORAGE_BUCKET", "jucso-uploads")
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.key and self.bucket)

    def _get_client(self):
        if self._client is None:
            if not self.enabled:
                raise StorageError("Supabase storage is not configured.")
            from supabase import create_client

            self._client = create_client(self.url, self.key)
        return self._client

    def _safe_filename(self, original_name: str) -> str:
        base = os.path.basename(original_name or "upload")
        stem, ext = os.path.splitext(base)
        ext = ext.lower() if ext else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise StorageError(f"File type not allowed. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", stem).strip("-") or "file"
        return f"{slug}-{uuid.uuid4().hex[:8]}{ext}"

    def upload(self, *, folder: str, original_name: str, file_obj: BinaryIO, content_type: str | None = None) -> str:
        data = file_obj.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise StorageError(f"File exceeds maximum size of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

        filename = self._safe_filename(original_name)
        path = f"{folder.strip('/')}/{filename}"
        mime = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        client = self._get_client()
        bucket = client.storage.from_(self.bucket)
        bucket.upload(
            path,
            data,
            file_options={"content-type": mime, "upsert": "false"},
        )
        logger.info("Uploaded %s to Supabase bucket %s", path, self.bucket)
        return path

    def public_url(self, path: str) -> str | None:
        if not path or not self.enabled:
            return None
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{path}"

    def signed_url(self, path: str, expires_in: int | None = None) -> str | None:
        if not path:
            return None
        if not self.enabled:
            return None
        ttl = expires_in or getattr(settings, "SUPABASE_SIGNED_URL_TTL", 3600)
        client = self._get_client()
        result = client.storage.from_(self.bucket).create_signed_url(path, ttl)
        if isinstance(result, dict):
            return result.get("signedURL") or result.get("signedUrl")
        return getattr(result, "signed_url", None) or getattr(result, "signedURL", None)

    def download_url(self, path: str, *, public: bool = False) -> str | None:
        if public:
            return self.public_url(path)
        return self.signed_url(path)


_storage: SupabaseStorage | None = None


def get_storage() -> SupabaseStorage:
    global _storage
    if _storage is None:
        _storage = SupabaseStorage()
    return _storage
