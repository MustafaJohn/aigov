"""
Outbound and inbound guard.

Outbound (before anything is sent to an AI provider):
  BLOCK   a detected value, or a multi-word form of it ('Mr Aldridge', 'J. Aldridge'), is still
          in the text or the instruction, in its own case or in CAPITALS; or any structured
          identifier (NI number, email, phone, reference number, postcode, date of birth...)
          appears unmasked, whether or not it was detected.
  REVIEW  a single word that is also a person's first name or surname ('Grant', 'Will') is still
          present. It may be the person or an ordinary word at the start of a sentence, so the
          lawyer is asked rather than blocked; dispatch needs their acknowledgement.

Only placeholders this system issues ([PERSON 1], [REF 2] ...) are treated as masked text;
anything else in square brackets is checked like normal text.
"""
from typing import List, Tuple

from app.models import OutboundCheckRequest, OutboundCheckResponse, DetectedEntity
from app.detector.names import is_strong_form, name_in, org_stem, person_forms
from app.detector.patterns import PATTERNS, PLACEHOLDER_REGEX

# Structured patterns the guard checks on raw text. Amounts are excluded: a figure on its own
# identifies no one, and blocking every "£250,000" in an instruction makes the tool unusable.
GUARDED_PATTERNS = [name for name in PATTERNS if name != "MONETARY_AMOUNT"]

_LABELS = {"PERSON": "name", "ORGANISATION": "organisation name"}


def _label(entity_type: str) -> str:
    return _LABELS.get(entity_type, PATTERNS.get(entity_type, {}).get("label", entity_type.replace("_", " ").lower())).lower()


class GuardEngine:
    @staticmethod
    def get_surface_forms(entity: DetectedEntity) -> List[str]:
        forms = {entity.text.strip(), *(s.strip() for s in entity.surface_forms if s and s.strip())}
        t = entity.type.upper()
        if t == "PERSON":
            forms |= person_forms(entity.text)
        elif t in ("ORGANISATION", "ORGANIZATION"):
            forms.add(org_stem(entity.text))
        # Two-letter forms only for acronyms of organisations ('BP'); never a person's two-letter token
        return sorted(f for f in forms if len(f) >= 3 or (len(f) == 2 and f.isupper() and t != "PERSON"))

    @staticmethod
    def _unmask(text: str) -> str:
        return PLACEHOLDER_REGEX.sub(" ", text or "")

    @classmethod
    def _scan(cls, text: str, entities: List[DetectedEntity]) -> Tuple[List[str], List[str]]:
        """Returns (blocking findings, review findings) for one piece of text."""
        block, review = [], []
        for ent in entities:
            for form in cls.get_surface_forms(ent):
                if not name_in(text, form):
                    continue
                item = f"{_label(ent.type)} '{form}'" + (f" (part of '{ent.text}')" if form != ent.text else "")
                strong = ent.type.upper() != "PERSON" or is_strong_form(form, ent.text, text)
                (block if strong else review).append(item)
        for name in GUARDED_PATTERNS:
            p = PATTERNS[name]
            for m in p["regex"].finditer(text):
                g = next((i for i in range(1, (p["regex"].groups or 0) + 1) if m.group(i)), 0)
                value = m.group(g)
                if p.get("validate") and not p["validate"](value):
                    continue
                block.append(f"{p['label'].lower()} '{value}'")
        return sorted(set(block)), sorted(set(review) - set(block))

    @classmethod
    def check_outbound(cls, request: OutboundCheckRequest) -> OutboundCheckResponse:
        entities = request.active_entities or []
        doc_block, doc_review = cls._scan(cls._unmask(request.protected_text), entities)
        prm_block, prm_review = cls._scan(cls._unmask(request.user_prompt), entities)

        passed = not doc_block and not prm_block
        review = [f"In the document: {r}" for r in doc_review] + [f"In your instruction: {r}" for r in prm_review]
        if not passed:
            explanation = ("Not sent. Some details that must be redacted are still visible in what would go to the AI. "
                           "Redact them on the review screen, or remove them from your instruction, then try again.")
        elif review:
            explanation = ("Please check before sending: some single words match a person's first name or surname. "
                           "They may be ordinary words, or they may identify the person.")
        else:
            explanation = "Ready to send. No unredacted personal or confidential details were found."
        return OutboundCheckResponse(passed=passed, leaked_items=doc_block, prompt_leaks=prm_block,
                                     review_items=review, explanation=explanation)

    @classmethod
    def check_inbound(cls, summary: str, entities: List[DetectedEntity]) -> List[str]:
        """
        The AI only ever saw placeholders, so a real detail in its answer means it guessed one or
        something slipped through. These are warnings shown with the answer, not blocks.
        """
        if not summary:
            return []
        block, review = cls._scan(cls._unmask(summary), entities)
        return [f"The AI response contains {item}. Check it before relying on or sharing the response." for item in block + review]
