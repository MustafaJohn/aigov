from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class Span(BaseModel):
    start: int
    end: int
    source_ref: Optional[str] = None

class Block(BaseModel):
    id: str
    type: str = "paragraph"  # paragraph, heading, table, cell, comment, tracked_insertion, tracked_deletion, etc.
    text: str
    visibility: str = "visible"  # visible, hidden, deleted, metadata, non_printing
    locator: Dict[str, Any] = Field(default_factory=dict)
    spans: List[Span] = Field(default_factory=list)
    confidence: float = 1.0
    parent_id: Optional[str] = None
    order: int = 0

class MetadataItem(BaseModel):
    key: str
    value: str
    source: str = "document_properties"

class ParseReport(BaseModel):
    status: str  # READY, READY_WITH_WARNINGS, BLOCKED
    summary: str
    pages_or_sheets: int = 1
    total_blocks: int = 0
    warnings: List[str] = Field(default_factory=list)
    hidden_items_count: int = 0
    gate_reason: Optional[str] = None

class SourceInfo(BaseModel):
    format: str  # docx, xlsx, pdf, txt
    filename: str
    size_bytes: int
    sha256: str
    pages_or_sheets: int = 1

class DocumentIR(BaseModel):
    doc_id: str
    source: SourceInfo
    metadata: List[MetadataItem] = Field(default_factory=list)
    blocks: List[Block] = Field(default_factory=list)
    report: ParseReport

class DetectedEntity(BaseModel):
    id: str
    block_id: str
    start: int
    end: int
    text: str
    type: str  # PERSON, ORGANISATION, or a key of detector.patterns.PATTERNS (NI_NUMBER, REFERENCE, ...)
    placeholder: str
    confidence: float = 1.0
    is_active: bool = True  # Lawyer can toggle inclusion
    canonical_id: Optional[str] = None
    surface_forms: List[str] = Field(default_factory=list)
    tier: str = "confident"  # confident, uncertain, manual

class DetectionResult(BaseModel):
    doc_id: str
    entities: List[DetectedEntity] = Field(default_factory=list)
    total_entities: int = 0
    entities_by_type: Dict[str, int] = Field(default_factory=dict)

class OutboundCheckRequest(BaseModel):
    doc_id: str
    protected_text: str
    active_entities: List[DetectedEntity]
    user_prompt: str

class OutboundCheckResponse(BaseModel):
    passed: bool                                                   # False = hard block
    leaked_items: List[str] = Field(default_factory=list)
    prompt_leaks: List[str] = Field(default_factory=list)
    review_items: List[str] = Field(default_factory=list)          # need the lawyer's acknowledgement, not a block
    explanation: str

class SummarizeRequest(BaseModel):
    provider: str  # openai, anthropic, gemini
    api_key: str
    model: Optional[str] = None
    protected_text: str
    instructions: Optional[str] = "Provide a concise legal summary of the following document."
    active_entities: List[DetectedEntity] = Field(default_factory=list)
    acknowledged_review_items: bool = False    # lawyer has confirmed the guard's review items are not personal details

class SummarizeResponse(BaseModel):
    success: bool
    summary: str
    provider: str
    model: str
    inbound_warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None
