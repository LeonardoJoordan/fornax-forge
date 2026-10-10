"""PNG sem perdas: compactação mais leve somente para intermediários do PDF."""
from PySide6.QtGui import QImageWriter


def save_png(image, path, *, intermediate=False):
    if not intermediate:
        return image.save(str(path), "PNG")
    writer = QImageWriter(str(path), b"PNG")
    # Escala do Qt: 0–100, não a escala 0–9 do zlib. Mantém pixels e DPI.
    writer.setCompression(25)
    return writer.write(image)
