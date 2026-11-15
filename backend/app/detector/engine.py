import uuid
import re
from typing import List, Dict, Tuple, Set, Optional, Any
from dataclasses import dataclass, field
from app.models import DocumentIR, DetectedEntity, DetectionResult
from app.detector.spacy_loader import get_nlp
from app.detector.patterns import (
    PATTERNS,
    PERSON_TITLES_REGEX,
    COMPANY_REGEX,
    BANK_REGEX
)

# Standard UK/International corporate suffixes and entity indicators
ORG_INDICATORS: Tuple[str, ...] = (
    "llp", "ltd", "limited", "plc", "llc", "inc", "corp", "corporation",
    "holdings", "partners", "chambers", "solicitors", "law firm", "bank",
    "school", "academy", "college", "university", "hospital", "clinic",
    "care home", "council", "association", "agency", "trust", "foundation", "centre", "center",
    "factory", "systems", "logistics", "services"
)

# Public judicial venues and standard contractual boilerplate (not private client organizations)
PUBLIC_VENUES_OR_CLAUSES: Tuple[str, ...] = (
    "court", "tribunal", "jurisdiction", "severability", "entire agreement",
    "governing law", "confidentiality", "warranties", "indemnities"
)

# Street suffixes to prevent addresses from being mislabelled as organizations
STREET_SUFFIXES: Tuple[str, ...] = (
    "road", "street", "avenue", "lane", "drive", "way", "close",
    "grove", "gardens", "terrace", "square", "crescent"
)

# Compiled regex for legal heading names (e.g. "WITNESS STATEMENT OF MEENA PATEL")
CAPS_HEADING_REGEX = re.compile(
    r"\b(?:STATEMENT|AFFIDAVIT|DEED|MEMORANDUM)\s+OF\s+([A-Z]{2,}(?:\s+[A-Z]{2,}){1,2})\b"
)

# Structural role-based party definitions in contracts and attendance notes
# Restrict delimiters to : or - (avoid bare commas which appear in prose)
ROLE_PREFIX_REGEX = re.compile(
    r"(?i:\b(?:Claimant|Respondent|Defendant|Plaintiff|Appellant|Solicitor|Counsel|Fee\s+Earner|Partner|Director|Witness|Author|Client|Party(?:\s+[A-Z])?|Name|Full\s+Name|Candidate|Employee|Applicant|Executive|Prepared\s+by|Attn|Attention|Dear)\b)[ \t]*[:\-–][ \t]*([A-Z][a-z]+(?:-[A-Z][a-z]+)?(?:[ \t]+[A-Z][a-z]+(?:-[A-Z][a-z]+)?){1,2})\b"
)

PARENTHETICAL_ROLE_REGEX = re.compile(
    r"\b([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,2})[ \t]*\((?:Executive|Employee|Director|Partner|Witness|Client|Claimant|Respondent|Defendant)\)"
)

# Non-name department or placeholder words to prevent catching non-persons in role regex
NON_PERSON_ROLE_WORDS: Set[str] = {
    "human", "resources", "team", "department", "division", "not", "provided",
    "applicable", "unknown", "none", "corporate", "commercial", "litigation", "finance", "legal"
}

# Known titles & honorifics classification with gender mapping
TITLE_GENDER_MAP: Dict[str, str] = {
    "mr": "M", "lord": "M", "sir": "M", "master": "M",
    "mrs": "F", "ms": "F", "miss": "F", "lady": "F", "dame": "F", "baroness": "F",
    "dr": "U", "prof": "U", "justice": "U", "judge": "U", "hon": "U"
}


@dataclass
class ParsedPersonMention:
    raw_text: str
    clean_name: str
    honorific: Optional[str] = None
    first_name: Optional[str] = None
    middle_tokens: List[str] = field(default_factory=list)
    surname: Optional[str] = None
    initial: Optional[str] = None
    gender: str = "U"  # "M", "F", "U"
    is_full_name: bool = False


def parse_person_tokens(text: str) -> ParsedPersonMention:
    """
    Parses a person mention into honorific, first name, middle tokens, surname, initial, and gender hint.
    """
    raw = text.strip()
    words = raw.split()
    honorific = None
    gender = "U"
    remaining_words = words

    if words:
        first_clean = words[0].strip(".,").lower()
        if first_clean in TITLE_GENDER_MAP:
            honorific = words[0].strip(".,")
            gender = TITLE_GENDER_MAP[first_clean]
            remaining_words = words[1:]

    clean_tokens = [w.strip(".,") for w in remaining_words if w.strip(".,")]
    # Strip leading English determiners or prepositions (e.g. "the Vance" -> "Vance")
    while clean_tokens and clean_tokens[0].lower() in {"the", "a", "an", "this", "that", "in", "for", "with", "from", "and", "or"}:
        clean_tokens.pop(0)

    if not clean_tokens:
        return ParsedPersonMention(raw_text=raw, clean_name=raw, honorific=honorific, gender=gender)

    # Conjoined phrases (e.g. "Claimant and Vance") are not a single individual
    has_conjunction = any(t.lower() in ("and", "or", "&") for t in clean_tokens)

    surname = clean_tokens[-1]
    first_name = None
    initial = None
    middle_tokens = []
    is_full = False

    if len(clean_tokens) >= 2 and not has_conjunction:
        is_full = True
        first_token = clean_tokens[0]
        if len(first_token) == 1:
            initial = first_token.upper()
        else:
            first_name = first_token
            initial = first_name[0].upper()
        middle_tokens = clean_tokens[1:-1]

    clean_name = " ".join(clean_tokens)
    return ParsedPersonMention(
        raw_text=raw,
        clean_name=clean_name,
        honorific=honorific,
        first_name=first_name,
        middle_tokens=middle_tokens,
        surname=surname,
        initial=initial,
        gender=gender,
        is_full_name=is_full
    )


