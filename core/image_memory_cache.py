"""Cache LRU de QImages, compartilhado somente dentro de um pipeline."""
from collections import OrderedDict
from threading import RLock

from PySide6.QtGui import QImage

DEFAULT_IMAGE_CACHE_BYTES = 256 * 1024 * 1024


class ImageMemoryCache:
    def __init__(self, max_bytes=DEFAULT_IMAGE_CACHE_BYTES, *, _pool=None):
        self._pool = _pool if _pool is not None else {
            "images": OrderedDict(), "bytes": 0, "limit": max_bytes, "lock": RLock(),
        }

    def fork(self):
        return ImageMemoryCache(_pool=self._pool)

    @property
    def retained_bytes(self):
        with self._pool["lock"]:
            return self._pool["bytes"]

    def get(self, key, default=None):
        pool = self._pool
        with pool["lock"]:
            entry = pool["images"].get(key)
            if entry is None:
                return default
            pool["images"].move_to_end(key)
            # Compartilha pixels implicitamente; escrita posterior desanexa.
            return QImage(entry)

    def __setitem__(self, key, value):
        pool = self._pool
        size = value.sizeInBytes()
        with pool["lock"]:
            old = pool["images"].pop(key, None)
            if old is not None:
                pool["bytes"] -= old.sizeInBytes()
            if size > pool["limit"]:
                return  # Pode ser desenhada, mas não retida pelo cache.
            while pool["images"] and (pool["bytes"] + size > pool["limit"] or len(pool["images"]) >= 4096):
                _, evicted = pool["images"].popitem(last=False)
                pool["bytes"] -= evicted.sizeInBytes()
            pool["images"][key] = QImage(value)
            pool["bytes"] += size
