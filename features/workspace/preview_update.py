"""Compartilha leituras apenas durante uma atualização síncrona da prévia."""
from functools import wraps


def preview_update(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        if getattr(self, "_preview_update_cache", None) is not None:
            return method(self, *args, **kwargs)
        self._preview_update_cache = {}
        try:
            return method(self, *args, **kwargs)
        finally:
            # Não retém dados pessoais/snapshots entre eventos ou sessões.
            self._preview_update_cache = None
    return wrapped
