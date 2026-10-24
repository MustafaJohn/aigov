from typing import List, Tuple
from app.models import Block, MetadataItem

def parse_txt(content: bytes) -> Tuple[List[Block], List[MetadataItem], List[str], int]:
    blocks: List[Block] = []
    metadata: List[MetadataItem] = []
    warnings: List[str] = []
    hidden_count = 0
    order = 0

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
            warnings.append("Document decoded using Latin-1 fallback.")
        except Exception:
            text = content.decode("utf-8", errors="replace")
            warnings.append("Document had non-standard characters replaced.")

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    for idx, p in enumerate(paragraphs):
        blocks.append(Block(
            id=f"txt_b_{idx}",
            type="paragraph",
            text=p,
            visibility="visible",
            locator={"line_block": idx},
            order=order
        ))
        order += 1

    return blocks, metadata, warnings, hidden_count
