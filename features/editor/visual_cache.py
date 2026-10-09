"""Resultados visuais reutilizáveis, limitados à memória da sessão do editor."""
from collections import OrderedDict
from hashlib import sha256
import json
from pathlib import Path

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from core.i18n import current_locale


class _PixelCache:
    def __init__(self, limit):
        self.limit = limit
        self.entries = OrderedDict()
        self.retained_bytes = 0

    def get(self, key):
        entry = self.entries.get(key)
        if entry is not None:
            self.entries.move_to_end(key)
            return entry[0]
        return None

    def put(self, key, value, size):
        if size > self.limit:
            return
        old = self.entries.pop(key, None)
        if old is not None:
            self.retained_bytes -= old[1]
        while self.entries and (self.retained_bytes + size > self.limit or len(self.entries) >= 4096):
            _, (_, removed_size) = self.entries.popitem(last=False)
            self.retained_bytes -= removed_size
        self.entries[key] = value, size
        self.retained_bytes += size

    def clear(self):
        self.entries.clear()
        self.retained_bytes = 0


class EditorVisualCache:
    def __init__(self, proxy_bytes=64 * 1024 * 1024, preview_bytes=16 * 1024 * 1024):
        self.proxies = _PixelCache(proxy_bytes)
        self.previews = _PixelCache(preview_bytes)

    def clear(self):
        self.proxies.clear()
        self.previews.clear()

    def proxy(self, path=None, *, data=None):
        from .canvas_items import _load_proxy_pixmap, _load_proxy_pixmap_bytes
        path = str(path) if path is not None else None
        if data is not None:
            key = 'asset', sha256(data).digest()
        elif path:
            try:
                # O conteúdo, não apenas nome/data/tamanho, identifica a imagem.
                key = 'file', str(Path(path).resolve()), sha256(Path(path).read_bytes()).digest()
            except OSError:
                return _load_proxy_pixmap(path)
        else:
            key = 'empty',
        value = self.proxies.get(key)
        if value is None:
            value = _load_proxy_pixmap_bytes(data) if data is not None else _load_proxy_pixmap(path)
            pixmap = value[0]
            if not pixmap.isNull():
                self.proxies.put(key, value, pixmap.width() * pixmap.height() * pixmap.depth() // 8)
        # A cópia implícita evita modificar os pixels guardados no cache.
        return QPixmap(value[0]), *value[1:]

    def card_preview(self, template, asset_provider, render):
        references = {entry['path'] for collection in ('images', 'signatures')
                      for entry in template.get(collection, []) if entry.get('path')}
        if template.get('background_path'):
            references.add(template['background_path'])
        assets, fingerprints = {}, []
        for reference in sorted(references):
            try:
                payload = bytes(asset_provider(reference))
            except Exception:
                payload = None
            assets[reference] = payload
            fingerprints.append((reference, sha256(payload).hexdigest() if payload is not None else None))
        key = sha256(json.dumps(
            [template, fingerprints, QApplication.font().key(), current_locale()],
            sort_keys=True, ensure_ascii=False, separators=(',', ':'),
        ).encode('utf-8')).digest()
        cached = self.previews.get(key)
        if cached is not None:
            return QImage(cached)

        def snapshot_asset(reference):
            if reference not in assets:
                return asset_provider(reference)
            if assets[reference] is None:
                raise FileNotFoundError(reference)
            return assets[reference]

        image = render(snapshot_asset)
        if not image.isNull():
            self.previews.put(key, QImage(image), image.sizeInBytes())
        return image
