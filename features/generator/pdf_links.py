from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link


def _pdf_link_rect(page, rect, canvas_width, canvas_height):
    """Converte um QRectF do canvas (origem superior) para coordenadas PDF."""
    if canvas_width <= 0 or canvas_height <= 0:
        raise ValueError("As dimensões do canvas devem ser maiores que zero.")

    page_box = page.mediabox
    page_left = float(page_box.left)
    page_bottom = float(page_box.bottom)
    page_width = float(page_box.width)
    page_height = float(page_box.height)

    scale_x = page_width / float(canvas_width)
    scale_y = page_height / float(canvas_height)

    x0 = page_left + rect.x() * scale_x
    x1 = page_left + (rect.x() + rect.width()) * scale_x

    # O canvas/Qt cresce de cima para baixo. O sistema de coordenadas do PDF
    # cresce de baixo para cima, portanto os limites verticais são invertidos.
    canvas_y0 = rect.y() * scale_y
    canvas_y1 = (rect.y() + rect.height()) * scale_y
    y0 = page_bottom + page_height - canvas_y1
    y1 = page_bottom + page_height - canvas_y0

    return x0, y0, x1, y1


def inject_pdf_links(
    pdf_path, links_by_page, canvas_width, canvas_height, *, memory_only=False,
):
    """Adiciona hyperlinks a um PDF pronto.

    ``links_by_page`` mapeia o índice (base zero) de cada página para uma lista
    de dicionários com ``rect`` (QRectF) e ``url``. O modo comum usa troca
    atômica; ``memory_only`` evita criar uma segunda cópia sensível no disco.
    """
    if not links_by_page:
        return 0

    pdf_path = Path(pdf_path)
    temp_path = pdf_path.with_name(f".{pdf_path.name}.links.tmp")
    inserted_links = 0

    try:
        with pdf_path.open("rb") as source_file:
            reader = PdfReader(source_file)
            writer = PdfWriter()
            writer.clone_document_from_reader(reader)

            for raw_page_index, links in links_by_page.items():
                page_index = int(raw_page_index)
                if page_index < 0 or page_index >= len(writer.pages):
                    continue

                page = writer.pages[page_index]
                for link_data in links:
                    url = str(link_data.get("url", "")).strip()
                    rect = link_data.get("rect")
                    if not url or rect is None:
                        continue

                    writer.add_annotation(
                        page_number=page_index,
                        annotation=Link(
                            rect=_pdf_link_rect(
                                page,
                                rect,
                                canvas_width,
                                canvas_height,
                            ),
                            url=url,
                        ),
                    )
                    inserted_links += 1

            if inserted_links:
                if memory_only:
                    output = BytesIO()
                    writer.write(output)
                    rewritten = output.getvalue()
                else:
                    with temp_path.open("wb") as output_file:
                        writer.write(output_file)

        if inserted_links:
            if memory_only:
                pdf_path.write_bytes(rewritten)
            else:
                temp_path.replace(pdf_path)
        return inserted_links
    finally:
        if temp_path.exists():
            temp_path.unlink()
