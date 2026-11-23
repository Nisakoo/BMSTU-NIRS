import asyncio
from typing import Any

from smeshariki_ai.speech.config import CephS3Config
from smeshariki_ai.speech.errors import SpeechObjectStoreError
from smeshariki_ai.speech.objects import AudioObjectStore, ObjectInfo


class CephS3AudioObjectStore(AudioObjectStore):
    """S3-compatible Ceph RGW client; all calls run outside the event loop."""

    def __init__(
        self,
        config: CephS3Config,
        *,
        client: Any | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._bucket = config.bucket

    async def startup(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    async def put(self, key: str, data: bytes, *, content_type: str) -> ObjectInfo:
        return await asyncio.to_thread(
            self._put_sync,
            key,
            data,
            content_type,
        )

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get_sync, key)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete_sync, key)

    def _client_or_create(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.config import Config
        except ImportError as error:
            raise SpeechObjectStoreError("Ceph client is unavailable.") from error
        self._client = boto3.client(
            "s3",
            endpoint_url=self._config.endpoint,
            aws_access_key_id=self._config.access_key,
            aws_secret_access_key=self._config.secret_key.get_secret_value(),
            region_name=self._config.region,
            config=Config(s3={"addressing_style": "path"}),
        )
        return self._client

    def _ensure_bucket_sync(self) -> None:
        client = self._client_or_create()
        try:
            client.head_bucket(Bucket=self._bucket)
            return
        except Exception as error:
            if not _is_not_found(error):
                raise SpeechObjectStoreError("Ceph bucket check failed.") from error
        try:
            client.create_bucket(Bucket=self._bucket)
        except Exception as error:
            raise SpeechObjectStoreError("Ceph bucket creation failed.") from error

    def _put_sync(self, key: str, data: bytes, content_type: str) -> ObjectInfo:
        try:
            response = self._client_or_create().put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except Exception as error:
            raise SpeechObjectStoreError("Ceph object upload failed.") from error
        etag = str(response.get("ETag", "")).strip('"')
        return ObjectInfo(size=len(data), etag=etag)

    def _get_sync(self, key: str) -> bytes:
        try:
            response = self._client_or_create().get_object(
                Bucket=self._bucket,
                Key=key,
            )
            return response["Body"].read()
        except Exception as error:
            raise SpeechObjectStoreError("Ceph object download failed.") from error

    def _delete_sync(self, key: str) -> None:
        try:
            self._client_or_create().delete_object(Bucket=self._bucket, Key=key)
        except Exception as error:
            if _is_not_found(error):
                return
            raise SpeechObjectStoreError("Ceph object deletion failed.") from error


def _is_not_found(error: Exception) -> bool:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return False
    code = response.get("Error", {}).get("Code")
    return code in {"404", "NoSuchKey", "NotFound"}
