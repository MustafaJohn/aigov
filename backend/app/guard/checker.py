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
        if entity.surface_forms:
            for s in entity.surface_forms:
                if s and s.strip():
                    forms.add(s.strip())

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

                    # First name alone if substantive (Issue 8)
                    if len(firstname) >= 3:
                        forms.add(firstname)

                    # Initial + surname
                    if firstname:
                        forms.add(f"{firstname[0]}. {surname}")
                        forms.add(f"{firstname[0]}.{surname}")
                        forms.add(f"{firstname[0]} {surname}")

                    # If multi-token with middle name (e.g. Amaan Ahmad Siddiqui), add First + Surname and multi-initial
                    if len(words) >= 3:
                        forms.add(f"{firstname} {surname}")
                        forms.add(f"{words[0][0]}. {words[1][0]}. {surname}")
                        forms.add(f"{words[0][0]}.{words[1][0]}. {surname}")

            elif len(words) == 1:
                if len(words[0]) >= 3:
                    forms.add(words[0])

        elif ent_type in ("ORGANISATION", "ORGANIZATION"):
            # Generic statutory corporate suffix stripping (including logistics, partners, services, etc.)
            stem = re.sub(
                r"(?i)\b(?:ltd|limited|llp|plc|inc|corp|corporation|holdings|group|chambers|logistics|partners|services|solicitors|bank|school|academy|college|hospital|clinic|systems)\b\.?$",
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
    def _matches_in_text(text: str, surface_form: str, is_person_entity: bool = False) -> bool:
        """
        Checks if a surface form appears in text on word boundaries.
        Case-sensitive for personal names and word-like surface forms to prevent
        blocking ordinary lowercase English words like 'rose', 'grant', 'will', 'grace', 'hope'.
        """
        clean_form = surface_form.strip()
        if len(clean_form) < 3:
            return False

        # If it's a person entity or single title-cased word, enforce case-sensitivity
        is_title_cased = clean_form[0].isupper() and clean_form.isalpha()
        case_sensitive = is_person_entity or (is_title_cased and len(clean_form.split()) == 1)

        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(rf"(?<!\w){re.escape(clean_form)}(?!\w)", flags)
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

        # 1. Check active entities and their surface forms
        for ent in request.active_entities:
            is_person = (ent.type.upper() == "PERSON")
            surface_forms = cls.get_surface_forms(ent)

            for form in surface_forms:
                if cls._matches_in_text(sanitized_doc, form, is_person_entity=is_person):
                    leaked_in_doc.append(f"{ent.type}: '{form}' (alias of '{ent.text}')")

                if cls._matches_in_text(sanitized_prompt, form, is_person_entity=is_person):
                    leaked_in_prompt.append(f"{ent.type} in prompt: '{form}' (alias of '{ent.text}')")

        # 2. Defense-in-depth: check document and prompt for raw structured PII directly
        # Ensures that if active_entities is empty, raw unmasked PII is still blocked!
        for p_name, p_info in PATTERNS.items():
            if p_name in ("NI_NUMBER", "SORT_CODE", "EMAIL", "PHONE", "ACCOUNT_NUMBER", "CREDIT_CARD", "DRIVING_LICENCE", "PASSPORT"):
                regex = p_info["regex"]
                for m in regex.finditer(sanitized_doc):
                    val = m.group(1) if m.groups() and m.group(1) else m.group()
                    leaked_in_doc.append(f"Document contains unmasked {p_info['label']}: '{val}'")
                for m in regex.finditer(sanitized_prompt):
                    val = m.group(1) if m.groups() and m.group(1) else m.group()
                    leaked_in_prompt.append(f"Prompt contains unmasked {p_info['label']}: '{val}'")

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
