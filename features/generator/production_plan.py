"""Planejamento compartilhado entre a prévia e a geração de folhas."""

from dataclasses import dataclass
from typing import Any, Sequence
from PySide6.QtGui import QPageLayout

from .imposition import SheetAssembler


@dataclass(frozen=True)
class ImpositionPlan:
    assembler: SheetAssembler
    pages: tuple[tuple[Any, ...], ...]
    sheets: tuple["PhysicalSheet", ...] = ()
    duplex: bool = False

    @property
    def capacity(self) -> int:
        return self.assembler.capacity


@dataclass(frozen=True)
class PhysicalSheet:
    number: int
    front: tuple[Any | None, ...]
    back: tuple[Any | None, ...] | None = None


def _standard_a4_back_slots(front_slots, cols, rows, orientation):
    """Espelha a malha física, preservando conteúdo e rotação de cada item."""
    back = [None] * (cols * rows)
    for row in range(rows):
        for col in range(cols):
            source = row * cols + col
            if orientation == QPageLayout.Orientation.Landscape:
                # A página lógica foi girada sobre a folha A4 alimentada de pé.
                target = (rows - 1 - row) * cols + col
            else:
                target = row * cols + (cols - 1 - col)
            back[target] = front_slots[source]
    return tuple(back)


def build_imposition_plan(items: Sequence[Any], settings: dict) -> ImpositionPlan:
    """Divide uma sequência na mesma malha física usada para montar as folhas."""
    duplex = bool(settings.get("duplex", False))
    assembler = SheetAssembler(
        settings.get("target_w_mm", 100),
        settings.get("target_h_mm", 150),
        settings.get("sheet_w_mm", 210.0),
        settings.get("sheet_h_mm", 297.0),
        settings.get("crop_marks", True),
        settings.get("bleed_margin", False),
        auto_rotate=True,
    )
    if assembler.capacity <= 0:
        return ImpositionPlan(assembler, (), (), duplex)

    pages = tuple(
        tuple(items[start:start + assembler.capacity])
        for start in range(0, len(items), assembler.capacity)
    )
    sheets = []
    for index, page in enumerate(pages):
        front = (
            tuple(page) + (None,) * (assembler.capacity - len(page))
            if duplex else tuple(page)
        )
        back = (
            _standard_a4_back_slots(
                front, assembler.cols, assembler.rows, assembler.orientation
            )
            if duplex else None
        )
        sheets.append(PhysicalSheet(index + 1, front, back))
    return ImpositionPlan(assembler, pages, tuple(sheets), duplex)
