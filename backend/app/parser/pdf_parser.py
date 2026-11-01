import io
from typing import List, Tuple
from pypdf import PdfReader
from app.models import Block, MetadataItem

def parse_pdf(content: bytes) -> Tuple[List[Block], List[MetadataItem], List[str], int]:
    blocks: List[Block] = []
    metadata: List[MetadataItem] = []
    warnings: List[str] = []
    hidden_count = 0
    order = 0

    reader = PdfReader(io.BytesIO(content))

    # 1. Read document metadata
    if reader.metadata:
        for k, v in reader.metadata.items():
            if v and isinstance(v, str) and v.strip():
                clean_k = k.replace("/", "")
                metadata.append(MetadataItem(key=clean_k, value=v.strip(), source="pdf_info"))
                hidden_count += 1

    # 2. Extract Form Fields (Crucial for official e-visas, court forms, and government applications)
    try:
        form_fields = reader.get_form_text_fields()
        if form_fields:
            for field_name, field_value in form_fields.items():
                if field_value and str(field_value).strip():
                    field_text = f"[{field_name}]: {str(field_value).strip()}"
                    blocks.append(Block(
                        id=f"pdf_form_{order}",
                        type="form_field",
                        text=field_text,
                        visibility="visible",
                        locator={"field": field_name, "layer": "acroform"},
                        order=order
                    ))
                    order += 1
            warnings.append(f"Extracted {len(form_fields)} interactive form fields from PDF.")
    except Exception:
        # Graceful fallback if form fields cannot be read
        pass

    total_pages = len(reader.pages)
    scanned_pages_count = 0

    # 3. Extract Pages (supports layout mode for multi-column court cases and handles image scans)
    for p_idx, page in enumerate(reader.pages):
        page_num = p_idx + 1

        # Attempt layout-aware extraction first (ideal for multi-column court cases)
        page_text = ""
        try:
            page_text = page.extract_text(extraction_mode="layout") or ""
        except Exception:
            page_text = ""

        # Fallback to standard text extraction
        if not page_text.strip():
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""

        page_text = page_text.strip()

        # Check for annotations (e.g. court stamps, notes, redaction boxes)
        try:
            if page.annotations:
                for a_idx, annot in enumerate(page.annotations):
                    annot_obj = annot.get_object()
                    contents = annot_obj.get("/Contents")
                    if contents and isinstance(contents, str) and contents.strip():
                        blocks.append(Block(
                            id=f"pdf_p_{page_num}_annot_{a_idx}",
                            type="annotation",
                            text=f"[Annotation Page {page_num}]: {contents.strip()}",
                            visibility="visible",
                            locator={"page": page_num, "annotation": a_idx},
                            order=order
                        ))
                        order += 1
        except Exception:
            pass

        # Check if page is an image scan (e.g. birth certificate, e-visa, scanned letter)
        if len(page_text) < 15:
            scanned_pages_count += 1
            has_images = False
            try:
                has_images = len(page.images) > 0
            except Exception:
                has_images = True

            scan_notice = (
                f"[Page {page_num}: Scanned Certificate / Document Image - Low digital text layer. "
                f"Visual document detected ({'images present' if has_images else 'non-digital content'}).]"
            )
            if page_text:
                scan_notice += f" Residual text: {page_text}"

            # Make scanned block visible so the lawyer can see and review the page in the studio
            blocks.append(Block(
                id=f"pdf_p_{page_num}_scan",
                type="annotation",
                text=scan_notice,
                visibility="visible",
                confidence=0.5,
                locator={"page": page_num, "layer": "scanned_image"},
                order=order
            ))
            order += 1
            continue

        # Split into readable paragraphs (preserving court case structure)
        paras = [p.strip() for p in page_text.split("\n\n") if p.strip()]
        if not paras:
            paras = [p.strip() for p in page_text.splitlines() if p.strip()]
        if not paras:
            paras = [page_text]

        for para_idx, para in enumerate(paras):
            blocks.append(Block(
                id=f"pdf_p_{page_num}_{para_idx}",
                type="paragraph",
                text=para,
                visibility="visible",
                locator={"page": page_num, "para": para_idx},
                order=order
            ))
            order += 1

    if scanned_pages_count > 0:
        warnings.append(
            f"{scanned_pages_count} of {total_pages} pages contain scanned images or certificates with low digital text."
        )

    return blocks, metadata, warnings, hidden_count
