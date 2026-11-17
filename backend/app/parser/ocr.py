"""
Local OCR for scanned PDF pages.

Rendering: pypdfium2 (pip wheel, bundles PDFium, so no Poppler is needed on the server).
Recognition: Tesseract via pytesseract. Tesseract is a system binary; on Render it comes from the
backend Dockerfile (apt-get install tesseract-ocr). Nothing leaves the server: this is the reason
the brief insists on local OCR.

Every page gets a confidence between 0 and 1: the mean of Tesseract's per-word confidences,
weighted by word length, so a page of long, clean words is not dragged down by stray specks.

Configuration (environment variables, all optional):
  OCR_ENABLED            "true" (default) or "false"
  OCR_MAX_PAGES          pages to OCR per document, default 20 (free-tier CPU and memory)
  OCR_DPI                render resolution, default 300
  OCR_WARN_CONFIDENCE    below this a page is READY_WITH_WARNINGS, default 0.80
  OCR_BLOCK_CONFIDENCE   below this the document is BLOCKED, default 0.60
  OCR_PAGE_TIMEOUT       seconds per page before Tesseract is stopped, default 60
  OMP_THREAD_LIMIT       Tesseract threads, default 1 (see below)
"""
import logging
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("aigov.ocr")

# Tesseract is spawned per page; one OpenMP thread was 3x faster per page in testing (thread start-up
# outweighs the gain on a single page) and suits Render's fractional CPU. The Dockerfile sets it too.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def ocr_settings() -> dict:
    """Read at call time so tests and Render env changes take effect without a code change."""
    return {
        "enabled": os.getenv("OCR_ENABLED", "true").lower() not in ("false", "0", "no"),
        "max_pages": _env_int("OCR_MAX_PAGES", 20),
        "dpi": _env_int("OCR_DPI", 300),
        "warn": _env_float("OCR_WARN_CONFIDENCE", 0.80),
        "block": _env_float("OCR_BLOCK_CONFIDENCE", 0.60),
        "timeout": _env_int("OCR_PAGE_TIMEOUT", 60),
    }


@dataclass
class OcrPage:
    page_num: int
    text: str = ""
    confidence: float = 0.0
    words: int = 0
    seconds: float = 0.0
    error: Optional[str] = None          # set when the page could not be read at all
    lines: List[str] = field(default_factory=list)


class OcrUnavailable(Exception):
    """Raised when rendering or Tesseract is not installed on this server."""


def _check_available() -> None:
    try:
        import pypdfium2  # noqa: F401
        import pytesseract
        pytesseract.get_tesseract_version()
    except Exception as e:  # ImportError, TesseractNotFoundError, OSError
        raise OcrUnavailable(str(e)) from e


def ocr_pdf_pages(content: bytes, page_numbers: List[int]) -> List[OcrPage]:
    """
    OCR the given 1-based page numbers of a PDF. Pages are rendered and recognised one at a time
    and each bitmap is released before the next, so peak memory stays at one page (about 26 MB
    for A4 at 300 dpi in greyscale) on top of the API process.
    """
    _check_available()
    import pypdfium2 as pdfium
    import pytesseract
    from pytesseract import Output

    s = ocr_settings()
    scale = s["dpi"] / 72.0
    results: List[OcrPage] = []
    pdf = pdfium.PdfDocument(content)
    try:
        for pnum in page_numbers:
            started = time.perf_counter()
            res = OcrPage(page_num=pnum)
            try:
                page = pdf[pnum - 1]
                bitmap = page.render(scale=scale, grayscale=True)
                img = bitmap.to_pil()
                data = pytesseract.image_to_data(img, lang="eng", config="--psm 3", output_type=Output.DICT,
                                                 timeout=s["timeout"])
                img.close(); bitmap.close(); page.close()

                # Rebuild text line by line, and the confidence weighted by word length
                lines: dict = {}
                weight = 0
                score = 0.0
                for i, word in enumerate(data["text"]):
                    word = (word or "").strip()
                    try:
                        conf = float(data["conf"][i])
                    except (TypeError, ValueError):
                        conf = -1.0
                    if not word or conf < 0:
                        continue
                    key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                    lines.setdefault(key, []).append(word)
                    weight += len(word)
                    score += conf * len(word)
                    res.words += 1
                ordered = [" ".join(ws) for _, ws in sorted(lines.items())]
                # paragraph breaks where Tesseract changes block or paragraph
                paras: List[str] = []
                last = None
                for key, ws in sorted(lines.items()):
                    para_key = key[:2]
                    if last is not None and para_key != last:
                        paras.append("")
                    paras.append(" ".join(ws))
                    last = para_key
                res.lines = ordered
                res.text = "\n".join(paras).strip()
                res.confidence = round((score / weight) / 100.0, 3) if weight else 0.0
            except RuntimeError as e:          # pytesseract raises RuntimeError on timeout
                res.error = f"OCR timed out after {s['timeout']} seconds"
                logger.warning("OCR timeout on page %s: %s", pnum, e)
            except Exception as e:
                res.error = "OCR failed on this page"
                logger.exception("OCR failure on page %s", pnum)
            res.seconds = round(time.perf_counter() - started, 2)
            results.append(res)
    finally:
        pdf.close()
    return results
