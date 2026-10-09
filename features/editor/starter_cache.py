"""Miniaturas LRU por janela; nenhum conteúdo de modelo vai para disco."""
from hashlib import sha256
import json
import weakref

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from core.i18n import current_locale
from core.model_document import adapt_model_page, iter_page_asset_paths
from features.generator.renderer import NativeRenderer
from .visual_cache import _PixelCache


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':')).encode()).digest()


def asset_snapshot(document, provider):
    """Bytes comuns ao cartão ficam só no diálogo, nunca no cache persistente."""
    references = sorted({path for _, _, path in iter_page_asset_paths(document)})
    resolver = NativeRenderer(adapt_model_page(document)) if provider is None else None
    assets = {}
    for reference in references:
        try:
            assets[reference] = bytes(provider(reference) if provider else
                                      resolver._resolve_asset_path(reference).read_bytes())
        except (OSError, KeyError, ValueError):
            assets[reference] = None
    return assets


class StarterPreviewCache(QObject):
    def __init__(self, parent, limit=16 * 1024 * 1024):
        super().__init__(parent)
        self.pixels = _PixelCache(limit)
        self.scope = None
        self.validator = None
        self.revoked = False
        self.dialogs = weakref.WeakSet()
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.check_authorization)
        QApplication.instance().fontDatabaseChanged.connect(self.clear)
        parent.destroyed.connect(self.clear)

    def bind(self, scope, validator=None):
        self.check_authorization()
        if scope != self.scope:
            self.clear()
            self.scope = scope
        self.revoked = False
        self.validator = validator
        if validator:
            self.timer.start()
            if not self.check_authorization():
                raise PermissionError('A autorização do modelo não está mais disponível.')

    def check_authorization(self):
        if self.revoked:
            return False
        if self.validator is not None:
            try:
                valid = self.validator()
            except (OSError, ValueError, RuntimeError):
                valid = False
            if not valid:
                self.clear()
                self.revoked = True
                return False
        return True

    def clear(self):
        self.pixels.clear()
        self.scope = self.validator = None
        if isValid(self.timer):
            self.timer.stop()
        for dialog in tuple(self.dialogs):
            if isValid(dialog):
                dialog._discard_starter_preview()
        self.dialogs.clear()

    def preview(self, document, provider, recipe, render, *, assets=None):
        if not self.check_authorization():
            raise PermissionError('A autorização do modelo não está mais disponível.')
        assets = asset_snapshot(document, provider) if assets is None else assets
        fingerprints = [(path, sha256(data).hexdigest() if data is not None else None)
                        for path, data in sorted(assets.items())]
        key = digest([recipe, fingerprints, QApplication.font().key(), current_locale()])
        cached = self.pixels.get(key)
        if cached is not None:
            return QPixmap(cached)
        def snapshot_provider(reference):
            data = assets[reference]
            if data is None:
                raise FileNotFoundError(reference)
            return data
        # Arquivos legados conservam inclusive o caminho de proxies do renderer.
        pixmap = render(document, snapshot_provider if provider is not None else None)
        if not self.check_authorization():
            raise PermissionError('A autorização do modelo não está mais disponível.')
        if not pixmap.isNull():
            self.pixels.put(key, QPixmap(pixmap), pixmap.width() * pixmap.height() * pixmap.depth() // 8)
        return pixmap


def window_cache(parent):
    cache = getattr(parent, '_starter_preview_cache', None)
    if cache is None:
        cache = StarterPreviewCache(parent)
        parent._starter_preview_cache = cache
    return cache
