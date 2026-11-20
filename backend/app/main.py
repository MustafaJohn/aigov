import os
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

from app.models import (
    DocumentIR,
    DetectionResult,
    DetectedEntity,
    OutboundCheckRequest,
    OutboundCheckResponse,
    SummarizeRequest,
    SummarizeResponse
)
from app.parser.intake import intake_file
from app.detector.engine import DetectionEngine
from app.guard.checker import GuardEngine
from app.llm.client import execute_llm_summary

app = FastAPI(
    title="LegalTech AI Governance MVP Backend",
    version="0.1.0",
    description="Secure, fail-safe intake, PII detection, outbound guard, and BYOK LLM proxy."
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("aigov.api")

# CORS: only the frontend origin(s) may call this API. Set ALLOWED_ORIGINS on Render as a
# comma-separated list, e.g. "https://aigov-frontend.onrender.com". Localhost is always allowed for dev.
# allow_credentials is off: the API uses no cookies, and "*" with credentials is invalid anyway.
_configured_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
ALLOWED_ORIGINS = _configured_origins + ["http://localhost:3000", "http://127.0.0.1:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

detection_engine = DetectionEngine()

class IntakeResponse(BaseModel):
    ir: DocumentIR
    detection: DetectionResult

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "LegalTech AI Governance Gateway",
        "version": "0.1.0"
    }

@app.post("/api/documents/upload", response_model=IntakeResponse)
async def upload_document(
    file: UploadFile = File(...)
):
    try:
        content = await file.read()
        filename = file.filename or "unknown.txt"
        
        # 1. Parse into standard IR & Gate report
        doc_ir = intake_file(filename, content)

        # 2. If blocked at intake, return immediately with empty entities
        if doc_ir.report.status == "BLOCKED":
            return IntakeResponse(
                ir=doc_ir,
                detection=DetectionResult(doc_id=doc_ir.doc_id, entities=[], total_entities=0)
            )

        # 3. Detect sensitive items
        detection_res = detection_engine.detect(doc_ir)

        return IntakeResponse(
            ir=doc_ir,
            detection=detection_res
        )
    except Exception:
        # Full traceback stays in server logs; the client gets a generic message. The exception text
        # can contain file contents or library internals and must not reach the browser.
        logger.exception("Document intake failed for %s", file.filename)
        raise HTTPException(status_code=500, detail="The document could not be processed. Try another file or format.")

@app.post("/api/guard/outbound-check", response_model=OutboundCheckResponse)
def outbound_check(request: OutboundCheckRequest):
    return GuardEngine.check_outbound(request)

@app.post("/api/llm/summarize", response_model=SummarizeResponse)
async def summarize(request: SummarizeRequest):
    # 1. Use typed active_entities from request
    active_entities: List[DetectedEntity] = request.active_entities

    # 2. Server-side outbound guard on the document text and the instruction. This is the only
    #    screening step: it checks every detected value and its aliases, plus every structured
    #    identifier pattern, in both. (The earlier extra NER pass over the instruction blocked
    #    ordinary instructions such as "Summarise the GDPR and SRA implications".)
    outbound_res = GuardEngine.check_outbound(OutboundCheckRequest(
        doc_id="server_check",
        protected_text=request.protected_text,
        active_entities=active_entities or [],
        user_prompt=request.instructions or ""
    ))

    def blocked(message: str) -> SummarizeResponse:
        return SummarizeResponse(success=False, summary="", provider=request.provider,
                                 model=request.model or "unknown", error=message)

    if not outbound_res.passed:
        found = outbound_res.leaked_items + [f"{p} (in your instruction)" for p in outbound_res.prompt_leaks]
        return blocked(f"{outbound_res.explanation} Still visible: {'; '.join(found[:4])}"
                       + (f" and {len(found) - 4} more." if len(found) > 4 else "."))
    if outbound_res.review_items and not request.acknowledged_review_items:
        return blocked(f"{outbound_res.explanation} Please confirm these are fine to send: {'; '.join(outbound_res.review_items[:4])}"
                       + (f" and {len(outbound_res.review_items) - 4} more." if len(outbound_res.review_items) > 4 else "."))

    # 3. Dispatch to LLM provider
    response = await execute_llm_summary(request)

    # 4. Inbound scan of the AI response: known details and any structured identifier it contains
    if response.success and response.summary:
        response.inbound_warnings = GuardEngine.check_inbound(response.summary, active_entities or [])

    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
