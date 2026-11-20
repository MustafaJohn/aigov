"""
DOCX parser: walks the WordprocessingML XML directly so that nothing a lawyer cannot see
on the page is silently dropped.

Why not python-docx's paragraph.text: it only reads runs that are direct children of the
paragraph, so text inside a tracked insertion (w:ins) and deleted text (w:delText) never
appear, and hidden runs (w:vanish) are merged into visible text with no flag. For a
confidentiality gate every one of those is a place a name can hide.

Block.visibility stays within the three values the review screen understands:
  visible    body text the reader sees (tracked insertions are on the page, so they are in it)
  hidden     anything in the file that is not on the page
  metadata   document properties
Block.type carries the specific kind, which the review screen shows as a badge:
  paragraph, heading, table, textbox, tracked_insertion, tracked_deletion, hidden_text,
  comment, header_footer, footnote, endnote, metadata
"""
import io
import re
from typing import List, Tuple, Optional, Iterable

import docx
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from lxml import etree

from app.models import Block, MetadataItem

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS
NSMAP = {"w": W_NS}

RT_COMMENTS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
RT_CUSTOM_PROPS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"


# --------------------------------------------------------------------------------------
# Run-level text extraction
# --------------------------------------------------------------------------------------

def _run_text(r: etree._Element, deleted: bool = False) -> str:
    """Text of one w:r, honouring tabs and breaks. Deleted runs hold w:delText instead of w:t."""
    parts: List[str] = []
    for child in r:
        tag = etree.QName(child).localname
        if tag == ("delText" if deleted else "t"):
            parts.append(child.text or "")
        elif tag == "tab":
            parts.append("\t")
        elif tag in ("br", "cr"):
            parts.append("\n")
        elif tag == "sym":
            parts.append("?")
    return "".join(parts)


def _is_hidden_run(r: etree._Element) -> bool:
    rpr = r.find(W + "rPr")
    if rpr is None:
        return False
    v = rpr.find(W + "vanish")
    if v is None:
        return False
    val = v.get(W + "val")
    return val not in ("0", "false")


class _ParaParts:
    """Text of one paragraph split by how it reaches the page."""
    def __init__(self) -> None:
        self.visible: List[str] = []
        self.inserted: List[Tuple[str, Optional[str]]] = []   # (text, author)
        self.deleted: List[Tuple[str, Optional[str]]] = []
        self.hidden: List[str] = []
        self.footnote_refs: List[str] = []


def _walk_paragraph(p: etree._Element, parts: _ParaParts, in_ins: Optional[str] = None, in_del: Optional[str] = None) -> None:
    """
    Depth-first over a w:p. Text boxes (w:txbxContent) are skipped here and handled as their
    own blocks so a name inside a floating box is reported where it lives.
    """
    for child in p:
        tag = etree.QName(child).localname
        if tag == "r":
            if in_del is not None:
                txt = _run_text(child, deleted=True)
                if txt:
                    parts.deleted.append((txt, in_del))
                continue
            txt = _run_text(child)
            for ref in child.findall(W + "footnoteReference") + child.findall(W + "endnoteReference"):
                parts.footnote_refs.append(ref.get(W + "id", ""))
            if not txt:
                continue
            if _is_hidden_run(child):
                parts.hidden.append(txt)
            elif in_ins is not None:
                parts.inserted.append((txt, in_ins))
                parts.visible.append(txt)   # an insertion is on the page
            else:
                parts.visible.append(txt)
        elif tag == "ins":
            _walk_paragraph(child, parts, in_ins=child.get(W + "author") or "unknown", in_del=in_del)
        elif tag == "del":
            _walk_paragraph(child, parts, in_ins=in_ins, in_del=child.get(W + "author") or "unknown")
        elif tag in ("hyperlink", "smartTag", "sdt", "sdtContent", "fldSimple", "customXml", "moveTo", "moveFrom"):
            # containers that wrap runs; moveFrom is text moved away (treat like a deletion)
            if tag == "moveFrom":
                _walk_paragraph(child, parts, in_ins=in_ins, in_del=child.get(W + "author") or "moved")
            else:
                _walk_paragraph(child, parts, in_ins=in_ins, in_del=in_del)
        elif tag in ("pict", "drawing", "object"):
            # text boxes handled separately; skip to avoid double counting
            continue
        # rPr, pPr, bookmarks, proofErr etc. carry no text


