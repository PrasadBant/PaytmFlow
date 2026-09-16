"""Real local OCR / document text extraction.

Two genuine, distinct extraction paths, chosen by what the input actually
is - never a guess:

1. Native-text PDF -> PyMuPDF's text layer (already used by
   `app/evidence/extract.py`; no OCR needed, near-perfect text, fast).
2. Image (JPEG/PNG) or a scanned/rasterized PDF page with no usable text
   layer -> real local OCR via Tesseract 5 (open-source, Apache-2.0,
   installed locally - `winget install UB-Mannheim.TesseractOCR`, bound
   through `pytesseract`). This is genuine optical character recognition
   of pixels, not a placeholder string.

Both paths return an `OcrResult` carrying not just concatenated text but
Tesseract's own per-word confidence (mean word confidence, 0-100, scaled
to 0-1) so downstream confidence composition (docai/confidence.py) has a
real, measured signal to build on instead of a fabricated constant.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
import pytesseract
import structlog
from PIL import Image

logger = structlog.get_logger(__name__)

_TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _configure_tesseract_path() -> bool:
    """Points pytesseract at the local Tesseract binary. Returns whether a
    usable binary was found - callers must not assume OCR is available."""
    found = shutil.which("tesseract")
    if found:
        pytesseract.pytesseract.tesseract_cmd = found
        return True
    for candidate in _TESSERACT_CANDIDATES:
        if Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return True
    return False


TESSERACT_AVAILABLE = _configure_tesseract_path()


@dataclass
class OcrLine:
    """One recognized line with its vertical position on the page, so
    downstream extraction can associate a label with a value that
    Tesseract's page-segmentation happened to split into a different
    line/paragraph block despite being visually on the same printed row
    (common for wide, sparse two-column layouts - a label on the left and
    a right-aligned amount can land in separate text blocks once there is
    enough horizontal whitespace between them, especially under
    rotation/blur degradation). This is real bounding-box information
    from Tesseract, not inferred."""

    text: str
    top: int
    bottom: int


@dataclass
class OcrResult:
    text: str
    mean_word_confidence: float  # 0.0-1.0, real Tesseract output, 0.0 if OCR unavailable/no words
    engine: str  # "pymupdf_text_layer" | "tesseract" | "none"
    word_count: int = 0
    degraded_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    lines: list[OcrLine] = field(default_factory=list)


# Real PyMuPDF text-layer coordinates are in PDF points (72/inch); the
# row-band-tolerance constants in app/docai/extraction.py
# (_MIN/MAX_ROW_BAND_TOLERANCE_PX) were tuned against Tesseract's pixel
# coordinates from images rasterized at `rasterize_pdf_to_images`'s own
# 200 DPI default elsewhere in this file. Scaling by that same DPI/72
# factor keeps a native-text PDF's line positions on the same coordinate
# scale those constants actually assume, rather than coincidentally
# relying on a particular document's font size landing in range.
_POINTS_TO_PIXELS = 200 / 72


def _pdf_page_lines(page: pymupdf.Page) -> list[OcrLine]:
    """Real per-line text + vertical position for one native-text PDF
    page, in the SAME shape `ocr_image()` already produces for Tesseract
    (OcrLine.top/bottom) - genuine PyMuPDF layout data (each line's own
    bounding box), not inferred or guessed. This is what lets
    `_find_amount_near_label`'s existing cross-line, same-visual-row
    matching (already built for Tesseract's OCR-segmented two-column
    layouts) also work for a born-digital PDF whose label and value sit
    in separate columns of the SAME printed row - a real, common table
    layout (e.g. "Net Monthly Income" | "133,000" as two side-by-side
    cells) that a same-printed-LINE-only text search can never find,
    since the two cells are different lines in the flat text string even
    though they are the same visual row."""
    lines: list[OcrLine] = []
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            line_text = "".join(span.get("text", "") for span in spans).strip()
            if not line_text:
                continue
            bbox = line.get("bbox")
            if not bbox:
                continue
            _x0, y0, _x1, y1 = bbox
            lines.append(
                OcrLine(
                    text=line_text,
                    top=int(y0 * _POINTS_TO_PIXELS),
                    bottom=int(y1 * _POINTS_TO_PIXELS),
                )
            )
    return lines


def extract_pdf_text_layer(content: bytes) -> OcrResult:
    """Real PyMuPDF text-layer extraction for native-text PDFs. If the PDF
    has no embedded text (i.e. it's a scanned PDF with no text layer),
    returns an empty result so the caller falls back to rasterize+OCR
    rather than silently reporting an empty document as successfully
    processed."""
    try:
        doc = pymupdf.open(stream=content, filetype="pdf")
        pages_text = [page.get_text().strip() for page in doc if page.get_text().strip()]
        combined_lines: list[OcrLine] = []
        for page in doc:
            if page.get_text().strip():
                combined_lines.extend(_pdf_page_lines(page))
    except Exception as exc:
        logger.warning("pdf_text_layer_extraction_failed", error=str(exc))
        return OcrResult(text="", mean_word_confidence=0.0, engine="none", degraded_reason=str(exc))

    text = "\n\n".join(pages_text)
    if not text.strip():
        return OcrResult(
            text="", mean_word_confidence=0.0, engine="none", degraded_reason="no_text_layer"
        )
    return OcrResult(
        text=text,
        # A real text layer is authoritative (not model-predicted), so it is
        # reported at full confidence rather than an invented probability -
        # this is a measured fact about the document (it has a text layer),
        # not a claim about extraction correctness.
        mean_word_confidence=1.0,
        engine="pymupdf_text_layer",
        word_count=len(text.split()),
        lines=combined_lines,
    )


def rasterize_pdf_to_images(content: bytes, dpi: int = 200) -> list[Image.Image]:
    """Renders every page of a PDF to a PIL image, for the scanned-PDF OCR
    fallback path."""
    doc = pymupdf.open(stream=content, filetype="pdf")
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        import io

        images.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
    return images


def ocr_image(pil_image: Image.Image) -> OcrResult:
    """Runs real local Tesseract OCR on a single image and returns text
    plus Tesseract's own measured mean word confidence. Never fabricates a
    confidence value - if Tesseract finds zero words, confidence is 0.0
    and that is reported honestly."""
    if not TESSERACT_AVAILABLE:
        return OcrResult(
            text="",
            mean_word_confidence=0.0,
            engine="none",
            degraded_reason="tesseract_not_installed",
            warnings=["Local OCR engine (Tesseract) is not installed/found on this machine."],
        )

    try:
        data = pytesseract.image_to_data(pil_image, output_type=pytesseract.Output.DICT)
    except Exception as exc:
        logger.warning("tesseract_ocr_failed", error=str(exc))
        return OcrResult(text="", mean_word_confidence=0.0, engine="none", degraded_reason=str(exc))

    # Group words by their actual printed line (block/paragraph/line),
    # not just concatenate every recognized word into one flat string.
    # A flattened string loses which words were visually on the same row,
    # which breaks any downstream "label X is followed by value Y"
    # extraction whenever OTHER text (e.g. an employer name between a
    # "SALARY CREDIT" label and its amount) sits between them on the page
    # but Tesseract emits it as a later word in reading order - preserving
    # line boundaries lets the extraction layer search within a line
    # instead of relying on token adjacency in a flattened stream.
    lines: dict[tuple, list[tuple[str, float, int, int]]] = {}
    n = len(data.get("text", []))
    for i in range(n):
        word = data["text"][i].strip()
        try:
            conf_f = float(data["conf"][i])
            top_i = int(data["top"][i])
            height_i = int(data["height"][i])
        except (TypeError, ValueError, KeyError):
            continue
        if not word or conf_f < 0:
            continue
        line_key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(line_key, []).append((word, conf_f, top_i, top_i + height_i))

    words = []
    confidences = []
    text_lines = []
    ocr_lines: list[OcrLine] = []
    for line_key in sorted(lines.keys()):
        line_words = lines[line_key]
        line_text = " ".join(w for w, _, _, _ in line_words)
        text_lines.append(line_text)
        tops = [t for _, _, t, _ in line_words]
        bottoms = [b for _, _, _, b in line_words]
        ocr_lines.append(OcrLine(text=line_text, top=min(tops), bottom=max(bottoms)))
        for w, c, _, _ in line_words:
            words.append(w)
            confidences.append(c)

    text = "\n".join(text_lines)
    mean_conf = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
    return OcrResult(
        text=text,
        mean_word_confidence=round(mean_conf, 4),
        engine="tesseract",
        word_count=len(words),
        degraded_reason=None if words else "no_text_detected",
        lines=ocr_lines,
    )


def extract_text(content: bytes, mime_type: str) -> OcrResult:
    """Single entrypoint: picks the correct real extraction path for the
    given document bytes. This replaces the placeholder string previously
    returned for images in `app/evidence/extract.py::extract_text_from_document`."""
    if mime_type == "application/pdf":
        layer_result = extract_pdf_text_layer(content)
        if layer_result.text:
            return layer_result
        # No text layer -> genuinely scanned PDF -> rasterize + real OCR.
        try:
            images = rasterize_pdf_to_images(content)
        except Exception as exc:
            return OcrResult(
                text="", mean_word_confidence=0.0, engine="none", degraded_reason=str(exc)
            )
        if not images:
            return OcrResult(
                text="", mean_word_confidence=0.0, engine="none", degraded_reason="no_pages"
            )
        page_results = [ocr_image(img) for img in images]
        combined_text = "\n\n".join(r.text for r in page_results if r.text)
        confidences = [r.mean_word_confidence for r in page_results if r.word_count > 0]
        combined_lines: list[OcrLine] = []
        for r in page_results:
            combined_lines.extend(r.lines)
        return OcrResult(
            text=combined_text,
            mean_word_confidence=round(sum(confidences) / len(confidences), 4)
            if confidences
            else 0.0,
            engine="tesseract",
            word_count=sum(r.word_count for r in page_results),
            lines=combined_lines,
        )

    if mime_type in ("image/jpeg", "image/png"):
        try:
            import io

            pil_image = Image.open(io.BytesIO(content))
        except Exception as exc:
            return OcrResult(
                text="", mean_word_confidence=0.0, engine="none", degraded_reason=str(exc)
            )
        return ocr_image(pil_image)

    return OcrResult(
        text="", mean_word_confidence=0.0, engine="none", degraded_reason="unsupported_mime_type"
    )
