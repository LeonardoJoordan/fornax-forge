"""Limites de saída independentes da geometria lógica dos documentos."""
from dataclasses import dataclass
import math
import sys
from core.i18n import tr


def available_memory_bytes():
    """Consulta somente memória disponível; ausência da API mantém o orçamento."""
    try:
        if sys.platform.startswith('linux'):
            with open('/proc/meminfo', encoding='ascii') as source:
                for line in source:
                    if line.startswith('MemAvailable:'):
                        return int(line.split()[1]) * 1024
        elif sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes
            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD),
                            *[(name, ctypes.c_ulonglong) for name in
                              ('total', 'available', 'total_page', 'available_page',
                               'total_virtual', 'available_virtual', 'extended')]]
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.available)
    except (OSError, ValueError, AttributeError, IndexError):
        pass
    return None

PIXEL_LIMITS = (40, 80, 150, 300, 600)
LEGACY_PIXEL_LIMITS = {12: 40, 20: 40, 36: 40, 72: 80}
EXPORT_DPI = 300
MAX_RASTER_SIDE = 32760


@dataclass(frozen=True)
class ExportPerformance:
    megapixels: int = 150
    dpi: int = EXPORT_DPI

    def __post_init__(self):
        if type(self.megapixels) is not int or self.megapixels not in PIXEL_LIMITS:
            raise ValueError('Limite de pixels inválido.')
        if type(self.dpi) is not int or self.dpi != EXPORT_DPI:
            raise ValueError('Resolução de saída inválida.')

    @property
    def memory_budget(self):
        # Orçamento para buffers da geração, não promessa de consumo total.
        return {40: 768, 80: 1024, 150: 2048,
                300: 4096, 600: 8192}[self.megapixels] * 1024**2

    def dimensions(self, width_mm, height_mm):
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not math.isfinite(v) or v <= 0 for v in (width_mm, height_mm)):
            raise ValueError(tr('As dimensões físicas devem ser positivas.'))
        return tuple(max(1, round(v * self.dpi / 25.4)) for v in (width_mm, height_mm))

    def buffer_budget(self):
        available = available_memory_bytes()
        return min(self.memory_budget, int(available * .7)) if available is not None else self.memory_budget

    def validate(self, width, height, *, buffers=2):
        if any(type(v) is not int or v <= 0 for v in (width, height)):
            raise ValueError(tr('As dimensões da imagem devem ser inteiras e positivas.'))
        pixels = width * height
        if max(width, height) > MAX_RASTER_SIDE:
            raise ValueError(tr('A saída prevista tem {w} × {h} pixels e excede o limite técnico de {side} pixels por lado. Aumentar o limite de exportação não remove esse limite técnico. Use Ladrilhos.').format(
                w=width, h=height, side=MAX_RASTER_SIDE))
        if pixels > self.megapixels * 1_000_000:
            raise ValueError(tr('O programa está configurado para até {limit} MP por imagem. Esta saída exige {mp:.1f} MP ({w} × {h} pixels).').format(
                mp=pixels / 1_000_000, w=width, h=height,
                limit=self.megapixels) + '\n\n' + performance_guidance())
        required, budget = pixels * 4 * buffers, self.buffer_budget()
        if required > budget:
            raise MemoryError(generation_memory_message(required, budget))
        return width, height


PROFILES = {
    'balanced': ExportPerformance(40),
    'expanded': ExportPerformance(80),
    'large': ExportPerformance(150, 300),
    'high': ExportPerformance(300),
    'maximum': ExportPerformance(600),
}


def load_performance(settings=None):
    if settings is None:
        from core.settings import get_app_settings
        settings = get_app_settings()
    profile = settings.value('performance/profile', 'large')
    if profile == 'economy':
        return PROFILES['balanced']
    if profile in PROFILES:
        return PROFILES[profile]
    if profile != 'custom':
        return PROFILES['large']
    try:
        # Preferências antigas de DPI são ignoradas, preservando o limite escolhido.
        limit = int(settings.value('performance/megapixels', 150))
        return ExportPerformance(LEGACY_PIXEL_LIMITS.get(limit, limit))
    except (ValueError, TypeError, OverflowError):
        return PROFILES['large']


def performance_guidance():
    return tr('Verifique a memória disponível. Se houver memória suficiente, aumente o limite em Configurações → Limite de exportação, até 600 MP, ou divida a saída em Ladrilhos. Aumentar o limite não aumenta a memória livre do computador.')


def generation_memory_message(required, budget):
    return tr('Não há capacidade de memória suficiente para esta geração: são necessários cerca de {required:.0f} MB para os buffers, mas o orçamento atual permite {budget:.0f} MB.').format(
        required=required / 1_000_000, budget=budget / 1_000_000) + '\n\n' + performance_guidance()


def allocation_failure_message():
    return tr('Não foi possível reservar memória para a geração. A memória disponível pode ter mudado durante o processo.') + '\n\n' + performance_guidance()


def set_physical_density(image, width_mm, height_mm):
    """Densidade após a pintura: não altera as métricas lógicas do texto."""
    image.setDotsPerMeterX(max(1, round(image.width() * 1000 / width_mm)))
    image.setDotsPerMeterY(max(1, round(image.height() * 1000 / height_mm)))
