from typing import List
from app.models import (
    OutboundCheckRequest,
    OutboundCheckResponse,
    DetectedEntity
)

class GuardEngine:
    @staticmethod
    def check_outbound(request: OutboundCheckRequest) -> OutboundCheckResponse:
        leaked_in_doc: List[str] = []
        leaked_in_prompt: List[str] = []

        protected_text = request.protected_text.lower()
        user_prompt = request.user_prompt.lower()

        for ent in request.active_entities:
            # Skip very short identifiers (1-2 chars) to avoid false positive substring matches
            clean_raw = ent.text.strip().lower()
            if len(clean_raw) < 3:
                continue

            # Check document text
            if clean_raw in protected_text:
                leaked_in_doc.append(f"{ent.type}: '{ent.text}'")

            # Check user prompt
            if clean_raw in user_prompt:
                leaked_in_prompt.append(f"Prompt mentions real detail: '{ent.text}'")

        passed = len(leaked_in_doc) == 0 and len(leaked_in_prompt) == 0

        if passed:
            explanation = "Outbound check passed. Zero unmasked sensitive identifiers detected in document text or prompt."
        else:
            explanation = "Outbound check FAILED. One or more raw sensitive details remain unmasked."

        return OutboundCheckResponse(
            passed=passed,
            leaked_items=list(set(leaked_in_doc)),
            prompt_leaks=list(set(leaked_in_prompt)),
            explanation=explanation
        )

    @staticmethod
    def check_inbound(summary: str, entities: List[DetectedEntity]) -> List[str]:
        # Checks if the LLM output accidentally leaked any unexpected details
        warnings: List[str] = []
        lower_summary = summary.lower()
        for ent in entities:
            clean_raw = ent.text.strip().lower()
            if len(clean_raw) >= 4 and clean_raw in lower_summary:
                warnings.append(f"Notice: Raw value '{ent.text}' appears in the AI response.")
        return warnings