def _para_style(p: etree._Element) -> str:
    ppr = p.find(W + "pPr")
    if ppr is None:
        return "Normal"
    ps = ppr.find(W + "pStyle")
    return (ps.get(W + "val") if ps is not None else "Normal") or "Normal"


def _iter_body_paragraphs(root: etree._Element) -> Iterable[Tuple[etree._Element, dict]]:
    """
    Every w:p under the given root in document order, with a locator describing where it sits
    (body, table cell, nested table). Paragraphs inside text boxes are excluded here.
    """
    for p in root.iter(W + "p"):
        # skip paragraphs that live inside a text box; they get their own pass
        anc = p.getparent()
        in_txbx = False
        loc: dict = {}
        while anc is not None:
            lt = etree.QName(anc).localname
            if lt == "txbxContent":
                in_txbx = True
                break
            if lt == "tc" and "cell" not in loc:
                tc = anc
                tr = tc.getparent()
                tbl = tr.getparent() if tr is not None else None
                if tr is not None:
                    loc["row"] = list(tr.getparent()).index(tr) if tr.getparent() is not None else 0
                    loc["cell"] = list(tr).index(tc)
                if tbl is not None:
                    loc["table"] = True
            anc = anc.getparent()
        if in_txbx or loc.get("table"):
            continue
        yield p, loc


# --------------------------------------------------------------------------------------
# Parts: comments, footnotes/endnotes, headers/footers, properties
# --------------------------------------------------------------------------------------

def _related_part_xml(part, reltype: str) -> List[Tuple[str, etree._Element]]:
    out = []
    for rel in part.rels.values():
        if rel.reltype == reltype and not rel.is_external:
            try:
                out.append((str(rel.target_part.partname), etree.fromstring(rel.target_part.blob)))
            except Exception:
                continue
    return out


def _element_text(el: etree._Element) -> str:
    """All visible-and-deleted text under an element, paragraph by paragraph."""
    paras = []
    for p in el.iter(W + "p"):
        parts = _ParaParts()
        _walk_paragraph(p, parts)
        txt = "".join(parts.visible).strip()
        if txt:
            paras.append(txt)
    return "\n".join(paras)


# --------------------------------------------------------------------------------------
# Main entry
# --------------------------------------------------------------------------------------

