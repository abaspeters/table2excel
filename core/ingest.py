"""Getting pages out of a scanned PDF without degrading them.

A PDF made by photographing or scanning pages is just a thin wrapper around
one JPEG per page. That matters more than it sounds.

Rendering such a PDF at a fixed DPI resamples someone else's JPEG twice:
once when the viewer scales it onto the page, once when you rasterise. Pick
too low a DPI and you throw away detail that was really there; too high and
you upscale a small JPEG into a blurry big one and pay to send the extra
pixels.

So: pull the embedded image out at its native resolution when the page is a
single full-page scan, and fall back to rendering only when it isn't.
"""

import io
from pathlib import Path
from typing import List, Optional, Tuple

import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader

from . import preprocess

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}

# Claude downscales anything larger, so sending more pixels costs upload time
# and tokens without improving what the model can read.
MAX_EDGE = 1568

# Below this a scan is too coarse for reliable small-digit transcription.
LOW_DPI_WARNING = 150


class Page:
    def __init__(self, number: int, image: Image.Image, notes: List[str],
                 source_dpi: Optional[float] = None):
        self.number = number
        self.image = image
        self.notes = notes
        self.source_dpi = source_dpi
        self._png: Optional[bytes] = None

    @property
    def png(self) -> bytes:
        if self._png is None:
            self._png = _to_png_bytes(self.image)
        return self._png


def kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    raise ValueError(f"Unsupported file type: {suffix}")


def _downscale(img: Image.Image) -> Image.Image:
    if max(img.size) <= MAX_EDGE:
        return img
    scale = MAX_EDGE / max(img.size)
    return img.resize((int(img.width * scale), int(img.height * scale)),
                      Image.LANCZOS)


def _to_png_bytes(img: Image.Image) -> bytes:
    target = "L" if img.mode == "L" else "RGB"
    buf = io.BytesIO()
    _downscale(img).convert(target).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _embedded_image(reader: PdfReader, index: int):
    """Return the page's dominant embedded image and its effective DPI.

    Only accepts a page whose largest image spans the page in both directions
    — that is the signature of a scan. A page with several small figures is a
    real layout and must be rendered, not cherry-picked.
    """
    page = reader.pages[index]
    try:
        images = list(page.images)
    except Exception:
        return None, None
    if not images:
        return None, None

    best, best_pixels = None, 0
    for item in images:
        try:
            img = item.image
        except Exception:
            continue
        pixels = img.width * img.height
        if pixels > best_pixels:
            best, best_pixels = img, pixels
    if best is None:
        return None, None

    box = page.mediabox
    page_w_pt = float(box.width) or 612.0
    page_h_pt = float(box.height) or 792.0

    dpi_x = best.width / (page_w_pt / 72.0)
    dpi_y = best.height / (page_h_pt / 72.0)
    if not dpi_y:
        return None, None

    # Disagreeing aspect ratios mean this isn't a full-page scan.
    if not 0.8 < dpi_x / dpi_y < 1.25:
        return None, None

    return best, (dpi_x + dpi_y) / 2


def load_pages(path: str, render_dpi: int = 220, clean: bool = True,
               max_pages: Optional[int] = None) -> List[Page]:
    """Load every page as a cleaned image, ready for the vision model."""
    if kind(path) == "image":
        img = Image.open(path)
        notes: List[str] = []
        if clean:
            img, notes = preprocess.prepare(img)
        return [Page(1, img, notes)]

    pages: List[Page] = []
    reader = PdfReader(path)
    total = len(reader.pages)
    n = total if max_pages is None else min(total, max_pages)

    doc = None
    try:
        for i in range(n):
            notes: List[str] = []
            img, dpi = _embedded_image(reader, i)

            if img is not None:
                notes.append(f"native scan, ~{dpi:.0f} dpi")
                if dpi < LOW_DPI_WARNING:
                    notes.append(f"low resolution (<{LOW_DPI_WARNING} dpi) — "
                                 "check digits carefully")
            else:
                if doc is None:
                    doc = pdfium.PdfDocument(path)
                img = doc[i].render(scale=render_dpi / 72).to_pil()
                dpi = float(render_dpi)
                notes.append(f"rendered at {render_dpi} dpi")

            if clean:
                img, clean_notes = preprocess.prepare(img)
                notes.extend(clean_notes)

            pages.append(Page(i + 1, img, notes, source_dpi=dpi))
    finally:
        if doc is not None:
            doc.close()

    return pages


def render_pages(path: str, dpi: int = 150) -> List[Tuple[int, bytes]]:
    """Unprocessed page images, for showing the operator the original."""
    if kind(path) == "image":
        return [(1, _to_png_bytes(Image.open(path).convert("RGB")))]

    doc = pdfium.PdfDocument(path)
    try:
        return [(i + 1, _to_png_bytes(doc[i].render(scale=dpi / 72).to_pil()))
                for i in range(len(doc))]
    finally:
        doc.close()
