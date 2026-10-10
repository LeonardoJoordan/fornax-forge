"""Orçamentos JSON existentes do contêiner, compartilhados sem Qt."""
import json
import math

MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_JSON_OBJECTS = 100_000


def validate_json_budget(value):
    """Confere dados completos antes da cópia/Qt, sem montar outra string gigante."""
    stack = [(value, 1)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > MAX_JSON_OBJECTS or depth > MAX_JSON_DEPTH:
            raise ValueError('O documento excede o orçamento de elementos/profundidade JSON.')
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise ValueError('Chave JSON inválida.')
            if len(item) > MAX_JSON_OBJECTS-count:
                raise ValueError('O documento excede o orçamento de elementos JSON.')
            stack.extend((entry, depth+1) for entry in item.values())
        elif isinstance(item, list):
            if len(item) > MAX_JSON_OBJECTS-count:
                raise ValueError('O documento excede o orçamento de elementos JSON.')
            stack.extend((entry, depth+1) for entry in item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError('Número JSON não finito.')
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError('Valor não serializável como JSON.')
    length = 1  # Nova linha do documento canônico.
    for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(',', ':')).iterencode(value):
        length += len(chunk.encode('utf-8'))
        if length > MAX_JSON_BYTES:
            raise ValueError('O documento excede o orçamento de bytes JSON.')
