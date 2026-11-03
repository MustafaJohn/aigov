import re
from typing import List, Set
from app.models import (
    OutboundCheckRequest,
    OutboundCheckResponse,
    DetectedEntity
)
from app.detector.patterns import PATTERNS


class GuardEngine:
    @staticmethod
    def get_surface_forms(entity: DetectedEntity) -> Set[str]:
        """
        Generically and algorithmically derives all surface forms and aliases
        for an entity (no hardcoded names or document values).
        """
        forms: Set[str] = set()
        raw = entity.text.strip()
        if not raw:
            return forms

        forms.add(raw)
        ent_type = entity.type.upper()

        if ent_type == "PERSON":
            # Strip common titles to isolate personal name tokens
            title_pattern = r"^(?:Mr\.?|Mrs\.?|Ms\.?|Miss|Dr\.?|Prof\.?|Lord|Lady|Sir|Master)\s+"
            clean_name = re.sub(title_pattern, "", raw, flags=re.IGNORECASE).strip()
            if clean_name and clean_name != raw:
                forms.add(clean_name)

            words = [w for w in re.split(r"\s+", clean_name) if w.strip(".,")]
            if len(words) >= 2:
                firstname = words[0]
                surname = words[-1]

                # Surname alone if substantive (>= 3 chars)
                if len(surname) >= 3:
                    forms.add(surname)
                    # Common legal honorific + surname combinations
                    for title in ("Mr", "Mr.", "Mrs", "Mrs.", "Ms", "Ms.", "Dr", "Dr."):
                        forms.add(f"{title} {surname}")

                    # Initial + surname
                    if firstname:
                        forms.add(f"{firstname[0]}. {surname}")
                        forms.add(f"{firstname[0]} {surname}")

            elif len(words) == 1:
                if len(words[0]) >= 3:
                    forms.add(words[0])

        elif ent_type in ("ORGANISATION", "ORGANIZATION"):
            # Generic statutory corporate suffix stripping
            stem = re.sub(
                r"(?i)\b(?:ltd|limited|llp|plc|inc|corp|corporation|holdings|group|chambers)\b\.?$",
                "",
                raw
            ).strip()
            if len(stem) >= 3 and stem != raw:
                forms.add(stem)

        elif ent_type in ("SORT_CODE", "ACCOUNT_NUMBER", "NI_NUMBER", "PHONE", "UK_POSTCODE"):
            # Compact form without spaces or hyphens
            compact = re.sub(r"[\s\-\(\)\.]+", "", raw)
            if len(compact) >= 4 and compact != raw:
                forms.add(compact)

        return forms

    @staticmethod
    def _matches_in_text(text: str, surface_form: str) -> bool:
        """
        Checks if a surface form appears in text on word boundaries.
        Prevents false positive substring matches (e.g. 'Vance' inside 'Advance').
        """
        clean_form = surface_form.strip()
        if len(clean_form) < 3:
            return False

        # Escape form and enforce word boundaries
        pattern = re.compile(rf"(?<!\w){re.escape(clean_form)}(?!\w)", re.IGNORECASE)
        return bool(pattern.search(text))

    @classmethod
    def check_outbound(cls, request: OutboundCheckRequest) -> OutboundCheckResponse:
        leaked_in_doc: List[str] = []
        leaked_in_prompt: List[str] = []

        doc_text = request.protected_text
        prompt_text = request.user_prompt

        # Mask existing typed placeholders from doc text so their category names don't trigger false flags
        sanitized_doc = re.sub(r"\[[A-Z_\s0-9]+\]", " ", doc_text)
        sanitized_prompt = re.sub(r"\[[A-Z_\s0-9]+\]", " ", prompt_text)

        for ent in request.active_entities:
            surface_forms = cls.get_surface_forms(ent)

            for form in surface_forms:
                if cls._matches_in_text(sanitized_doc, form):
                    leaked_in_doc.append(f"{ent.type}: '{form}' (alias of '{ent.text}')")

                if cls._matches_in_text(sanitized_prompt, form):
                    leaked_in_prompt.append(f"{ent.type} in prompt: '{form}' (alias of '{ent.text}')")

        # Also check if the prompt contains raw structured PII directly (e.g. NI numbers, sort codes)
        for p_name, p_info in PATTERNS.items():
            if p_name in ("NI_NUMBER", "SORT_CODE", "EMAIL", "PHONE", "ACCOUNT_NUMBER"):
                regex = p_info["regex"]
                for m in regex.finditer(sanitized_prompt):
                    leaked_in_prompt.append(f"Prompt contains raw {p_info['label']}: '{m.group()}'")

        passed = len(leaked_in_doc) == 0 and len(leaked_in_prompt) == 0

        if passed:
            explanation = "Outbound check passed. No unmasked sensitive identifiers or aliases detected in document text or prompt."
        else:
            explanation = "Outbound check FAILED. One or more sensitive details or aliases remain unmasked."

        return OutboundCheckResponse(
            passed=passed,
            leaked_items=sorted(list(set(leaked_in_doc))),
            prompt_leaks=sorted(list(set(leaked_in_prompt))),
            explanation=explanation
        )

    @classmethod
    def check_inbound(cls, summary: str, entities: List[DetectedEntity]) -> List[str]:
        """
        Scans AI output for leaked client entity surface forms and newly introduced PII patterns.
        """
        warnings: List[str] = []
        if not summary:
            return warnings

        # 1. Check for any known entity surface forms leaked back in response
        for ent in entities:
            forms = cls.get_surface_forms(ent)
            for form in forms:
                if cls._matches_in_text(summary, form):
                    warnings.append(f"Notice: Entity detail '{form}' (alias of '{ent.text}') appears in the AI response.")

        # 2. Check for newly introduced structured identifiers (e.g. LLM invented or leaked numbers)
        for p_name, p_info in PATTERNS.items():
            if p_name in ("NI_NUMBER", "SORT_CODE", "CREDIT_CARD", "ACCOUNT_NUMBER", "EMAIL", "PHONE"):
                regex = p_info["regex"]
                for m in regex.finditer(summary):
                    val = m.group()
                    # Only flag if not already an existing placeholder
                    if not re.match(r"^\[[A-Z_\s0-9]+\]$", val):
                        warnings.append(f"Notice: AI response contains an unmasked {p_info['label']}: '{val}'.")

        return sorted(list(set(warnings)))
