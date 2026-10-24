import uuid
import re
from typing import List, Dict, Tuple, Set
from app.models import DocumentIR, DetectedEntity, DetectionResult
from app.detector.patterns import (
    PATTERNS,
    PERSON_TITLES_REGEX,
    ROLE_BASED_PERSON_REGEX,
    COMMON_FIRST_NAMES,
    NAME_STOPWORDS,
    COMPANY_REGEX,
    BANK_REGEX
)

class DetectionEngine:
    def __init__(self):
        pass

    def detect(self, doc_ir: DocumentIR) -> DetectionResult:
        entities: List[DetectedEntity] = []
        value_to_jargon: Dict[str, str] = {}
        jargon_counter = 0

        # Alternate between XXX and XYZ for randomized jargon placeholders
        def get_random_jargon(text: str, ent_type: str, preferred_prefix: str = "XXX") -> str:
            nonlocal jargon_counter
            clean_text = text.strip()
            
            # Reuse existing jargon for identical or case-insensitive matching (alias consistency)
            if clean_text in value_to_jargon:
                return value_to_jargon[clean_text]
            
            for existing_val, existing_jargon in value_to_jargon.items():
                if existing_val.lower() == clean_text.lower():
                    value_to_jargon[clean_text] = existing_jargon
                    return existing_jargon

            jargon_counter += 1
            # Alternate between XXX and XYZ or respect preferred prefix
            prefix = "XXX" if (jargon_counter % 2 != 0) else "XYZ"
            if preferred_prefix in ["XXX", "XYZ"]:
                prefix = preferred_prefix
            
            # Produces random jargon format like XXX_1, XYZ_2, XXX_3
            jargon_token = f"{prefix}_{jargon_counter}"
            value_to_jargon[clean_text] = jargon_token
            return jargon_token

        for block in doc_ir.blocks:
            text = block.text
            if not text:
                continue

            # 1. Structured Patterns (NI Number, Sort Code, Postcode, Address, Email, Phone, etc.)
            for p_name, p_info in PATTERNS.items():
                regex = p_info["regex"]
                for match in regex.finditer(text):
                    # Handle capture groups for context-based regexes (like Account Number)
                    if match.groups() and match.group(1):
                        match_text = match.group(1)
                        start = match.start(1)
                        end = match.end(1)
                    else:
                        match_text = match.group()
                        start = match.start()
                        end = match.end()

                    jargon = get_random_jargon(match_text, p_name, p_info.get("jargon_prefix", "XXX"))
                    entities.append(DetectedEntity(
                        id=f"ent_{uuid.uuid4().hex[:8]}",
                        block_id=block.id,
                        start=start,
                        end=end,
                        text=match_text,
                        type=p_name,
                        placeholder=jargon,
                        confidence=0.98,
                        is_active=True
                    ))

            # 2. Person Names with Titles/Honorifics
            for match in PERSON_TITLES_REGEX.finditer(text):
                match_text = match.group()
                jargon = get_random_jargon(match_text, "PERSON", "XXX")
                entities.append(DetectedEntity(
                    id=f"ent_{uuid.uuid4().hex[:8]}",
                    block_id=block.id,
                    start=match.start(),
                    end=match.end(),
                    text=match_text,
                    type="PERSON",
                    placeholder=jargon,
                    confidence=0.95,
                    is_active=True
                ))

            # 3. Role-based Person Names (e.g. "Claimant: Jonathan Vance")
            for match in ROLE_BASED_PERSON_REGEX.finditer(text):
                if match.group(1):
                    match_text = match.group(1).strip()
                    start = match.start(1)
                    end = match.end(1)
                    if match_text not in NAME_STOPWORDS:
                        jargon = get_random_jargon(match_text, "PERSON", "XXX")
                        entities.append(DetectedEntity(
                            id=f"ent_{uuid.uuid4().hex[:8]}",
                            block_id=block.id,
                            start=start,
                            end=end,
                            text=match_text,
                            type="PERSON",
                            placeholder=jargon,
                            confidence=0.92,
                            is_active=True
                        ))

            # 4. First Name + Surname combinations in text
            name_pattern = re.compile(r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b")
            for match in name_pattern.finditer(text):
                first_name = match.group(1)
                full_match = match.group(0)
                if first_name in COMMON_FIRST_NAMES and full_match not in NAME_STOPWORDS:
                    jargon = get_random_jargon(full_match, "PERSON", "XXX")
                    entities.append(DetectedEntity(
                        id=f"ent_{uuid.uuid4().hex[:8]}",
                        block_id=block.id,
                        start=match.start(),
                        end=match.end(),
                        text=full_match,
                        type="PERSON",
                        placeholder=jargon,
                        confidence=0.88,
                        is_active=True
                    ))

            # 5. Companies & Legal Entities
            for match in COMPANY_REGEX.finditer(text):
                match_text = match.group().strip()
                jargon = get_random_jargon(match_text, "ORGANISATION", "XYZ")
                entities.append(DetectedEntity(
                    id=f"ent_{uuid.uuid4().hex[:8]}",
                    block_id=block.id,
                    start=match.start(),
                    end=match.end(),
                    text=match_text,
                    type="ORGANISATION",
                    placeholder=jargon,
                    confidence=0.94,
                    is_active=True
                ))

            # 6. Recognized Banks & Financial Institutions
            for match in BANK_REGEX.finditer(text):
                match_text = match.group().strip()
                jargon = get_random_jargon(match_text, "ORGANISATION", "XYZ")
                entities.append(DetectedEntity(
                    id=f"ent_{uuid.uuid4().hex[:8]}",
                    block_id=block.id,
                    start=match.start(),
                    end=match.end(),
                    text=match_text,
                    type="ORGANISATION",
                    placeholder=jargon,
                    confidence=0.95,
                    is_active=True
                ))

        # De-duplicate overlapping entity spans within each block
        deduped = self._deduplicate_spans(entities)

        counts: Dict[str, int] = {}
        for ent in deduped:
            counts[ent.type] = counts.get(ent.type, 0) + 1

        return DetectionResult(
            doc_id=doc_ir.doc_id,
            entities=deduped,
            total_entities=len(deduped),
            entities_by_type=counts
        )

    def _deduplicate_spans(self, entities: List[DetectedEntity]) -> List[DetectedEntity]:
        blocks_map: Dict[str, List[DetectedEntity]] = {}
        for ent in entities:
            blocks_map.setdefault(ent.block_id, []).append(ent)

        result: List[DetectedEntity] = []
        for block_id, ent_list in blocks_map.items():
            # Sort by start asc, then longer span first
            sorted_ents = sorted(ent_list, key=lambda x: (x.start, -(x.end - x.start)))
            kept: List[DetectedEntity] = []
            last_end = -1
            for ent in sorted_ents:
                if ent.start >= last_end:
                    kept.append(ent)
                    last_end = ent.end
            result.extend(kept)

        return result
