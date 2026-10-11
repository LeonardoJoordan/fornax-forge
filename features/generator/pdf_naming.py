"""Identificação das páginas sem alterar os pixels ou a ordem da produção."""
from pathlib import Path

from core.i18n import tr
from core.naming_engine import sanitize_filename


def grouped_pdf_name(output_dir):
    # A pasta já contém o número reservado para esta Forja.
    return f"{sanitize_filename(Path(output_dir).name)}.pdf"


def face_labels(base, count):
    if count == 1:
        return (base,)
    if count == 2:
        return (f"{base} — {tr('Frente')}", f"{base} — {tr('Verso')}")
    return tuple(f"{base} — {tr('Página {numero}').format(numero=index + 1)}" for index in range(count))


def sheet_page_labels(slots, face_count):
    indexes = [task[0] + 1 for task in slots if task is not None]
    if not indexes:
        raise ValueError("A folha não possui cartões para identificar.")
    base = tr("Cartão de {inicio} a {fim}").format(inicio=min(indexes), fim=max(indexes))
    return face_labels(base, face_count)
