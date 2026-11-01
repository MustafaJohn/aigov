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

            # 3b. Legal Heading Person Names (e.g. "WITNESS STATEMENT OF MEENA PATEL", "AFFIDAVIT OF JOHN DOE")
            caps_heading_pattern = re.compile(
                r"\b(?:STATEMENT|AFFIDAVIT|DEED|EVIDENCE|MEMORANDUM)\s+OF\s+([A-Z]{2,}(?:\s+[A-Z]{2,}){1,2})\b"
            )
            for match in caps_heading_pattern.finditer(text):
                caps_name = match.group(1).strip()
                jargon = get_random_jargon(caps_name, "PERSON", "XXX")
                entities.append(DetectedEntity(
                    id=f"ent_{uuid.uuid4().hex[:8]}",
                    block_id=block.id,
                    start=match.start(1),
                    end=match.end(1),
                    text=caps_name,
                    type="PERSON",
                    placeholder=jargon,
                    confidence=0.95,
                    is_active=True
                ))

            # 4. First Name + Surname combinations in text (handles leading prepositions like "Between Jonathan Vance")
            LEADING_STOPWORDS = {"Between", "The", "This", "That", "In", "On", "Under", "Whereas", "Now", "Therefore", "Upon", "With", "After", "Before", "During", "Both", "Each", "All", "When", "While", "Dear", "From", "To"}
            seq_pattern = re.compile(r"\b[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,3}\b")
            for match in seq_pattern.finditer(text):
                matched_str = match.group()
                words = matched_str.split()
                start_offset = 0
                while words and words[0] in LEADING_STOPWORDS:
                    start_offset += len(words[0]) + 1
                    words.pop(0)

                if len(words) >= 2:
                    cand_name = " ".join(words)
                    first_w = words[0]
                    # Check if first word is in common names OR if candidate is not a generic title
                    if (first_w in COMMON_FIRST_NAMES or len(words) in [2, 3]) and cand_name not in NAME_STOPWORDS:
                        # Ensure not part of an organization (e.g. Barclays Bank or High Court)
                        if not any(sw in cand_name for sw in ["Court", "Bank", "LLP", "Ltd", "PLC", "Council", "Chambers", "Service", "Department"]):
                            jargon = get_random_jargon(cand_name, "PERSON", "XXX")
                            cand_start = match.start() + start_offset
                            cand_end = cand_start + len(cand_name)
                            entities.append(DetectedEntity(
                                id=f"ent_{uuid.uuid4().hex[:8]}",
                                block_id=block.id,
                                start=cand_start,
                                end=cand_end,
                                text=cand_name,
                                type="PERSON",
                                placeholder=jargon,
                                confidence=0.91,
                                is_active=True
                            ))

            # 5. Standalone party surnames introduced in legal text (e.g. "Jenkins contacted me", "session with Jenkins")
            party_verb_pattern = re.compile(
                r"\b(?:with|against|by|from|to|contacted|attended|stated|confirmed|instructed)\s+([A-Z][a-z]{3,})\b|\b([A-Z][a-z]{3,})\s+(?:contacted|attended|stated|confirmed|instructed|agreed|signed|refused)\b"
            )
            for match in party_verb_pattern.finditer(text):
                cand_surname = match.group(1) or match.group(2)
                if cand_surname and cand_surname not in NAME_STOPWORDS and cand_surname not in LEADING_STOPWORDS:
                    jargon = get_random_jargon(cand_surname, "PERSON", "XXX")
                    word_offset = match.group().find(cand_surname)
                    cand_start = match.start() + word_offset
                    cand_end = cand_start + len(cand_surname)
                    entities.append(DetectedEntity(
                        id=f"ent_{uuid.uuid4().hex[:8]}",
                        block_id=block.id,
                        start=cand_start,
                        end=cand_end,
                        text=cand_surname,
                        type="PERSON",
                        placeholder=jargon,
                        confidence=0.90,
                        is_active=True
                    ))

            # 6. Companies & Legal Entities
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
                    confidence=0.96,
                    is_active=True
                ))

            # 7. Recognized Banks & Financial Institutions
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

            # 7. Document Header / CV Name Detection (checks the first 3 blocks for standalone full names)
            if block.order < 3 and len(text.split()) in [2, 3, 4]:
                clean_header = text.strip()
                header_words = clean_header.split()
                if all(w[0].isupper() and w.isalpha() for w in header_words):
                    if clean_header not in NAME_STOPWORDS and not any(sw in clean_header for sw in ["Court", "Legal", "Curriculum", "Resume", "Dispute", "Agreement", "Terms", "Schedule"]):
                        jargon = get_random_jargon(clean_header, "PERSON", "XXX")
                        entities.append(DetectedEntity(
                            id=f"ent_{uuid.uuid4().hex[:8]}",
                            block_id=block.id,
                            start=0,
                            end=len(clean_header),
                            text=clean_header,
                            type="PERSON",
                            placeholder=jargon,
                            confidence=0.96,
                            is_active=True
                        ))

        # 8. Alias Resolution Pass (detects subsequent surname-only and initial mentions e.g. "Vance", "Mr Vance", "J. Vance")
        known_persons = [e for e in entities if e.type == "PERSON"]
        surname_to_placeholder: Dict[str, str] = {}
        for pe in known_persons:
            words = pe.text.strip().split()
            if len(words) >= 2:
                surname = words[-1].strip()
                if len(surname) >= 3 and surname not in NAME_STOPWORDS:
                    surname_to_placeholder[surname] = pe.placeholder

        for surname, placeholder in surname_to_placeholder.items():
            alias_pattern = re.compile(
                rf"\b(?:(?:Mr\.?|Mrs\.?|Ms\.?|Miss|Dr\.?)\s+|[A-Z]\.?\s+)?{re.escape(surname)}\b"
            )
            for block in doc_ir.blocks:
                for match in alias_pattern.finditer(block.text):
                    match_str = match.group()
                    entities.append(DetectedEntity(
                        id=f"ent_{uuid.uuid4().hex[:8]}",
                        block_id=block.id,
                        start=match.start(),
                        end=match.end(),
                        text=match_str,
                        type="PERSON",
                        placeholder=placeholder,
                        confidence=0.93,
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

        ORG_INDICATORS = ("School", "College", "University", "Care Home", "Community Centre", "Hospital", "Clinic", "Council", "LLP", "Ltd", "PLC", "Chambers", "Bank", "Holdings", "Partners", "Group", "Primary School")

        result: List[DetectedEntity] = []
        for block_id, ent_list in blocks_map.items():
            # If an entity was tagged as PERSON but contains organisation indicators, correct it to ORGANISATION
            for ent in ent_list:
                if ent.type == "PERSON" and any(ind in ent.text for ind in ORG_INDICATORS):
                    ent.type = "ORGANISATION"

            # Sort by start asc, longer span first, ORGANISATION before PERSON on tie
            sorted_ents = sorted(
                ent_list,
                key=lambda x: (x.start, -(x.end - x.start), 0 if x.type == "ORGANISATION" else 1)
            )
            kept: List[DetectedEntity] = []
            last_end = -1
            for ent in sorted_ents:
                if ent.start >= last_end:
                    kept.append(ent)
                    last_end = ent.end
            result.extend(kept)

        return result
