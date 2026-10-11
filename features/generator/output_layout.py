"""Escolha de distribuição compartilhada pela configuração, prévia e geração.

O tamanho solicitado nunca é reduzido para caber: uma folha recebe vários itens
quando possível; desenhos maiores são repartidos pelos mesmos planos de ladrilhos.
"""
from copy import deepcopy
from dataclasses import dataclass

from PySide6.QtCore import QRectF

from core.tiling import build_tile_plan, UNITS_PER_MM, TilePlan, reserved_margin_mm, BLEED_MARGIN_MM
from .imposition import SheetAssembler, DPI


@dataclass
class OutputLayout:
    mode: str
    plan: TilePlan | None = None
    assembler: SheetAssembler | None = None
    imposition: dict | None = None


def output_bounds(document):
    """Geometria física, sem carregar fontes, imagens ou renderizadores."""
    if document.get('organogram') is not None:
        from core.organogram import board_bounds
        return board_bounds(document['organogram'])
    from core.model_document import adapt_model_page
    page = adapt_model_page(document) if document.get('pages') else document
    canvas = page.get('canvas_size', {'w': 1000, 'h': 1000})
    return QRectF(0, 0, (page.get('target_w_mm') or canvas['w'] / UNITS_PER_MM) * UNITS_PER_MM,
                  (page.get('target_h_mm') or canvas['h'] / UNITS_PER_MM) * UNITS_PER_MM)


def layout_options(settings, bounds):
    target = settings.get('target_size_mm')
    if target:
        target = (target[0], target[0] * bounds.height() / bounds.width())
    offset = settings.get('offset_mm', (0, 0))
    if settings.get('layout_mode') == 'auto' and not settings.get('positioned'):
        offset = (0, 0)
    return dict(paper=tuple(settings.get('paper', (210, 297))),
                margin_mm=reserved_margin_mm(settings),
                overlap_mm=settings.get('overlap_mm', 0), crop_marks=settings.get('crop_marks', False),
                target_size_mm=target, offset_mm=offset,
                auto_orientation=settings.get('auto_orientation', True))


def resolve_output_layout(settings, bounds, *, repeat=True):
    if not settings.get('enabled', settings.get('tiling', False)):
        return OutputLayout('native')
    options = layout_options(settings, bounds)
    mode = settings.get('mode')
    if mode == 'imposition':
        options['overlap_mm'] = 0
    # Valida medidas, limites e espaço para marcas, inclusive antes da imposição.
    plan = build_tile_plan(bounds, **options)
    target_w = plan.drawing_bounds.width() / UNITS_PER_MM
    target_h = plan.drawing_bounds.height() / UNITS_PER_MM
    if repeat and mode != 'tiles':
        paper = options['paper']
        imp = dict(enabled=True, target_w_mm=target_w, target_h_mm=target_h,
                   sheet_w_mm=paper[0], sheet_h_mm=paper[1], crop_marks=options['crop_marks'],
                   bleed_margin=bool(settings.get('margin_enabled')), margin_mm=options['margin_mm'],
                   offset_mm=options['offset_mm'] if settings.get('positioned') else None,
                   auto_rotate=options['auto_orientation'])
        assembler = SheetAssembler.from_settings(imp)
        if assembler.capacity:
            return OutputLayout('imposition', assembler=assembler, imposition=imp)
        if mode == 'imposition':
            raise ValueError('O item não cabe na folha escolhida. Reduza o tamanho do item, '
                             'aumente a folha ou selecione Ladrilhos.')
    if mode == 'imposition' and len(plan.tiles) > 1:
        raise ValueError('O quadro não cabe em uma folha. Reduza o tamanho ou selecione Ladrilhos.')
    # Organogramas são um desenho único; mesmo quando cabem em uma folha,
    # o plano preserva o papel escolhido sem repetir os cartões da página 1.
    return OutputLayout('tiles', plan=plan)


def effective_settings(document, configuration):
    result = deepcopy(configuration)
    result['dpi'] = DPI
    if result.get('layout_mode') == 'auto':
        layout = resolve_output_layout(result, output_bounds(document), repeat=document.get('organogram') is None)
        result['tiling'] = layout.mode == 'tiles'
        if layout.plan:
            result['offset_mm'] = list(layout.plan.offset_mm)
    return result


def from_legacy_preset(preset, bounds):
    """Migração feita na edição, sem alterar silenciosamente arquivos antigos."""
    if preset.get('output_layout'):
        return deepcopy(preset['output_layout'])
    width = preset.get('w') or bounds.width() / UNITS_PER_MM
    return dict(layout_mode='auto', enabled=bool(preset.get('enabled')), paper_index=4,
                paper=[preset.get('sheet_w', 210), preset.get('sheet_h', 297)], auto_orientation=True,
                target_size_mm=[width, width * bounds.height() / bounds.width()],
                margin_policy='separate', margin_enabled=preset.get('bleed', True),
                margin_value=BLEED_MARGIN_MM, crop_marks=preset.get('crop', True),
                positioned=False, offset_mm=[0, 0], overlap_mm=0, dpi=DPI)
