import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from app.models import (
    DocumentIR,
    DetectionResult,
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

# Enable CORS for Next.js frontend (default on localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document intake failed: {str(e)}")

@app.post("/api/guard/outbound-check", response_model=OutboundCheckResponse)
def outbound_check(request: OutboundCheckRequest):
    return GuardEngine.check_outbound(request)

@app.post("/api/llm/summarize", response_model=SummarizeResponse)
async def summarize(request: SummarizeRequest):
    return await execute_llm_summary(request)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
