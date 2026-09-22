"""Criação segura das pastas que recebem cada produção do FORNAX."""

import re
from pathlib import Path

from core.i18n import tr


FORGE_COUNTER_KEY = "generation/lastForgeNumber"
FORGE_FOLDER_PATTERN = "FORNAX - Forja nº {numero}"
_FORGE_NAMES = (
    re.compile(r"^FORNAX - Forja nº ([1-9][0-9]*)$"),
    re.compile(r"^FORNAX - Forge No\. ([1-9][0-9]*)$"),
    re.compile(r"^FORNAX - Forja n\.º ([1-9][0-9]*)$"),
)


def _largest_existing_forge(base_dir: Path) -> int:
    largest = 0
    for entry in base_dir.iterdir():
        if not entry.is_dir():
            continue
        for pattern in _FORGE_NAMES:
            match = pattern.fullmatch(entry.name)
            if match:
                largest = max(largest, int(match.group(1)))
                break
    return largest


def create_forge_output_dir(base_dir, settings):
    """Cria e reserva a próxima pasta da sequência global de Forjas."""
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    try:
        stored = max(0, int(settings.value(FORGE_COUNTER_KEY, 0)))
    except (TypeError, ValueError):
        stored = 0

    number = max(stored, _largest_existing_forge(base_dir)) + 1
    while True:
        # Literal mantido aqui para que o lupdate inclua o padrão no catálogo.
        folder_name = tr("FORNAX - Forja nº {numero}").format(numero=number)
        output_dir = base_dir / folder_name
        try:
            # exist_ok=False transforma a criação na reserva do número e
            # também protege contra duas gerações iniciadas ao mesmo tempo.
            output_dir.mkdir(exist_ok=False)
            break
        except FileExistsError:
            number += 1

    settings.setValue(FORGE_COUNTER_KEY, number)
    settings.sync()
    return output_dir, number
