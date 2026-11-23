import io

import pytest

from smeshariki_ai.speech.ceph import CephS3AudioObjectStore
from smeshariki_ai.speech.config import CephS3Config
from smeshariki_ai.speech.errors import SpeechObjectStoreError
from smeshariki_ai.speech.memory_objects import InMemoryAudioObjectStore


class NotFound(Exception):
    response = {"Error": {"Code": "404"}}


class FakeS3:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}
        self.created: list[str] = []
        self.deleted: list[str] = []

    def head_bucket(self, *, Bucket: str) -> None:  # noqa: N803
        if Bucket not in self.buckets:
            raise NotFound()

    def create_bucket(self, *, Bucket: str) -> None:  # noqa: N803
        self.buckets.add(Bucket)
        self.created.append(Bucket)

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str):  # noqa: N803
        self.objects[(Bucket, Key)] = Body
        return {"ETag": '"etag-value"'}

    def get_object(self, *, Bucket: str, Key: str):  # noqa: N803
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, *, Bucket: str, Key: str) -> None:  # noqa: N803
        self.deleted.append(Key)
        self.objects.pop((Bucket, Key), None)


@pytest.mark.asyncio
async def test_ceph_store_creates_bucket_and_round_trips_an_object() -> None:
    client = FakeS3()
    store = CephS3AudioObjectStore(
        CephS3Config(bucket="audio", secret_key="secret"),
        client=client,
    )

    await store.startup()
    info = await store.put("a/b.mp3", b"mp3", content_type="audio/mpeg")

    assert client.created == ["audio"]
    assert info.size == 3
    assert info.etag == "etag-value"
    assert await store.get("a/b.mp3") == b"mp3"
    await store.delete("a/b.mp3")
    assert client.deleted == ["a/b.mp3"]


@pytest.mark.asyncio
async def test_ceph_store_maps_failures_to_safe_error() -> None:
    class Broken:
        def head_bucket(self, **kwargs: object) -> None:
            raise RuntimeError("private endpoint")

    store = CephS3AudioObjectStore(
        CephS3Config(secret_key="secret"),
        client=Broken(),
    )

    with pytest.raises(SpeechObjectStoreError):
        await store.startup()


@pytest.mark.asyncio
async def test_in_memory_object_store_round_trips() -> None:
    store = InMemoryAudioObjectStore()

    info = await store.put("key", b"data", content_type="audio/mpeg")

    assert info.size == 4
    assert await store.get("key") == b"data"
    await store.delete("key")
    assert "key" not in store.objects
    assert store.deleted == ["key"]
