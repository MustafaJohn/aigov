import hashlib
import uuid
from typing import List, Tuple
from app.models import DocumentIR, SourceInfo, ParseReport, Block, MetadataItem
from app.parser.docx_parser import parse_docx
from app.parser.xlsx_parser import parse_xlsx
from app.parser.pdf_parser import parse_pdf
from app.parser.txt_parser import parse_txt

def intake_file(filename: str, content: bytes) -> DocumentIR:
    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    sha256 = hashlib.sha256(content).hexdigest()
    size_bytes = len(content)

    lower_name = filename.lower()
    fmt = "unknown"
    if lower_name.endswith(".docx"):
        fmt = "docx"
    elif lower_name.endswith(".xlsx"):
        fmt = "xlsx"
    elif lower_name.endswith(".pdf"):
        fmt = "pdf"
    elif lower_name.endswith(".txt"):
        fmt = "txt"

    # Enforce basic intake checks (Principle: Fail-safe)
    if fmt == "unknown":
        return DocumentIR(
            doc_id=doc_id,
            source=SourceInfo(format="unknown", filename=filename, size_bytes=size_bytes, sha256=sha256),
            report=ParseReport(
                status="BLOCKED",
                summary="Unsupported file format.",
                gate_reason="Only .docx, .xlsx, .pdf, and .txt files are accepted for safe parsing.",
                total_blocks=0
            )
        )

    if size_bytes == 0:
        return DocumentIR(
            doc_id=doc_id,
            source=SourceInfo(format=fmt, filename=filename, size_bytes=size_bytes, sha256=sha256),
            report=ParseReport(
                status="BLOCKED",
                summary="File is empty.",
                gate_reason="Zero bytes received. Cannot process an empty document.",
                total_blocks=0
            )
        )

    # Size limit check (e.g. 25MB for safety)
    if size_bytes > 25 * 1024 * 1024:
        return DocumentIR(
            doc_id=doc_id,
            source=SourceInfo(format=fmt, filename=filename, size_bytes=size_bytes, sha256=sha256),
            report=ParseReport(
                status="BLOCKED",
                summary="File exceeds size limit.",
                gate_reason="Document is larger than 25MB safety threshold.",
                total_blocks=0
            )
        )

    blocks: List[Block] = []
    metadata: List[MetadataItem] = []
    warnings: List[str] = []
    hidden_count = 0

    try:
        if fmt == "docx":
            blocks, metadata, warnings, hidden_count = parse_docx(content)
        elif fmt == "xlsx":
            blocks, metadata, warnings, hidden_count = parse_xlsx(content)
        elif fmt == "pdf":
            blocks, metadata, warnings, hidden_count = parse_pdf(content)
        elif fmt == "txt":
            blocks, metadata, warnings, hidden_count = parse_txt(content)
    except Exception as e:
        return DocumentIR(
            doc_id=doc_id,
            source=SourceInfo(format=fmt, filename=filename, size_bytes=size_bytes, sha256=sha256),
            report=ParseReport(
                status="BLOCKED",
                summary="Extraction failure.",
                gate_reason=f"Failed to securely parse {fmt.upper()} content: {str(e)}",
                total_blocks=0
            )
        )

    # Determine Gate Outcome: If text blocks extracted, document is READY immediately.
    if len(blocks) == 0:
        status = "BLOCKED"
        gate_reason = "No extractable text or structure found in document."
        summary = "File contained zero readable text blocks."
    else:
        status = "READY"
        gate_reason = None
        summary = f"Document ready: {len(blocks)} blocks extracted."

    return DocumentIR(
        doc_id=doc_id,
        source=SourceInfo(
            format=fmt,
            filename=filename,
            size_bytes=size_bytes,
            sha256=sha256,
            pages_or_sheets=max(1, len({b.locator.get("page", 1) for b in blocks if "page" in b.locator}))
        ),
        metadata=metadata,
        blocks=blocks,
        report=ParseReport(
            status=status,
            summary=summary,
            pages_or_sheets=max(1, len({b.locator.get("page", 1) for b in blocks if "page" in b.locator})),
            total_blocks=len(blocks),
            warnings=warnings,
            hidden_items_count=hidden_count,
            gate_reason=gate_reason
        )
    )
