from smeshariki_ai.speech.objects import AudioObjectStore, ObjectInfo


class InMemoryAudioObjectStore(AudioObjectStore):
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []

    async def startup(self) -> None:
        return None

    async def put(self, key: str, data: bytes, *, content_type: str) -> ObjectInfo:
        self.objects[key] = (data, content_type)
        return ObjectInfo(size=len(data), etag="memory")

    async def get(self, key: str) -> bytes:
        return self.objects[key][0]

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)
