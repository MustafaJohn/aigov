"""
End-to-end through FastAPI: upload -> redact every detected span -> summarise (demo key, no network).
Covers the lawyer's IHS case and the instruction false positives.
"""
import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))
from fastapi.testclient import TestClient          # noqa: E402
from app.main import app                           # noqa: E402
from app.models import DocumentIR, DetectionResult  # noqa: E402
from detection_cases import IHS_EMAIL              # noqa: E402
from test_detection_regressions import protected_text  # noqa: E402

client = TestClient(app)


def _upload(text):
    r = client.post("/api/documents/upload", files={"file": ("ihs.txt", text.encode(), "text/plain")})
    assert r.status_code == 200
    body = r.json()
    return DocumentIR(**body["ir"]), DetectionResult(**body["detection"])


def _summarise(ir, det, instructions, ack=False):
    return client.post("/api/llm/summarize", json={
        "provider": "anthropic", "api_key": "demo", "protected_text": protected_text(ir, det),
        "instructions": instructions, "active_entities": [e.model_dump() for e in det.entities],
        "acknowledged_review_items": ack}).json()


def test_lawyer_ihs_document_is_sent():
    ir, det = _upload(IHS_EMAIL)
    res = _summarise(ir, det, "explain the document to me")
    assert res["success"], res["error"]


@pytest.mark.parametrize("instruction", [
    "Summarise the GDPR and SRA implications.",
    "Focus on whether the £250,000 liability cap is enforceable.",
    "Write the summary in the style of a Barclays credit memo.",
    "Explain what [PERSON 1] alleges against [ORG 1] under the Equality Act.",
])
def test_ordinary_instructions_are_not_blocked(instruction):
    ir, det = _upload(IHS_EMAIL)
    assert _summarise(ir, det, instruction)["success"]


def test_instruction_with_client_name_is_blocked_in_plain_english():
    ir, det = _upload(IHS_EMAIL)
    res = _summarise(ir, det, "Is Amara Okonkwo entitled to a refund?")
    assert not res["success"]
    assert "Not sent" in res["error"] and "alias" not in res["error"]


def test_instruction_with_raw_identifier_is_blocked():
    ir, det = _upload(IHS_EMAIL)
    assert not _summarise(ir, det, "Check IHS204518736 against GWF071234567")["success"]