@dataclass
class PersonCluster:
    cluster_id: str
    canonical_name: str
    surname: str
    first_name: Optional[str] = None
    middle_tokens: List[str] = field(default_factory=list)
    initials: Set[str] = field(default_factory=set)
    gender: str = "U"  # "M", "F", "U"
    placeholder: Optional[str] = None
    canonical_id: Optional[str] = None
    confidence: float = 0.90
    tier: str = "confident"
    entities: List[DetectedEntity] = field(default_factory=list)


class EntityRegistry:
    """
    Manages consistent typed placeholders and canonical identity mapping.
    Includes entity_type in the registry key so reclassified entities never inherit
    the wrong category placeholder (e.g. PERSON never gets [ORG 1]).
    """
    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.registry: Dict[Tuple[str, str], Tuple[str, str]] = {}

    def allocate(self, entity_type: str, canonical_key: str) -> Tuple[str, str]:
        prefix = entity_type.replace("_", " ").upper()
        if prefix in ("ORGANISATION", "ORGANIZATION"):
            prefix = "ORG"
        elif prefix == "ACCOUNT NUMBER":
            prefix = "ACCOUNT"
        elif prefix == "MONETARY AMOUNT":
            prefix = "AMOUNT"
        elif prefix == "PHYSICAL ADDRESS":
            prefix = "ADDRESS"
        elif prefix == "UK POSTCODE":
            prefix = "POSTCODE"
        elif prefix == "MATTER REF":
            prefix = "MATTER"
        elif prefix == "DATE OF BIRTH":
            prefix = "DATE"

        lookup_key = (prefix, canonical_key.strip().lower())
        if lookup_key in self.registry:
            return self.registry[lookup_key]

        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        placeholder = f"[{prefix} {self.counters[prefix]}]"
        canon_id = f"canon_{prefix.lower().replace(' ', '_')}_{self.counters[prefix]}"

        self.registry[lookup_key] = (canon_id, placeholder)
        return canon_id, placeholder


def extract_org_stem(text: str) -> str:
    """Extracts distinctive core organisation stem by stripping standard corporate indicators."""
    stem = re.sub(
        r"(?i)\b(?:llp|ltd\.?|limited|plc|llc|inc\.?|corp\.?|corporation|holdings|partners|chambers|solicitors|law\s+firm|bank|school|academy|college|hospital|clinic|systems|logistics|services|group)\b\.?$",
        "",
        text.strip()
    ).strip()
    return stem if len(stem) >= 3 else text.strip()


