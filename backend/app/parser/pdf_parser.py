"""
PDF parser: page text (layout-aware), local OCR for scanned pages, and everything in the file that
is not body text: annotations of every kind, unapplied redaction marks, form fields and their
dropdown options, embedded attachments, bookmarks and document properties.

Block.visibility stays within visible / hidden / metadata. Block.type carries the kind:
  paragraph, ocr_text, scan_unread, form_field, form_options, annotation, hyperlink,
  redaction_mark, attachment, bookmark, metadata

Fail-safe: a parser cannot set the gate status itself, so a block that must stop the document
carries locator["gate_block_reason"]; intake.py turns any such block into BLOCKED. Used for
scanned pages that could not be read, pages read below OCR_BLOCK_CONFIDENCE, pages beyond the OCR
page limit, and password-protected files.
"""
import io
import logging
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader

from app.models import Block, MetadataItem
from app.parser.ocr import OcrUnavailable, ocr_pdf_pages, ocr_settings

logger = logging.getLogger("aigov.pdf")

SCANNED_TEXT_THRESHOLD = 15         # fewer characters than this in the text layer = treat as a scan
TEXT_ATTACHMENT_EXTS = (".txt", ".csv", ".md", ".json", ".xml", ".eml")
TEXT_ATTACHMENT_MAX_BYTES = 20_000

# Annotation subtypes whose text is printed on the page itself
ON_PAGE_SUBTYPES = {"/FreeText", "/Stamp"}
SKIP_SUBTYPES = {"/Popup", "/Widget"}   # popups duplicate their parent; widgets are form fields


def _s(v: Any) -> str:
    try:
        v = v.get_object()
    except Exception:
        pass
    if v is None:
        return ""
    return str(v).strip()


