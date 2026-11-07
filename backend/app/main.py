import os
import re
import logging
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

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
async def summarize(request: SummarizeRequest, raw_req: Request):
    # 1. Dynamically extract active_entities from JSON payload if provided (schema remains frozen)
    active_entities: List[DetectedEntity] = []
    try:
        body = await raw_req.json()
        raw_ents = body.get("active_entities", [])
        if isinstance(raw_ents, list):
            for item in raw_ents:
                try:
                    active_entities.append(DetectedEntity.model_validate(item))
                except Exception:
                    pass
    except Exception:
        pass

    # 2. Server-side Outbound Guard: check all surface forms & aliases against document and prompt
    if active_entities:
        outbound_res = GuardEngine.check_outbound(OutboundCheckRequest(
            doc_id="server_check",
            protected_text=request.protected_text,
            active_entities=active_entities,
            user_prompt=request.instructions or ""
        ))
        if not outbound_res.passed:
            leaks = outbound_res.leaked_items + outbound_res.prompt_leaks
            return SummarizeResponse(
                success=False,
                summary="",
                provider=request.provider,
                model=request.model or "unknown",
                error=f"Security gate blocked dispatch: {outbound_res.explanation} Details: {', '.join(leaks[:4])}"
            )

    # 3. Defense-in-depth prompt screening: screen lawyer instructions for unmasked sensitive items
    if request.instructions and request.instructions.strip():
        prompt_text = request.instructions.strip()
        prompt_ir = intake_file("prompt.txt", prompt_text.encode("utf-8"))
        prompt_det = detection_engine.detect(prompt_ir)
        unmasked_prompt_ents = [
            e for e in prompt_det.entities
            if not re.match(r"^\[[A-Z_\s0-9]+\]$", e.text)
        ]
        if unmasked_prompt_ents:
            leaked_summary = ", ".join(f"{e.type}: '{e.text}'" for e in unmasked_prompt_ents[:4])
            return SummarizeResponse(
                success=False,
                summary="",
                provider=request.provider,
                model=request.model or "unknown",
                error=f"Security gate blocked dispatch: Lawyer instructions contain unmasked sensitive identifiers ({leaked_summary}). Please use placeholders or remove real details."
            )

    # 4. Dispatch to LLM provider
    response = await execute_llm_summary(request)

    # 5. Inbound scan verification on the AI response
    if response.success and response.summary and active_entities:
        inbound_warnings = GuardEngine.check_inbound(response.summary, active_entities)
        if inbound_warnings:
            warnings_text = "\n\n> [!WARNING] **AI Governance Notice (Inbound Check):**\n> " + "\n> ".join(inbound_warnings)
            response.summary += warnings_text

    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
