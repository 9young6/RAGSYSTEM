from __future__ import annotations

import io

from minio import Minio

from app.config import settings


class MinioService:
    def __init__(self) -> None:
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_USE_SSL,
        )
        self.bucket = settings.MINIO_BUCKET

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    @staticmethod
    def get_user_path(user_id: int, path_type: str, filename: str = "") -> str:
        """
        Generate user-specific MinIO path for multi-tenant isolation

        Args:
            user_id: User ID for isolation
            path_type: Type of path ('documents' or 'markdown')
            filename: Optional filename to append

        Returns:
            str: Path like 'user_{id}/documents/{filename}' or 'user_{id}/markdown/{filename}'
        """
        if path_type not in ("documents", "markdown"):
            raise ValueError(f"Invalid path_type: {path_type}. Must be 'documents' or 'markdown'")

        base_path = f"user_{user_id}/{path_type}"
        if filename:
            return f"{base_path}/{filename}"
        return base_path

    def upload_bytes(self, object_name: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        stream = io.BytesIO(content)
        self.client.put_object(
            self.bucket,
            object_name,
            stream,
            length=len(content),
            content_type=content_type,
        )

    def download_bytes(self, object_name: str) -> bytes:
        response = self.client.get_object(self.bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete_object(self, object_name: str) -> None:
        """Delete an object from MinIO"""
        self.client.remove_object(self.bucket, object_name)

    def list_user_objects(self, user_id: int, path_type: str) -> list[str]:
        """
        List all objects for a user in a specific path type

        Args:
            user_id: User ID
            path_type: 'documents' or 'markdown'

        Returns:
            List of object names
        """
        prefix = self.get_user_path(user_id, path_type)
        objects = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
        return [obj.object_name for obj in objects]