def parse_docx(content: bytes) -> Tuple[List[Block], List[MetadataItem], List[str], int]:
    blocks: List[Block] = []
    metadata: List[MetadataItem] = []
    warnings: List[str] = []
    order = 0
    counts = {"tracked_insertion": 0, "tracked_deletion": 0, "hidden_text": 0, "comment": 0,
              "header_footer": 0, "footnote": 0, "endnote": 0, "textbox": 0, "metadata": 0}

    doc = docx.Document(io.BytesIO(content))
    body = doc.element.body

    def add(b_type: str, text: str, visibility: str, locator: dict, bid: str, confidence: float = 1.0) -> None:
        nonlocal order
        text = text.strip()
        if not text:
            return
        blocks.append(Block(id=bid, type=b_type, text=text, visibility=visibility,
                            locator=locator, confidence=confidence, order=order))
        order += 1
        if b_type in counts:
            counts[b_type] += 1

    # ---- 1. Core properties (every field, not just author/title) --------------------------
    cp = doc.core_properties
    core_fields = [
        ("Author", cp.author), ("Last Modified By", cp.last_modified_by), ("Title", cp.title),
        ("Subject", cp.subject), ("Keywords", cp.keywords), ("Comments", cp.comments),
        ("Category", cp.category), ("Identifier", cp.identifier), ("Content Status", cp.content_status),
        ("Created", cp.created.isoformat() if cp.created else None),
        ("Modified", cp.modified.isoformat() if cp.modified else None),
        ("Revision", str(cp.revision) if cp.revision else None),
    ]
    for key, val in core_fields:
        if val:
            metadata.append(MetadataItem(key=key, value=str(val), source="core_properties"))
            if key not in ("Created", "Modified", "Revision"):
                add("metadata", f"{key}: {val}", "metadata", {"part": "docProps/core.xml", "key": key}, f"docx_meta_{key.lower().replace(' ', '_')}")

    # ---- 2. Custom properties (docProps/custom.xml) --------------------------------------
    for partname, root in _related_part_xml(doc.part.package, RT_CUSTOM_PROPS):
        for prop in root:
            name = prop.get("name") or "custom"
            val = "".join(prop.itertext()).strip()
            if val:
                metadata.append(MetadataItem(key=f"Custom: {name}", value=val, source="custom_properties"))
                add("metadata", f"{name}: {val}", "metadata", {"part": partname, "key": name}, f"docx_custom_{re.sub(r'[^a-z0-9]+', '_', name.lower())}")

    # ---- 3. Body paragraphs: visible, inserted, deleted, hidden ---------------------------
    p_idx = 0
    for p, loc in _iter_body_paragraphs(body):
        parts = _ParaParts()
        _walk_paragraph(p, parts)
        style = _para_style(p)
        b_type = "table" if loc.get("table") else ("heading" if style.lower().startswith("heading") else "paragraph")
        locator = {"paragraph": p_idx, "style": style, **{k: v for k, v in loc.items() if k != "table"}}

        add(b_type, "".join(parts.visible), "visible", locator, f"docx_p_{p_idx}")
        for i, (txt, author) in enumerate(parts.inserted):
            add("tracked_insertion", txt, "hidden", {**locator, "author": author}, f"docx_p_{p_idx}_ins_{i}")
        for i, (txt, author) in enumerate(parts.deleted):
            add("tracked_deletion", txt, "hidden", {**locator, "author": author}, f"docx_p_{p_idx}_del_{i}")
        for i, txt in enumerate(parts.hidden):
            add("hidden_text", txt, "hidden", locator, f"docx_p_{p_idx}_hid_{i}")
        p_idx += 1

    # ---- 3b. Tables: one block per row (cells joined with " | "), nested tables included ----
    for t_idx, tbl in enumerate(body.iter(W + "tbl")):
        rows = [tr for tr in tbl if etree.QName(tr).localname == "tr"]
        for r_idx, tr in enumerate(rows):
            cell_texts: List[str] = []
            ins_list: List[Tuple[str, Optional[str]]] = []
            del_list: List[Tuple[str, Optional[str]]] = []
            hid_list: List[str] = []
            for tc in (c for c in tr if etree.QName(c).localname == "tc"):
                paras = []
                for p in tc.iter(W + "p"):
                    # paragraphs of a nested table are reported with that table; skip here.
                    # Compare with the NEAREST table only: every paragraph in a nested table also has
                    # the outer table as an ancestor, so checking all ancestors skipped nested text in
                    # both passes and it was never screened or sent.
                    if next(p.iterancestors(W + "tbl"), None) is not tbl:
                        continue
                    parts = _ParaParts(); _walk_paragraph(p, parts)
                    ptxt = "".join(parts.visible).strip()
                    if ptxt:
                        paras.append(ptxt)
                    ins_list += parts.inserted; del_list += parts.deleted; hid_list += parts.hidden
                ctxt = " ".join(paras).strip()
                if ctxt:
                    cell_texts.append(ctxt)
            locator = {"table": t_idx, "row": r_idx}
            add("table", " | ".join(cell_texts), "visible", locator, f"docx_tbl_{t_idx}_r_{r_idx}")
            for i, (txt, author) in enumerate(ins_list):
                add("tracked_insertion", txt, "hidden", {**locator, "author": author}, f"docx_tbl_{t_idx}_r_{r_idx}_ins_{i}")
            for i, (txt, author) in enumerate(del_list):
                add("tracked_deletion", txt, "hidden", {**locator, "author": author}, f"docx_tbl_{t_idx}_r_{r_idx}_del_{i}")
            for i, txt in enumerate(hid_list):
                add("hidden_text", txt, "hidden", locator, f"docx_tbl_{t_idx}_r_{r_idx}_hid_{i}")

    # ---- 4. Text boxes anywhere in the body ------------------------------------------------
    for t_idx, txbx in enumerate(body.iter(W + "txbxContent")):
        txt = _element_text(txbx)
        add("textbox", txt, "visible", {"textbox": t_idx}, f"docx_txbx_{t_idx}")
        # also count deletions/hidden inside the box
        for p in txbx.iter(W + "p"):
            parts = _ParaParts(); _walk_paragraph(p, parts)
            for i, (d_txt, author) in enumerate(parts.deleted):
                add("tracked_deletion", d_txt, "hidden", {"textbox": t_idx, "author": author}, f"docx_txbx_{t_idx}_del_{i}")
            for i, h_txt in enumerate(parts.hidden):
                add("hidden_text", h_txt, "hidden", {"textbox": t_idx}, f"docx_txbx_{t_idx}_hid_{i}")

    # ---- 5. Headers and footers, every variant of every section ---------------------------
    for s_idx, section in enumerate(doc.sections):
        for kind, hf in (("header", section.header), ("footer", section.footer),
                         ("first_page_header", section.first_page_header), ("first_page_footer", section.first_page_footer),
                         ("even_page_header", section.even_page_header), ("even_page_footer", section.even_page_footer)):
            try:
                if hf.is_linked_to_previous and s_idx > 0:
                    continue
                txt = _element_text(hf._element)
            except Exception:
                continue
            add("header_footer", txt, "hidden", {"section": s_idx, "kind": kind}, f"docx_{kind}_{s_idx}")

    # ---- 6. Footnotes and endnotes ----------------------------------------------------------
    for reltype, label in ((RT.FOOTNOTES, "footnote"), (RT.ENDNOTES, "endnote")):
        for partname, root in _related_part_xml(doc.part, reltype):
            for note in root:
                if note.get(W + "type") in ("separator", "continuationSeparator"):
                    continue
                nid = note.get(W + "id", "?")
                txt = _element_text(note)
                add(label, txt, "hidden", {"part": partname, "id": nid}, f"docx_{label}_{nid}")

    # ---- 7. Comments ------------------------------------------------------------------------
    for partname, root in _related_part_xml(doc.part, RT_COMMENTS):
        for c in root.findall(W + "comment"):
            cid = c.get(W + "id", "?")
            author = c.get(W + "author") or "unknown"
            txt = _element_text(c)
            add("comment", txt, "hidden", {"part": partname, "id": cid, "author": author, "date": c.get(W + "date")}, f"docx_comment_{cid}")
            if author and author != "unknown":
                metadata.append(MetadataItem(key="Comment Author", value=author, source="comments"))

    # ---- 8. Warnings the lawyer must see ------------------------------------------------------
    counts["metadata"] = len(metadata)
    labels = {
        "tracked_insertion": "tracked insertion(s)", "tracked_deletion": "deleted text block(s) still in the file",
        "hidden_text": "hidden-text run(s)", "comment": "review comment(s)", "header_footer": "header/footer block(s)",
        "footnote": "footnote(s)", "endnote": "endnote(s)", "textbox": "text box(es)", "metadata": "document property value(s)",
    }
    found = [f"{n} {labels[k]}" for k, n in counts.items() if n]
    hidden_count = sum(n for k, n in counts.items() if k != "textbox")
    if found:
        warnings.append("Content not visible on the page was found and will be screened: " + ", ".join(found) + ".")
    if counts["tracked_deletion"] or counts["hidden_text"]:
        warnings.append("Deleted or hidden text remains inside this file. Accept all changes and remove hidden text before sharing the original.")

    return blocks, metadata, warnings, hidden_count
