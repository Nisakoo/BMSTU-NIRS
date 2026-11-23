from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    size: int
    etag: str


class AudioObjectStore(Protocol):
    async def startup(self) -> None: ...

    async def put(self, key: str, data: bytes, *, content_type: str) -> ObjectInfo: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...
