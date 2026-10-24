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

    # Read metadata
    if reader.metadata:
        for k, v in reader.metadata.items():
            if v and isinstance(v, str) and v.strip():
                clean_k = k.replace("/", "")
                metadata.append(MetadataItem(key=clean_k, value=v.strip(), source="pdf_info"))
                hidden_count += 1

    total_pages = len(reader.pages)
    scanned_pages_count = 0

    for p_idx, page in enumerate(reader.pages):
        page_num = p_idx + 1
        page_text = page.extract_text() or ""
        page_text = page_text.strip()

        # Check for potential scanned page (empty or minimal text)
        if len(page_text) < 15:
            scanned_pages_count += 1
            blocks.append(Block(
                id=f"pdf_p_{page_num}_warn",
                type="annotation",
                text=f"[Page {page_num} appears to be a scanned image or empty. Local OCR inspection advised.]",
                visibility="non_printing",
                confidence=0.5,
                locator={"page": page_num, "layer": "scan"},
                order=order
            ))
            order += 1
            continue

        # Split paragraphs by double newlines or lines
        paras = [p.strip() for p in page_text.split("\n\n") if p.strip()]
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
        warnings.append(f"{scanned_pages_count} of {total_pages} pages have low extractable text; verify image scans.")

    return blocks, metadata, warnings, hidden_count