class DetectionEngine:
    """
    Production entity detection engine adhering to Phase 1 governance standards:
    - Document-independent rules: no client-specific or test-specific name lists or document tuning
    - Lexical filters for English determiners, boilerplate clauses, public court venues, and field labels
    - Structured UK PII regex patterns and format validation
    - Statistical Named Entity Recognition via singleton spaCy en_core_web_sm
    - Document-internal identity clustering and cross-referencing
    - Algorithmic alias resolution linking honorifics, initials, surnames, and first names
    """
    def __init__(self):
        self.nlp = get_nlp()

    def detect(self, doc_ir: DocumentIR) -> DetectionResult:
        raw_candidates: List[DetectedEntity] = []
        block_texts: Dict[str, str] = {b.id: b.text for b in doc_ir.blocks if b.text}

        # Issue 11: Scan user-authored metadata items (Author, Title, Last Modified By, etc.)
        # Exclude software tool metadata (Producer, Application, etc.)
        user_meta_keys = {"author", "creator", "last_modified_by", "last_author", "title", "subject", "comments", "description"}
        for meta in doc_ir.metadata:
            if meta.key.lower() in user_meta_keys:
                meta_val = (meta.value or "").strip()
                if len(meta_val) >= 2:
                    meta_block_id = f"meta_{meta.key}"
                    block_texts[meta_block_id] = meta_val

        # -------------------------------------------------------------------------
        # Phase 1: Candidate Extraction across Blocks & Metadata
        # (Placeholders are allocated post-clustering to prevent cross-type leakage)
        # -------------------------------------------------------------------------
        for b_id, text in block_texts.items():
            if not text:
                continue

            # 1. Structured UK Patterns (NI, Sort Code, Account, Card, Postcode, Address, Email, Phone, etc.)
            for p_name, p_info in PATTERNS.items():
                regex = p_info["regex"]
                for match in regex.finditer(text):
                    if match.groups() and match.group(1):
                        match_text = match.group(1)
                        start = match.start(1)
                        end = match.end(1)
                    else:
                        match_text = match.group()
                        start = match.start()
                        end = match.end()

                    conf = 1.0 if p_name in ("NI_NUMBER", "SORT_CODE", "ACCOUNT_NUMBER", "CREDIT_CARD", "UK_POSTCODE", "EMAIL", "DRIVING_LICENCE") else 0.95
                    raw_candidates.append(DetectedEntity(
                        id=f"ent_{uuid.uuid4().hex[:8]}",
                        block_id=b_id,
                        start=start,
                        end=end,
                        text=match_text,
                        type=p_name,
                        placeholder="",  # Assigned post-deduplication
                        confidence=conf,
                        is_active=True,
                        canonical_id=None,
                        surface_forms=[match_text],
                        tier="confident"
                    ))

            # 2. Statutory Corporate & Banking Patterns (LLP, Ltd, PLC, Holdings, recognized banks)
            for match in COMPANY_REGEX.finditer(text):
                match_text = match.group().strip()
                if "national insurance" not in match_text.lower():
                    raw_candidates.append(DetectedEntity(
                        id=f"ent_{uuid.uuid4().hex[:8]}",
                        block_id=b_id,
                        start=match.start(),
                        end=match.end(),
                        text=match_text,
                        type="ORGANISATION",
                        placeholder="",
                        confidence=0.96,
                        is_active=True,
                        canonical_id=None,
                        surface_forms=[match_text],
                        tier="confident"
                    ))

            for match in BANK_REGEX.finditer(text):
                match_text = match.group().strip()
                raw_candidates.append(DetectedEntity(
                    id=f"ent_{uuid.uuid4().hex[:8]}",
                    block_id=b_id,
                    start=match.start(),
                    end=match.end(),
                    text=match_text,
                    type="ORGANISATION",
                    placeholder="",
                    confidence=0.96,
                    is_active=True,
                    canonical_id=None,
                    surface_forms=[match_text],
                    tier="confident"
                ))

            # 3. Person Titles & Honorifics (Mr., Mrs., Ms., Dr., Master Arthur Pendelton)
            for match in PERSON_TITLES_REGEX.finditer(text):
                match_text = match.group().strip()
                raw_candidates.append(DetectedEntity(
                    id=f"ent_{uuid.uuid4().hex[:8]}",
                    block_id=b_id,
                    start=match.start(),
                    end=match.end(),
                    text=match_text,
                    type="PERSON",
                    placeholder="",
                    confidence=0.95,
                    is_active=True,
                    canonical_id=None,
                    surface_forms=[match_text],
                    tier="confident"
                ))

            # 4. Heading Person (e.g. "WITNESS STATEMENT OF MEENA PATEL")
            for match in CAPS_HEADING_REGEX.finditer(text):
                cand = match.group(1).strip()
                raw_candidates.append(DetectedEntity(
                    id=f"ent_{uuid.uuid4().hex[:8]}",
                    block_id=b_id,
                    start=match.start(1),
                    end=match.end(1),
                    text=cand,
                    type="PERSON",
                    placeholder="",
                    confidence=0.95,
                    is_active=True,
                    canonical_id=None,
                    surface_forms=[cand],
                    tier="confident"
                ))

            # 5. Structural Role-based Person Introductions (e.g. "Employee: Marcus Sterling", "Marcus Sterling (Executive)")
            # Issue 3: Marked uncertain (0.75) unless supported by spaCy model or explicit honorific
            for match in ROLE_PREFIX_REGEX.finditer(text):
                cand = match.group(1).strip()
                words = [w.lower() for w in cand.split()]
                if any(w in NON_PERSON_ROLE_WORDS for w in words):
                    continue
                raw_candidates.append(DetectedEntity(
                    id=f"ent_{uuid.uuid4().hex[:8]}",
                    block_id=b_id,
                    start=match.start(1),
                    end=match.end(1),
                    text=cand,
                    type="PERSON",
                    placeholder="",
                    confidence=0.75,
                    is_active=True,
                    canonical_id=None,
                    surface_forms=[cand],
                    tier="uncertain"
                ))

            for match in PARENTHETICAL_ROLE_REGEX.finditer(text):
                cand = match.group(1).strip()
                words = [w.lower() for w in cand.split()]
                if any(w in NON_PERSON_ROLE_WORDS for w in words):
                    continue
                raw_candidates.append(DetectedEntity(
                    id=f"ent_{uuid.uuid4().hex[:8]}",
                    block_id=b_id,
                    start=match.start(1),
                    end=match.end(1),
                    text=cand,
                    type="PERSON",
                    placeholder="",
                    confidence=0.90,
                    is_active=True,
                    canonical_id=None,
                    surface_forms=[cand],
                    tier="confident"
                ))

        # 6. Statistical Named Entity Recognition via singleton spaCy (nlp.pipe across blocks & metadata)
        valid_blocks = [(b_id, txt) for b_id, txt in block_texts.items() if txt and txt.strip()]
        if valid_blocks:
            block_texts_list = [txt for _, txt in valid_blocks]
            spacy_docs = list(self.nlp.pipe(block_texts_list, batch_size=16))

            for (b_id, original_text), spacy_doc in zip(valid_blocks, spacy_docs):
                for ent in spacy_doc.ents:
                    raw_ent_text = ent.text

                    # Issue 5: Split entities spanning newlines before using them
                    if "\n" in raw_ent_text or "\r" in raw_ent_text:
                        segments: List[Tuple[str, int]] = []
                        cur = 0
                        for line in raw_ent_text.splitlines(keepends=True):
                            line_stripped = line.strip()
                            if line_stripped:
                                line_offset = raw_ent_text.find(line, cur)
                                if line_offset != -1:
                                    cur = line_offset + len(line)
                                    segments.append((line, ent.start_char + line_offset))
                    else:
                        segments = [(raw_ent_text, ent.start_char)]

                    for seg_text, seg_base_start in segments:
                        clean_et = re.sub(r"\s*\([^)]*\)?", "", seg_text).strip()
                        # Strip leading or trailing bullets, dashes, bars, colons, or whitespace
                        clean_et = re.sub(r"^[•\-\*\s|:]+|[•\-\*\s|:]+$", "", clean_et).strip()
                        if not clean_et or len(clean_et) < 2 or re.match(r"^[\d\.\s\-_/]+$", clean_et) or re.match(r"^\d+\.\d+", clean_et):
                            continue

                        et_lower = clean_et.lower()
                        # Skip document titles, attendance note headers, table row markers, contact field labels
                        if et_lower in ("attendance note", "tel", "telephone", "email", "phone", "mob", "mobile", "row", "ledger row"):
                            continue

                        # Filter out public judicial venues (Courts) and contract boilerplate clauses
                        if any(v in et_lower for v in PUBLIC_VENUES_OR_CLAUSES):
                            continue

                        # Issue 6: Accurate offset calculation based on position of clean_et inside seg_text
                        char_pos = seg_text.find(clean_et)
                        exact_start = seg_base_start + (char_pos if char_pos != -1 else 0)
                        exact_end = exact_start + len(clean_et)

                        if ent.label_ == "PERSON":
                            # Filter all-caps section titles or acronyms with mathematical symbols
                            if clean_et.isupper() and any(w in et_lower for w in ("agreement", "memorandum", "obligations", "schedule")):
                                continue
                            if "+" in clean_et or (clean_et.isupper() and len(clean_et) <= 3):
                                continue
                            if len(clean_et) <= 3 and et_lower in ("the", "this", "that", "and", "for", "with", "from", "each", "both", "such", "said", "all", "order", "court"):
                                continue

                            words = clean_et.split()
                            is_full_name = len(words) >= 2
                            conf = 0.92 if is_full_name else 0.70
                            tier = "confident" if is_full_name else "uncertain"

                            raw_candidates.append(DetectedEntity(
                                id=f"ent_{uuid.uuid4().hex[:8]}",
                                block_id=b_id,
                                start=exact_start,
                                end=exact_end,
                                text=clean_et,
                                type="PERSON",
                                placeholder="",
                                confidence=conf,
                                is_active=True,
                                canonical_id=None,
                                surface_forms=[clean_et],
                                tier=tier
                            ))

                        elif ent.label_ in ("ORG", "FAC"):
                            # Exclude road/street addresses from becoming ORGs
                            if any(et_lower.endswith(sfx) for sfx in STREET_SUFFIXES):
                                continue
                            if "national insurance" in et_lower:
                                continue
                            if et_lower in ("party", "parties", "notice", "claimant", "respondent", "agreement", "severability", "jurisdiction", "executive"):
                                continue
                            if clean_et.isupper() and any(w in et_lower for w in ("memorandum", "obligations", "compliance", "settlement", "agreement")):
                                continue

                            words = clean_et.split()
                            first_word = words[0].strip(".,")
                            has_org_word = any(ind in et_lower for ind in ORG_INDICATORS)
                            is_titled_person = first_word.lower() in TITLE_GENDER_MAP
                            is_celtic_prefix = bool(re.match(r"^(?:O'|Mc|Mac)[A-Z][a-z]+", words[-1])) if len(words) in (2, 3) else False

                            # Reclassify to PERSON if spaCy mislabelled an entity with a person title or Celtic surname prefix
                            if is_titled_person or is_celtic_prefix:
                                raw_candidates.append(DetectedEntity(
                                    id=f"ent_{uuid.uuid4().hex[:8]}",
                                    block_id=b_id,
                                    start=exact_start,
                                    end=exact_end,
                                    text=clean_et,
                                    type="PERSON",
                                    placeholder="",
                                    confidence=0.95 if is_titled_person else 0.90,
                                    is_active=True,
                                    canonical_id=None,
                                    surface_forms=[clean_et],
                                    tier="confident"
                                ))
                            elif has_org_word:
                                raw_candidates.append(DetectedEntity(
                                    id=f"ent_{uuid.uuid4().hex[:8]}",
                                    block_id=b_id,
                                    start=exact_start,
                                    end=exact_end,
                                    text=clean_et,
                                    type="ORGANISATION",
                                    placeholder="",
                                    confidence=0.90,
                                    is_active=True,
                                    canonical_id=None,
                                    surface_forms=[clean_et],
                                    tier="confident"
                                ))
                            else:
                                # Issue 4: Organisations without an indicator word retained as uncertain instead of being dropped
                                raw_candidates.append(DetectedEntity(
                                    id=f"ent_{uuid.uuid4().hex[:8]}",
                                    block_id=b_id,
                                    start=exact_start,
                                    end=exact_end,
                                    text=clean_et,
                                    type="ORGANISATION",
                                    placeholder="",
                                    confidence=0.75,
                                    is_active=True,
                                    canonical_id=None,
                                    surface_forms=[clean_et],
                                    tier="uncertain"
                                ))

        # -------------------------------------------------------------------------
        # Phase 2: Document-Internal Cross-Referencing & Reclassification
        # Issue 2: Dropped first-name cross-referencing so "Morgan Stanley", "John Lewis"
        # and "Marks & Spencer" are NEVER converted to people based on first name alone!
        # -------------------------------------------------------------------------
        person_candidates = [e for e in raw_candidates if e.type == "PERSON"]
        parsed_mentions: Dict[str, ParsedPersonMention] = {}
        for cand in person_candidates:
            parsed_mentions[cand.id] = parse_person_tokens(cand.text)

        doc_confirmed_surnames: Set[str] = set()
        for cand in person_candidates:
            p = parsed_mentions[cand.id]
            if p.surname and len(p.surname) >= 3 and (p.is_full_name or p.honorific):
                doc_confirmed_surnames.add(p.surname.lower())

        for e in raw_candidates:
            if e.type == "ORGANISATION" and not any(ind in e.text.lower() for ind in ORG_INDICATORS):
                p_cand = parse_person_tokens(e.text)
                is_surname_match = bool(p_cand.surname and p_cand.surname.lower() in doc_confirmed_surnames)
                if p_cand.honorific or is_surname_match:
                    e.type = "PERSON"
                    parsed_mentions[e.id] = p_cand
                    if e not in person_candidates:
                        person_candidates.append(e)

        # -------------------------------------------------------------------------
        # Phase 3: Post-Collection Identity Clustering for PERSON Entities
        # Resolves Issue 1, 3, 6, 7 (shared surnames, Mrs Patel, initial matching)
        # -------------------------------------------------------------------------
        candidates_by_surname: Dict[str, List[DetectedEntity]] = {}
        for cand in person_candidates:
            p = parsed_mentions[cand.id]
            sname_key = (p.surname or p.clean_name).lower()
            candidates_by_surname.setdefault(sname_key, []).append(cand)

        person_clusters: List[PersonCluster] = []
        cluster_assignment: Dict[str, PersonCluster] = {}
        ambiguous_person_entities: List[DetectedEntity] = []

        for sname_key, cand_list in candidates_by_surname.items():
            full_name_groups: Dict[str, List[DetectedEntity]] = {}
            titled_only_groups: Dict[str, List[DetectedEntity]] = {}
            bare_mentions: List[DetectedEntity] = []

            for cand in cand_list:
                p = parsed_mentions[cand.id]
                if p.is_full_name and p.first_name:
                    fname_key = p.first_name.lower()
                    full_name_groups.setdefault(fname_key, []).append(cand)
                elif p.honorific:
                    titled_only_groups.setdefault(p.honorific.lower(), []).append(cand)
                else:
                    bare_mentions.append(cand)

            if full_name_groups:
                created_clusters_for_surname: List[PersonCluster] = []
                for fname_key, group_ents in full_name_groups.items():
                    canonical_text = max(group_ents, key=lambda x: len(x.text)).text
                    first_parsed = parsed_mentions[group_ents[0].id]
                    gender = "U"
                    for ge in group_ents:
                        g_parsed = parsed_mentions[ge.id]
                        if g_parsed.gender != "U":
                            gender = g_parsed.gender
                            break

                    initials = {first_parsed.initial} if first_parsed.initial else set()
                    cluster = PersonCluster(
                        cluster_id=f"cluster_{sname_key}_{fname_key}",
                        canonical_name=canonical_text,
                        surname=first_parsed.surname or sname_key,
                        first_name=first_parsed.first_name,
                        middle_tokens=first_parsed.middle_tokens,
                        initials=initials,
                        gender=gender,
                        confidence=max(e.confidence for e in group_ents),
                        tier="confident",
                        entities=list(group_ents)
                    )
                    person_clusters.append(cluster)
                    created_clusters_for_surname.append(cluster)
                    for ge in group_ents:
                        cluster_assignment[ge.id] = cluster

                # Assign titled mentions
                # Issue 6: If "Mrs Patel" is ambiguous between Meena and Priya, mark uncertain (do not create confident third person)
                for title_key, titled_ents in titled_only_groups.items():
                    title_gender = TITLE_GENDER_MAP.get(title_key, "U")
                    compatible_clusters = [
                        c for c in created_clusters_for_surname
                        if title_gender == "U" or c.gender == "U" or c.gender == title_gender
                    ]
                    if len(compatible_clusters) == 1:
                        target_cluster = compatible_clusters[0]
                        if title_gender != "U" and target_cluster.gender == "U":
                            target_cluster.gender = title_gender
                        for te in titled_ents:
                            cluster_assignment[te.id] = target_cluster
                            target_cluster.entities.append(te)
                    else:
                        # Ambiguous titled mention (e.g. Mrs Patel between Meena and Priya)
                        for te in titled_ents:
                            te.tier = "uncertain"
                            te.confidence = 0.70
                            ambiguous_person_entities.append(te)

                # Assign bare mentions or initial mentions (Issue 7: P. Smith matches Peter Smith)
                for be in bare_mentions:
                    be_parsed = parsed_mentions[be.id]
                    if be_parsed.initial:
                        matching_initial_clusters = [
                            c for c in created_clusters_for_surname
                            if c.initials and be_parsed.initial in c.initials
                        ]
                        if len(matching_initial_clusters) == 1:
                            target_cluster = matching_initial_clusters[0]
                            cluster_assignment[be.id] = target_cluster
                            target_cluster.entities.append(be)
                            continue

                    if len(created_clusters_for_surname) == 1:
                        single_cluster = created_clusters_for_surname[0]
                        cluster_assignment[be.id] = single_cluster
                        single_cluster.entities.append(be)
                    else:
                        be.tier = "uncertain"
                        be.confidence = 0.70
                        ambiguous_person_entities.append(be)

            elif titled_only_groups:
                created_clusters_for_surname = []
                genders_present = {TITLE_GENDER_MAP.get(tk, "U") for tk in titled_only_groups.keys()} - {"U"}
                if len(genders_present) <= 1:
                    all_titled_ents = [e for group in titled_only_groups.values() for e in group]
                    canonical_text = max(all_titled_ents, key=lambda x: len(x.text)).text
                    t_parsed = parsed_mentions[all_titled_ents[0].id]
                    gender = list(genders_present)[0] if genders_present else "U"
                    cluster = PersonCluster(
                        cluster_id=f"cluster_{sname_key}_titled",
                        canonical_name=canonical_text,
                        surname=t_parsed.surname or sname_key,
                        gender=gender,
                        confidence=0.95,
                        tier="confident",
                        entities=list(all_titled_ents)
                    )
                    person_clusters.append(cluster)
                    created_clusters_for_surname.append(cluster)
                    for te in all_titled_ents:
                        cluster_assignment[te.id] = cluster
                else:
                    for title_key, titled_ents in titled_only_groups.items():
                        canonical_text = max(titled_ents, key=lambda x: len(x.text)).text
                        t_parsed = parsed_mentions[titled_ents[0].id]
                        cluster = PersonCluster(
                            cluster_id=f"cluster_{sname_key}_{title_key}",
                            canonical_name=canonical_text,
                            surname=t_parsed.surname or sname_key,
                            gender=TITLE_GENDER_MAP.get(title_key, "U"),
                            confidence=0.95,
                            tier="confident",
                            entities=list(titled_ents)
                        )
                        person_clusters.append(cluster)
                        created_clusters_for_surname.append(cluster)
                        for te in titled_ents:
                            cluster_assignment[te.id] = cluster

                if len(created_clusters_for_surname) == 1:
                    single_cluster = created_clusters_for_surname[0]
                    for be in bare_mentions:
                        cluster_assignment[be.id] = single_cluster
                        single_cluster.entities.append(be)
                else:
                    for be in bare_mentions:
                        be.tier = "uncertain"
                        be.confidence = 0.70
                        ambiguous_person_entities.append(be)

            else:
                all_bare = bare_mentions
                canonical_text = max(all_bare, key=lambda x: len(x.text)).text
                b_parsed = parsed_mentions[all_bare[0].id]
                cluster = PersonCluster(
                    cluster_id=f"cluster_{sname_key}_bare",
                    canonical_name=canonical_text,
                    surname=b_parsed.surname or sname_key,
                    gender="U",
                    confidence=max(e.confidence for e in all_bare),
                    tier="confident" if any(e.tier == "confident" for e in all_bare) else "uncertain",
                    entities=list(all_bare)
                )
                person_clusters.append(cluster)
                for be in all_bare:
                    cluster_assignment[be.id] = cluster

        # -------------------------------------------------------------------------
        # Phase 4: Algorithmic Alias Resolution (Surnames, First Names, Org Stems)
        # Resolves Issue 2, 5, 8 (Halden stem, first names share person placeholder)
        # -------------------------------------------------------------------------
        surname_counts: Dict[str, int] = {}
        for cl in person_clusters:
            if cl.surname:
                surname_counts[cl.surname.lower()] = surname_counts.get(cl.surname.lower(), 0) + 1

        first_name_counts: Dict[str, int] = {}
        for cl in person_clusters:
            if cl.first_name:
                first_name_counts[cl.first_name.lower()] = first_name_counts.get(cl.first_name.lower(), 0) + 1

        alias_candidates: List[DetectedEntity] = []

        # 1. Person Surnames and Titles
        for cl in person_clusters:
            if cl.tier != "confident" or not cl.surname or len(cl.surname) < 3:
                continue

            sname = cl.surname
            sname_cap = sname[0].upper() + sname[1:]
            is_shared_surname = surname_counts.get(sname.lower(), 0) > 1

            prefixes = [
                r"(?:Mr|Mrs|Ms|Miss|Dr|Prof|Lord|Lady|Sir|Master|Dame)\.?\s+",
                r"[A-Z]\.\s*",
                r"[A-Z]\s+"
            ]
            if cl.first_name:
                fname_cap = cl.first_name[0].upper() + cl.first_name[1:]
                prefixes.append(rf"{re.escape(fname_cap)}\s+")

            prefix_group = f"(?:{'|'.join(prefixes)})"
            alias_pattern = re.compile(rf"\b(?:{prefix_group})?{re.escape(sname_cap)}\b")

            for b_id, b_text in block_texts.items():
                for match in alias_pattern.finditer(b_text):
                    m_text = match.group()
                    m_parsed = parse_person_tokens(m_text)

                    # Check if ambiguous when surname is shared
                    is_ambiguous_shared = False
                    target_cl = cl
                    if is_shared_surname:
                        if not m_parsed.is_full_name and not m_parsed.first_name:
                            matching_unique = None
                            if m_parsed.honorific:
                                t_gender = TITLE_GENDER_MAP.get(m_parsed.honorific.lower(), "U")
                                matching = [
                                    c for c in person_clusters
                                    if c.surname.lower() == sname.lower()
                                    and (c.gender == t_gender if t_gender != "U" and c.gender != "U" else False)
                                ]
                                if len(matching) == 1:
                                    matching_unique = matching[0]
                                    target_cl = matching_unique

                            if not matching_unique:
                                is_ambiguous_shared = True

                    if is_ambiguous_shared:
                        ent = DetectedEntity(
                            id=f"ent_{uuid.uuid4().hex[:8]}",
                            block_id=b_id,
                            start=match.start(),
                            end=match.end(),
                            text=m_text,
                            type="PERSON",
                            placeholder="",
                            confidence=0.70,
                            is_active=True,
                            canonical_id=None,
                            surface_forms=[m_text, sname_cap],
                            tier="uncertain"
                        )
                        alias_candidates.append(ent)
                        ambiguous_person_entities.append(ent)
                    else:
                        ent = DetectedEntity(
                            id=f"ent_{uuid.uuid4().hex[:8]}",
                            block_id=b_id,
                            start=match.start(),
                            end=match.end(),
                            text=m_text,
                            type="PERSON",
                            placeholder="",
                            confidence=min(0.90, target_cl.confidence),
                            is_active=True,
                            canonical_id=None,
                            surface_forms=[m_text, sname_cap],
                            tier=target_cl.tier
                        )
                        alias_candidates.append(ent)
                        cluster_assignment[ent.id] = target_cl
                        target_cl.entities.append(ent)

            # Issue 5: First names alone share established person's placeholder (tier: uncertain)
            if cl.tier == "confident" and cl.first_name and len(cl.first_name) >= 3:
                fname_lower = cl.first_name.lower()
                if fname_lower not in {"the", "this", "that", "said", "such", "each", "both", "all", "order", "court", "claimant", "defendant", "respondent"}:
                    if first_name_counts.get(fname_lower, 0) == 1:
                        fname_cap = cl.first_name[0].upper() + cl.first_name[1:]
                        fname_regex = re.compile(rf"\b{re.escape(fname_cap)}\b")
                        for b_id, b_text in block_texts.items():
                            for match in fname_regex.finditer(b_text):
                                m_text = match.group()
                                ent = DetectedEntity(
                                    id=f"ent_{uuid.uuid4().hex[:8]}",
                                    block_id=b_id,
                                    start=match.start(),
                                    end=match.end(),
                                    text=m_text,
                                    type="PERSON",
                                    placeholder="",
                                    confidence=0.75,
                                    is_active=True,
                                    canonical_id=None,
                                    surface_forms=[m_text],
                                    tier="uncertain"
                                )
                                alias_candidates.append(ent)
                                cluster_assignment[ent.id] = cl
                                cl.entities.append(ent)

        # 2. Issue 8: Organisation Stems (e.g. "Halden" after "Halden Logistics")
        org_entities = [e for e in raw_candidates if e.type == "ORGANISATION"]
        org_stems: Dict[str, str] = {}
        for org in org_entities:
            stem = extract_org_stem(org.text)
            if stem != org.text and len(stem) >= 3:
                org_stems[stem.lower()] = stem

        for stem_lower, stem_clean in org_stems.items():
            stem_regex = re.compile(rf"\b{re.escape(stem_clean)}\b")
            for b_id, b_text in block_texts.items():
                for match in stem_regex.finditer(b_text):
                    m_text = match.group()
                    alias_candidates.append(DetectedEntity(
                        id=f"ent_{uuid.uuid4().hex[:8]}",
                        block_id=b_id,
                        start=match.start(),
                        end=match.end(),
                        text=m_text,
                        type="ORGANISATION",
                        placeholder="",
                        confidence=0.85,
                        is_active=True,
                        canonical_id=None,
                        surface_forms=[m_text],
                        tier="uncertain"
                    ))

        all_candidates = raw_candidates + alias_candidates

        # -------------------------------------------------------------------------
        # Phase 5: Span Deduplication & Structured Pattern Protection
        # Issue 9: Structured patterns (DOB, NI, Sort Code, etc.) CANNOT be swallowed
        # by uncertain spans!
        # -------------------------------------------------------------------------
        deduped = self._deduplicate_spans(all_candidates, block_texts)

        # -------------------------------------------------------------------------
        # Phase 6: Late Placeholder & Canonical ID Allocation
        # Issue 1: Type is part of registry key; allocated only after clustering
        # so Marcus Sterling (Executive) gets [PERSON 1] and never [ORG 1].
        # -------------------------------------------------------------------------
        registry = EntityRegistry()

        # 1. Allocate for PersonClusters
        for cl in person_clusters:
            canon_id, placeholder = registry.allocate("PERSON", cl.canonical_name)
            cl.canonical_id = canon_id
            cl.placeholder = placeholder
            for ent in cl.entities:
                ent.canonical_id = canon_id
                ent.placeholder = placeholder

        # 2. Allocate for remaining kept entities
        for ent in deduped:
            if ent.placeholder and ent.canonical_id:
                continue

            if ent.type == "PERSON":
                if ent.id in cluster_assignment:
                    cl = cluster_assignment[ent.id]
                    ent.canonical_id = cl.canonical_id
                    ent.placeholder = cl.placeholder
                else:
                    canon_id, placeholder = registry.allocate("PERSON", ent.text)
                    ent.canonical_id = canon_id
                    ent.placeholder = placeholder
            elif ent.type == "ORGANISATION":
                stem = extract_org_stem(ent.text)
                canon_id, placeholder = registry.allocate("ORGANISATION", stem)
                ent.canonical_id = canon_id
                ent.placeholder = placeholder
            else:
                canon_id, placeholder = registry.allocate(ent.type, ent.text)
                ent.canonical_id = canon_id
                ent.placeholder = placeholder

        # -------------------------------------------------------------------------
        # Phase 7: Surface Forms Harmonization
        # Issue 8: Adds stem to organisation surface forms; adds first name to PERSON
        # -------------------------------------------------------------------------
        for ent in deduped:
            if not ent.surface_forms:
                ent.surface_forms = [ent.text]

            if ent.type == "PERSON":
                parsed = parse_person_tokens(ent.text)
                if parsed.surname and len(parsed.surname) >= 3:
                    surname = parsed.surname
                    if surname not in ent.surface_forms:
                        ent.surface_forms.append(surname)
                    for t in ("Mr", "Mr.", "Mrs", "Mrs.", "Ms", "Ms.", "Dr", "Dr."):
                        ent.surface_forms.append(f"{t} {surname}")
                    if parsed.first_name and len(parsed.first_name) >= 3:
                        if parsed.first_name not in ent.surface_forms:
                            ent.surface_forms.append(parsed.first_name)
                        initial = parsed.first_name[0]
                        ent.surface_forms.append(f"{initial}. {surname}")
                        ent.surface_forms.append(f"{initial}.{surname}")
                        ent.surface_forms.append(f"{initial} {surname}")
                        ent.surface_forms.append(f"{parsed.first_name} {surname}")
                    if parsed.middle_tokens and parsed.first_name:
                        mid_initial = parsed.middle_tokens[0][0]
                        ent.surface_forms.append(f"{parsed.first_name[0]}. {mid_initial}. {surname}")
                        ent.surface_forms.append(f"{parsed.first_name[0]}.{mid_initial}. {surname}")

            elif ent.type == "ORGANISATION":
                stem = extract_org_stem(ent.text)
                if stem != ent.text and len(stem) >= 3 and stem not in ent.surface_forms:
                    ent.surface_forms.append(stem)

            ent.surface_forms = list(dict.fromkeys(ent.surface_forms))

        counts: Dict[str, int] = {}
        for ent in deduped:
            counts[ent.type] = counts.get(ent.type, 0) + 1

        return DetectionResult(
            doc_id=doc_ir.doc_id,
            entities=deduped,
            total_entities=len(deduped),
            entities_by_type=counts
        )

    def _deduplicate_spans(
        self,
        entities: List[DetectedEntity],
        block_texts: Dict[str, str]
    ) -> List[DetectedEntity]:
        """
        Deduplicates and merges overlapping spans within each block.
        Issue 9: Structured patterns (DOB, NI, Sort Code, etc.) are strictly protected
        and CANNOT be swallowed or overridden by uncertain spans!
        """
        blocks_map: Dict[str, List[DetectedEntity]] = {}
        for ent in entities:
            blocks_map.setdefault(ent.block_id, []).append(ent)

        result: List[DetectedEntity] = []
        for block_id, ent_list in blocks_map.items():
            block_text = block_texts.get(block_id, "")

            # 1. Carve out protection for structured patterns
            struct_ents = [e for e in ent_list if e.type in PATTERNS]
            cleaned_ents: List[DetectedEntity] = []

            for ent in ent_list:
                if ent.type in PATTERNS:
                    cleaned_ents.append(ent)
                    continue

                # Check overlap with any structured pattern
                collides = False
                for s in struct_ents:
                    if max(ent.start, s.start) < min(ent.end, s.end):
                        # Collision: non-structured span overlaps with structured pattern
                        collides = True
                        if ent.start < s.start:
                            trimmed_end = s.start
                            trimmed_text = block_text[ent.start:trimmed_end].strip()
                            if len(trimmed_text) >= 3 and trimmed_text.lower() not in ("dob", "date of birth", "date", "tel", "acc", "account"):
                                ent.end = trimmed_end
                                ent.text = trimmed_text
                                cleaned_ents.append(ent)
                        break

                if not collides:
                    cleaned_ents.append(ent)

            # 2. Sort key: start ascending, structured priority, higher confidence, longer span (-len)
            def sort_key(x: DetectedEntity) -> Tuple[int, int, float, int]:
                is_struct = 0 if x.type in PATTERNS else 1
                span_len = x.end - x.start
                return (x.start, is_struct, -x.confidence, -span_len)

            sorted_ents = sorted(cleaned_ents, key=sort_key)
            merged: List[DetectedEntity] = []

            for ent in sorted_ents:
                if not merged:
                    merged.append(ent)
                    continue

                prev = merged[-1]
                # Case 1: No overlap
                if ent.start >= prev.end:
                    merged.append(ent)
                    continue

                # Case 2: ent is completely enclosed in prev
                if ent.start >= prev.start and ent.end <= prev.end:
                    # If ent is structured pattern and prev is not, structured pattern replaces prev!
                    if ent.type in PATTERNS and prev.type not in PATTERNS:
                        merged[-1] = ent
                    elif ent.confidence > prev.confidence and ent.start == prev.start and ent.end == prev.end:
                        merged[-1] = ent
                    else:
                        if ent.text not in prev.surface_forms:
                            prev.surface_forms.append(ent.text)
                        for sf in ent.surface_forms:
                            if sf not in prev.surface_forms:
                                prev.surface_forms.append(sf)
                    continue

                # Case 3: Partial overlap with extension (ent.start < prev.end and ent.end > prev.end)
                if prev.type in PATTERNS or ent.type in PATTERNS:
                    # Structured patterns cannot be merged into an organisation or generic span
                    if prev.type in PATTERNS:
                        ent.start = prev.end
                        ent.text = block_text[ent.start:ent.end].strip()
                        if len(ent.text) >= 3:
                            merged.append(ent)
                    else:
                        prev.end = ent.start
                        prev.text = block_text[prev.start:prev.end].strip()
                        if len(prev.text) < 3:
                            merged[-1] = ent
                        else:
                            merged.append(ent)
                    continue

                # Merge non-structured spans
                new_start = min(prev.start, ent.start)
                new_end = max(prev.end, ent.end)
                new_text = block_text[new_start:new_end] if block_text else ent.text

                has_prev_org_ind = any(ind in prev.text.lower() for ind in ORG_INDICATORS)
                has_ent_org_ind = any(ind in ent.text.lower() for ind in ORG_INDICATORS)

                if has_prev_org_ind or has_ent_org_ind or prev.type == "ORGANISATION" or ent.type == "ORGANISATION":
                    dominant_type = "ORGANISATION"
                    conf = max(prev.confidence, ent.confidence)
                    tier = "confident" if (has_prev_org_ind or has_ent_org_ind) else "uncertain"
                else:
                    if prev.confidence >= ent.confidence:
                        dominant_type = prev.type
                        conf = prev.confidence
                        tier = prev.tier
                    else:
                        dominant_type = ent.type
                        conf = ent.confidence
                        tier = ent.tier

                combined_surfaces = list(dict.fromkeys(prev.surface_forms + ent.surface_forms + [new_text, prev.text, ent.text]))

                prev.start = new_start
                prev.end = new_end
                prev.text = new_text
                prev.type = dominant_type
                prev.confidence = conf
                prev.tier = tier
                prev.surface_forms = combined_surfaces

            result.extend(merged)

        return result