def _text_in_rect(page, rect: List[float]) -> str:
    """Text drawn inside a rectangle, used to show what an unapplied redaction mark is covering."""
    x0, y0, x1, y1 = (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
    lo_x, hi_x, lo_y, hi_y = min(x0, x1), max(x0, x1), min(y0, y1) - 2, max(y0, y1) + 2
    hits: List[str] = []

    def visitor(text, cm, tm, font_dict, font_size):
        if not text or not text.strip():
            return
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        if lo_x - 2 <= x <= hi_x and lo_y <= y <= hi_y:
            hits.append(text.strip())

    try:
        page.extract_text(visitor_text=visitor)
    except Exception:
        return ""
    return " ".join(hits).strip()


def _walk_outline(items, depth: int = 0, out: Optional[List[str]] = None) -> List[str]:
    out = out if out is not None else []
    for it in items or []:
        if isinstance(it, list):
            _walk_outline(it, depth + 1, out)
        else:
            title = getattr(it, "title", None) or (it.get("/Title") if hasattr(it, "get") else None)
            if title and str(title).strip():
                out.append(str(title).strip())
    return out


def parse_pdf(content: bytes) -> Tuple[List[Block], List[MetadataItem], List[str], int]:
    blocks: List[Block] = []
    metadata: List[MetadataItem] = []
    warnings: List[str] = []
    order = 0
    counts: Dict[str, int] = {"annotation": 0, "hyperlink": 0, "redaction_mark": 0, "form_field": 0,
                              "form_options": 0, "attachment": 0, "bookmark": 0, "metadata": 0}

    def add(b_type: str, text: str, visibility: str, locator: dict, bid: str, confidence: float = 1.0) -> None:
        nonlocal order
        text = (text or "").strip()
        if not text:
            return
        blocks.append(Block(id=bid, type=b_type, text=text, visibility=visibility, locator=locator,
                            confidence=confidence, order=order))
        order += 1
        if b_type in counts:
            counts[b_type] += 1

    reader = PdfReader(io.BytesIO(content))

    # ---- 0. Encryption ----------------------------------------------------------------------------
    if reader.is_encrypted:
        try:
            ok = reader.decrypt("")
        except Exception:
            ok = 0
        if not ok:
            add("scan_unread", "[This PDF is password-protected and cannot be read]", "visible",
                {"gate_block_reason": "The PDF is password-protected. Remove the password and upload it again."},
                "pdf_encrypted", confidence=0.0)
            return blocks, metadata, warnings, 0

    # ---- 1. Document properties (Info dictionary and XMP) ------------------------------------------
    try:
        info = reader.metadata or {}
        for k, v in info.items():
            val = _s(v)
            if val and not val.startswith("D:"):      # skip raw PDF dates
                key = k.lstrip("/")
                metadata.append(MetadataItem(key=key, value=val, source="pdf_info"))
                if key not in ("Producer", "Creator", "Trapped"):
                    add("metadata", f"{key}: {val}", "metadata", {"part": "info", "key": key}, f"pdf_meta_{key.lower()}")
    except Exception:
        logger.debug("PDF info dictionary unreadable", exc_info=True)
    try:
        xmp = reader.xmp_metadata
        if xmp is not None:
            for label, val in (("XMP creator", ", ".join(xmp.dc_creator or [])),
                               ("XMP title", " ".join((xmp.dc_title or {}).values())),
                               ("XMP description", " ".join((xmp.dc_description or {}).values()))):
                if val and val.strip() and not any(val.strip() in b.text for b in blocks):
                    metadata.append(MetadataItem(key=label, value=val.strip(), source="pdf_xmp"))
                    add("metadata", f"{label}: {val.strip()}", "metadata", {"part": "xmp", "key": label},
                        f"pdf_{label.lower().replace(' ', '_')}")
    except Exception:
        logger.debug("XMP metadata unreadable", exc_info=True)

    # ---- 2. Form fields: values of every type, plus dropdown options -------------------------------
    try:
        fields = reader.get_fields() or {}
    except Exception:
        fields = {}
    for name, fld in fields.items():
        ftype = _s(fld.get("/FT"))
        value = fld.get("/V")
        tooltip = _s(fld.get("/TU"))
        label = tooltip or name
        if ftype == "/Btn":
            v = _s(value)
            if v and v not in ("/Off", "Off"):
                add("form_field", f"[{label}]: checked ({v.lstrip('/')})", "visible", {"field": name, "kind": "checkbox"},
                    f"pdf_field_{name}")
        elif value is not None:
            if isinstance(value, list):
                v = ", ".join(_s(x) for x in value)
            else:
                v = _s(value)
            add("form_field", f"[{label}]: {v}", "visible", {"field": name, "kind": ftype.lstrip('/') or 'field'},
                f"pdf_field_{name}")
        opts = fld.get("/Opt")
        if opts:
            try:
                flat = []
                for o in opts:
                    o = o.get_object() if hasattr(o, "get_object") else o
                    flat.append(_s(o[1] if isinstance(o, list) and len(o) > 1 else o))
                add("form_options", f"[{label}] options: {', '.join(x for x in flat if x)}", "hidden",
                    {"field": name, "kind": "options"}, f"pdf_field_{name}_opts")
            except Exception:
                pass

    # ---- 3. Attachments -----------------------------------------------------------------------------
    unscreened_attachments: List[str] = []
    try:
        attachments = reader.attachments or {}
    except Exception:
        attachments = {}
    for a_idx, (fname, payloads) in enumerate(attachments.items()):
        data = payloads[0] if payloads else b""
        text = f"Attached file: {fname} ({len(data)} bytes)"
        if fname.lower().endswith(TEXT_ATTACHMENT_EXTS) and len(data) <= TEXT_ATTACHMENT_MAX_BYTES:
            try:
                text += "\n" + data.decode("utf-8", errors="replace").strip()
            except Exception:
                unscreened_attachments.append(fname)
        else:
            unscreened_attachments.append(fname)
        add("attachment", text, "hidden", {"attachment": fname}, f"pdf_attach_{a_idx}")

    # ---- 4. Bookmarks -------------------------------------------------------------------------------
    try:
        for o_idx, title in enumerate(_walk_outline(reader.outline)):
            add("bookmark", f"Bookmark: {title}", "hidden", {"outline": o_idx}, f"pdf_bookmark_{o_idx}")
    except Exception:
        logger.debug("Outline unreadable", exc_info=True)

    # ---- 5. Pages: text layer, annotations, scan detection -------------------------------------------
    total_pages = len(reader.pages)
    scan_pages: List[int] = []
    redactions_with_text = 0

    for p_idx, page in enumerate(reader.pages):
        page_num = p_idx + 1

        # 5a. annotations
        try:
            annots = page.get("/Annots")
            annots = annots.get_object() if annots is not None else []
        except Exception:
            annots = []
        for a_idx, a_ref in enumerate(annots or []):
            try:
                a = a_ref.get_object()
            except Exception:
                continue
            sub = _s(a.get("/Subtype"))
            if sub in SKIP_SUBTYPES:
                continue
            author = _s(a.get("/T"))
            contents = _s(a.get("/Contents"))
            subject = _s(a.get("/Subj"))
            loc = {"page": page_num, "annotation": a_idx, "subtype": sub.lstrip("/"), "author": author or None}
            bid = f"pdf_p{page_num}_annot_{a_idx}"
            if sub == "/Link":
                action = a.get("/A")
                action = action.get_object() if action is not None else {}
                target = _s(action.get("/URI")) or _s(action.get("/F")) if action else ""
                add("hyperlink", f"[Page {page_num}, link] {target}", "hidden", loc, bid)
                continue
            if sub == "/Redact":
                rect = a.get("/Rect")
                under = _text_in_rect(page, list(rect)) if rect is not None else ""
                overlay = _s(a.get("/OverlayText"))
                desc = f"[Page {page_num}, redaction mark NOT applied]"
                if under:
                    desc += f" text still underneath: {under}"
                    redactions_with_text += 1
                if contents:
                    desc += f" | note: {contents}"
                if overlay:
                    desc += f" | overlay: {overlay}"
                add("redaction_mark", desc, "hidden", loc, bid)
                continue
            if sub == "/FileAttachment":
                fs = a.get("/FS")
                fs = fs.get_object() if fs is not None else {}
                fname = _s(fs.get("/UF")) or _s(fs.get("/F")) if fs else ""
                add("attachment", f"[Page {page_num}, attached file] {fname} {contents}".strip(), "hidden", loc, bid)
                continue
            parts = [p for p in (contents, subject if subject and subject != contents else "") if p]
            if not parts:
                continue
            who = f" by {author}" if author else ""
            vis = "visible" if sub in ON_PAGE_SUBTYPES else "hidden"
            add("annotation", f"[Page {page_num}, {sub.lstrip('/').lower()} note{who}] {' | '.join(parts)}", vis, loc, bid)
            if author:
                metadata.append(MetadataItem(key="Annotation author", value=author, source="pdf_annotations"))

        # 5b. text layer (layout mode first, for multi-column court documents)
        page_text = ""
        try:
            page_text = page.extract_text(extraction_mode="layout") or ""
        except Exception:
            page_text = ""
        if not page_text.strip():
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
        page_text = page_text.strip()

        if len(page_text) < SCANNED_TEXT_THRESHOLD:
            try:
                has_images = len(page.images) > 0
            except Exception:
                has_images = True
            if has_images or page_text:
                scan_pages.append(page_num)
            continue

        paras = [p.strip() for p in page_text.split("\n\n") if p.strip()] or \
                [p.strip() for p in page_text.splitlines() if p.strip()] or [page_text]
        for para_idx, para in enumerate(paras):
            add("paragraph", para, "visible", {"page": page_num, "para": para_idx}, f"pdf_p_{page_num}_{para_idx}")

    # ---- 6. OCR for scanned pages ---------------------------------------------------------------------
    s = ocr_settings()
    if scan_pages:
        to_ocr = scan_pages[: s["max_pages"]] if s["enabled"] else []
        over_limit = scan_pages[len(to_ocr):] if s["enabled"] else scan_pages
        unavailable_reason: Optional[str] = None if s["enabled"] else "OCR is switched off on this server"

        results = []
        if to_ocr:
            try:
                results = ocr_pdf_pages(content, to_ocr)
            except OcrUnavailable as e:
                # Expected on Render's free tier; one line, not a traceback per upload
                logger.info("OCR not available on this server (%s); scanned pages will be blocked", str(e).split(".")[0])
                unavailable_reason = "OCR is not installed on this server"
                over_limit = scan_pages

        low_pages: List[str] = []
        blocked_pages: List[str] = []
        for r in results:
            if r.error or not r.text:
                reason = r.error or "no text could be recognised"
                add("scan_unread", f"[Page {r.page_num}: scanned image, not read ({reason})]", "visible",
                    {"page": r.page_num, "ocr": True,
                     "gate_block_reason": f"Page {r.page_num} is a scanned image that could not be read ({reason}). Nothing on it can be screened."},
                    f"pdf_p_{r.page_num}_scan", confidence=0.0)
                continue
            gate: Dict[str, Any] = {"page": r.page_num, "ocr": True, "ocr_confidence": r.confidence,
                                    "ocr_seconds": r.seconds, "ocr_words": r.words}
            pct = f"{round(r.confidence * 100)}%"
            if r.confidence < s["block"]:
                blocked_pages.append(f"{r.page_num} ({pct})")
                gate["gate_block_reason"] = (f"Page {r.page_num} was read by OCR with only {pct} confidence, below the "
                                             f"{round(s['block'] * 100)}% minimum. Upload a clearer scan or a text-based PDF.")
            elif r.confidence < s["warn"]:
                low_pages.append(f"{r.page_num} ({pct})")
            paras = [p.strip() for p in r.text.split("\n\n") if p.strip()] or [r.text]
            for para_idx, para in enumerate(paras):
                loc = dict(gate, para=para_idx)
                if para_idx > 0:
                    loc.pop("gate_block_reason", None)   # one reason per page is enough
                add("ocr_text", para, "visible", loc, f"pdf_p_{r.page_num}_ocr_{para_idx}", confidence=r.confidence)

        if over_limit:
            reason = unavailable_reason or f"over the {s['max_pages']}-page OCR limit"
            pages = ", ".join(str(p) for p in over_limit)
            plural = "s" if len(over_limit) > 1 else ""
            combined = (f"Scanned page{plural} {pages} could not be read ({reason}). "
                        f"Nothing on {'them' if plural else 'it'} can be screened.")
            for i, pnum in enumerate(over_limit):
                loc = {"page": pnum, "ocr": False}
                if i == 0:
                    loc["gate_block_reason"] = combined     # one sentence for the lawyer, not one per page
                add("scan_unread", f"[Page {pnum}: scanned image, not read ({reason})]", "visible", loc,
                    f"pdf_p_{pnum}_scan", confidence=0.0)
        if over_limit and unavailable_reason:
            warnings.append(f"Scanned pages can't be read on this server yet (page(s) {pages}). Upload the original "
                            f"Word or text-based PDF instead, or make the scan searchable on your own computer first "
                            f"(for example with Adobe Acrobat's 'Recognise text') and upload that version.")

        read = [r for r in results if r.text and not r.error]
        if read:
            secs = sum(r.seconds for r in results)
            warnings.append(f"{len(read)} of {total_pages} page(s) are scans and were read by OCR "
                            f"({secs:.1f}s). Check the protected text against the original before sending.")
        if low_pages:
            warnings.append(f"OCR confidence is low on page(s) {', '.join(low_pages)}; names or numbers may be misread "
                            f"and therefore missed. Review those pages carefully.")
        if blocked_pages:
            warnings.append(f"OCR confidence is too low to screen page(s) {', '.join(blocked_pages)}.")

    # ---- 7. Warnings for off-page content -------------------------------------------------------------
    counts["metadata"] = len([m for m in metadata if m.source != "pdf_annotations"])
    labels = {"annotation": "annotation(s) / reviewer note(s)", "hyperlink": "link(s)", "redaction_mark": "unapplied redaction mark(s)",
              "form_field": "form field value(s)", "form_options": "dropdown option list(s)", "attachment": "attached file(s)",
              "bookmark": "bookmark(s)", "metadata": "document property value(s)"}
    found = [f"{n} {labels[k]}" for k, n in counts.items() if n]
    if found:
        warnings.append("Content not visible in the page text was found and will be screened: " + ", ".join(found) + ".")
    if counts["redaction_mark"]:
        warnings.append(f"{counts['redaction_mark']} redaction mark(s) were drawn but never applied"
                        + (f"; {redactions_with_text} still have readable text underneath" if redactions_with_text else "")
                        + ". The covered text is still in this file and has been screened like any other text.")
    if unscreened_attachments:
        warnings.append(f"{len(unscreened_attachments)} attached file(s) inside this PDF could not be screened: "
                        + ", ".join(unscreened_attachments) + ". Remove them before sharing the original.")

    hidden_count = sum(counts.values())
    return blocks, metadata, warnings, hidden_count
