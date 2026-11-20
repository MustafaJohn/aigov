"""
Detection engine: finds personal and confidential details in a DocumentIR and assigns each a
typed placeholder ([PERSON 1], [ORG 2], [REF 1] ...).

Pipeline (one method per stage, in order):
  1. public spans     public legal references (legislation, case numbers, ECLI, courts, EU
                      institutions, glossed foreign bodies). NER never masks inside these.
  2. candidates       structured patterns (always win), rule-based names and organisations, and
                      spaCy NER. Text in capitals is also read in normal case, so pleadings
                      headings ("JOHN ALDRIDGE") are found.
  3. evidence filters ordinary-word NER guesses are dropped using the document's own evidence
                      (the word also appears in lower case, or is an acronym of lower-case words).
  4. people           mentions are clustered into individuals (surname, first name, initial,
                      honorific gender), and every alias of each individual is found.
  5. spans            overlaps resolved; structured values can never be swallowed.
  6. placeholders     allocated from the final type of each span, so a type change during
                      overlap resolution can never leave an ORG with a [PERSON n] placeholder.
  7. propagation      every further occurrence of a detected value is masked too, so the outbound
                      gate never finds an unmasked copy of something the tool itself detected.

Rules are generic English/UK legal-drafting conventions. No client, matter or test-document
values belong here.
"""
import re
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from app.models import DocumentIR, DetectedEntity, DetectionResult
from app.detector.spacy_loader import get_nlp
from app.detector.names import (
    TITLE_GENDER, PersonName, has_org_indicator, is_all_caps, lowercase_words,
    name_occurrences, org_stem, parse_person, person_forms, NAME_TOKEN,
)
from app.detector.patterns import (
    PATTERNS, PLACEHOLDER_PREFIX, PERSON_TITLES_REGEX, PARTICLE_NAME_REGEX, SURNAME_FIRST_REGEX,
    COMPANY_REGEX, BANK_REGEX, PUBLIC_LEGAL_REFERENCE_REGEX, PUBLIC_INSTITUTION_REGEX,
    GLOSSED_PUBLIC_BODY_REGEX, CITED_CASE_NAME_REGEX, LATE_PERSON_REGEX,
)

# A NER span containing one of these whole words is a court, venue or standard clause heading
PUBLIC_VENUE_OR_CLAUSE = re.compile(
    r"\b(?:court|tribunal|justice\s+centre|magistrates|jurisdiction|severability|entire\s+agreement|governing\s+law|confidentiality|warranties|indemnities)\b",
    re.IGNORECASE,
)
STREET_SUFFIX = re.compile(r"\b(?:road|street|avenue|lane|drive|way|close|grove|gardens|terrace|square|crescent)$", re.IGNORECASE)

# Form/table field labels and legal role nouns. A NER span made only of these words is a label
# ("Matter Ref", "Role", "Client"), not a name.
LABEL_WORDS = {"attendance", "note", "tel", "telephone", "email", "e-mail", "phone", "mob", "mobile", "row", "ledger",
               "party", "parties", "notice", "claimant", "respondent", "defendant", "agreement", "executive",
               "dob", "d.o.b", "client", "matter", "ref", "reference", "our", "your", "signed", "dated", "name",
               "role", "title", "position", "contact", "address", "date", "amount", "account", "sort", "code",
               "status", "type", "description", "notes", "total", "department", "number", "no",
               # document-structure headings
               "order", "judgment", "schedule", "exhibit", "defence", "particulars", "claim", "statement", "witness",
               "consent", "application", "appendix", "annex", "between", "recitals", "background", "summary",
               # email/memo header labels
               "from", "to", "subject", "re", "fw", "fwd", "cc", "bcc", "sent", "received"}
STRUCTURED_CONFIDENCE_1 = {"NI_NUMBER", "SORT_CODE", "ACCOUNT_NUMBER", "CREDIT_CARD", "UK_POSTCODE", "EMAIL", "DRIVING_LICENCE"}
FUNCTION_WORDS = {"the", "your", "our", "their", "and", "for", "with", "from", "this", "that", "into", "onto", "upon"}
CORPORATE_ACRONYMS = {"LLP", "PLC", "LTD", "LLC", "INC"}

# "WITNESS STATEMENT OF MEENA PATEL"
CAPS_HEADING_REGEX = re.compile(r"\b(?:STATEMENT|AFFIDAVIT|DEED|MEMORANDUM)\s+OF\s+([A-Z]{2,}(?:\s+[A-Z]{2,}){1,2})\b")

# "Employee: Marcus Sterling", "Prepared by - Jane Doe" (delimiter must be : or -, never a bare comma)
_ROLE_NAME = rf"{NAME_TOKEN}(?:[ \t]+{NAME_TOKEN}){{1,2}}"
ROLE_PREFIX_REGEX = re.compile(
    r"(?i:\b(?:Claimant|Respondent|Defendant|Plaintiff|Appellant|Solicitor|Counsel|Fee\s+Earner|Partner|Director|Witness|"
    r"Author|Client|Party(?:\s+[A-Z])?|Name|Full\s+Name|Candidate|Employee|Applicant|Executive|Prepared\s+by|Attn|Attention|Dear)\b)"
    rf"[ \t]*[:\-–][ \t]*(?:(?:Mr|Mrs|Ms|Miss|Dr)\.?[ \t]+)?({_ROLE_NAME})(?!\w)"
)
# "Marcus Sterling (Executive)"
PARENTHETICAL_ROLE_REGEX = re.compile(
    rf"({_ROLE_NAME})[ \t]*\((?:Executive|Employee|Director|Partner|Witness|Client|Claimant|Respondent|Defendant)\)"
)
NON_PERSON_ROLE_WORDS = {"human", "resources", "team", "department", "division", "not", "provided", "applicable",
                         "unknown", "none", "corporate", "commercial", "litigation", "finance", "legal"}

_CAPS_WORD = re.compile(r"(?<![\w'’-])[A-ZÀ-Þ][A-ZÀ-Þ'’\-]+(?![\w'’-])")


def caps_normalised(text: str) -> str:
    """Same text with words in capitals rewritten in normal case; offsets are unchanged."""
    def fix(m: re.Match) -> str:
        w = m.group()
        if w in CORPORATE_ACRONYMS:
            return w
        t = w.title()
        return t if len(t) == len(w) else w
    return _CAPS_WORD.sub(fix, text)


_CAPS_RUN = re.compile(r"(?<![\w'’-])[A-ZÀ-Þ][A-ZÀ-Þ'’\-]+[ \t]+[A-ZÀ-Þ][A-ZÀ-Þ'’\-]+(?![\w'’-])")


def needs_caps_pass(text: str) -> bool:
    """A name in capitals is at least two capitalised words; a lone acronym (KB, UK, IHS) is not."""
    return bool(_CAPS_RUN.search(text))


def _strip_possessive(name: str) -> str:
    return re.sub(r"['’]s?$", "", name) if re.search(r"\w['’]s?$", name) else name


def _has_caps_word(span: str) -> bool:
    return any(is_all_caps(w) for w in span.split())


_RELATIVE = r"(?:wife|husband|spouse|widow|widower|mother|father|mum|dad|son|daughter|sister|brother|grandmother|grandfather|aunt|uncle|niece|nephew|cousin|stepmother|stepfather|stepson|stepdaughter)"
_RELATIVE_BEFORE = re.compile(rf"\b{_RELATIVE}\b[\s,:-]*$", re.IGNORECASE)
_RELATIVE_AFTER = re.compile(rf"^[\s,]*\((?:my|his|her|their|the\s+\w+'s)\s+{_RELATIVE}\)", re.IGNORECASE)


def is_relative_mention(text: str, start: int, end: int) -> bool:
    """'his wife, Mrs Vance' / 'Mrs Patel (my mother)': a titled mention that names a relative is a different person."""
    return bool(_RELATIVE_BEFORE.search(text[max(0, start - 30):start]) or _RELATIVE_AFTER.search(text[end:end + 40]))


# Full Name ("Short") / (the "Short") / (hereinafter "Short")
_DEFINED_TERM = re.compile(r"^\s*\(\s*(?:hereinafter\s+(?:called\s+|referred\s+to\s+as\s+)?)?(the\s+)?[\"“”'‘’]([^\"“”'‘’]{2,40})[\"“”'‘’]\s*\)", re.IGNORECASE)


def _overlaps(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    return max(a[0], b[0]) < min(a[1], b[1])


@dataclass
class PersonCluster:
    cluster_id: str
    canonical_name: str
    surname: str
    first_name: Optional[str] = None
    initials: Set[str] = field(default_factory=set)
    gender: str = "U"
    tier: str = "confident"
    confidence: float = 0.90


class EntityRegistry:
    """One placeholder per (type, canonical key) within a document."""
    def __init__(self) -> None:
        self.counters: Dict[str, int] = {}
        self.registry: Dict[Tuple[str, str], Tuple[str, str]] = {}

    def allocate(self, entity_type: str, key: str) -> Tuple[str, str]:
        prefix = PLACEHOLDER_PREFIX.get(entity_type, entity_type.replace("_", " "))
        lookup = (prefix, key.strip().lower())
        if lookup not in self.registry:
            self.counters[prefix] = self.counters.get(prefix, 0) + 1
            n = self.counters[prefix]
            self.registry[lookup] = (f"canon_{prefix.lower().replace(' ', '_')}_{n}", f"[{prefix} {n}]")
        return self.registry[lookup]


def _entity(block_id: str, start: int, end: int, text: str, type_: str, confidence: float, tier: str = "confident") -> DetectedEntity:
    return DetectedEntity(id=f"ent_{uuid.uuid4().hex[:10]}", block_id=block_id, start=start, end=end, text=text,
                          type=type_, placeholder="", confidence=confidence, is_active=True, surface_forms=[text], tier=tier)


class DetectionEngine:
    def __init__(self) -> None:
        self.nlp = get_nlp()

    # ------------------------------------------------------------------------------------------
    def detect(self, doc_ir: DocumentIR) -> DetectionResult:
        blocks: Dict[str, str] = {b.id: b.text for b in doc_ir.blocks if b.text and b.text.strip()}
        block_order = {bid: i for i, bid in enumerate(blocks)}
        doc_lower_words = lowercase_words("\n".join(blocks.values()))

        public = self._public_spans(blocks)
        ner_ids: Set[str] = set()
        cands: List[DetectedEntity] = []
        for bid, text in blocks.items():
            cands += self._structured(bid, text)
            cands += self._rule_based(bid, text, text)
            if needs_caps_pass(text):
                cands += [c for c in self._rule_based(bid, caps_normalised(text), text) if _has_caps_word(c.text)]
        cands += self._ner(blocks, ner_ids, doc_lower_words)

        cands = self._drop_public(cands, public, ner_ids)
        parsed = self._reclassify_orgs_as_people(cands)
        cands = self._drop_ordinary_words(cands, ner_ids, parsed, doc_lower_words, blocks)

        clusters, assignment = self._cluster_people(cands, parsed, blocks)
        alias_of: Dict[str, str] = {}
        cands += self._defined_term_aliases(blocks, cands, assignment, alias_of)
        cands += self._person_aliases(blocks, clusters, assignment)
        cands += self._org_aliases(blocks, cands)

        kept = self._deduplicate_spans(cands, blocks)
        self._allocate(kept, assignment, block_order, alias_of)
        kept += self._propagate(kept, blocks, public)
        self._surface_forms(kept, assignment)

        kept.sort(key=lambda e: (block_order.get(e.block_id, 0), e.start))
        counts: Dict[str, int] = {}
        for e in kept:
            counts[e.type] = counts.get(e.type, 0) + 1
        return DetectionResult(doc_id=doc_ir.doc_id, entities=kept, total_entities=len(kept), entities_by_type=counts)

    # ------------------------------------------------------------------------------------------
    # 1. Public spans
    # ------------------------------------------------------------------------------------------
    def _public_spans(self, blocks: Dict[str, str]) -> Dict[str, List[Tuple[int, int]]]:
        glossed: Set[str] = set()
        for text in blocks.values():
            for m in GLOSSED_PUBLIC_BODY_REGEX.finditer(text):
                for name in (m.group(1), m.group(2)):               # the body and its English gloss
                    name = re.sub(r"(?i)^the\s+", "", name).strip()
                    if len(name) >= 3:
                        glossed.add(name)
        spans: Dict[str, List[Tuple[int, int]]] = {}
        for bid, text in blocks.items():
            s = [m.span() for rx in (PUBLIC_LEGAL_REFERENCE_REGEX, PUBLIC_INSTITUTION_REGEX) for m in rx.finditer(text)]
            s += [m.span(g) for m in CITED_CASE_NAME_REGEX.finditer(text) for g in (1, 2) if m.group(g)]
            for name in glossed:
                s += [m.span() for m in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", text)]
            if s:
                spans[bid] = s
        return spans

    # ------------------------------------------------------------------------------------------
    # 2. Candidates
    # ------------------------------------------------------------------------------------------
    def _structured(self, bid: str, text: str) -> List[DetectedEntity]:
        out = []
        for p_name, p in PATTERNS.items():
            for m in p["regex"].finditer(text):
                g = next((i for i in range(1, (p["regex"].groups or 0) + 1) if m.group(i)), 0)
                s, e = m.span(g)
                value = text[s:e]
                if p.get("validate") and not p["validate"](value):
                    continue
                out.append(_entity(bid, s, e, value, p_name, 1.0 if p_name in STRUCTURED_CONFIDENCE_1 else 0.95))
        return out

    def _rule_based(self, bid: str, text: str, original: str) -> List[DetectedEntity]:
        """Rule-based names/organisations on `text`; spans and values are taken from `original`."""
        out: List[DetectedEntity] = []

        def add(s: int, e: int, type_: str, conf: float, tier: str = "confident") -> None:
            value = _strip_possessive(original[s:e].strip())
            if value:
                out.append(_entity(bid, s, s + len(value), value, type_, conf, tier))

        for m in COMPANY_REGEX.finditer(text):
            if "national insurance" not in m.group().lower():
                add(m.start(), m.end(), "ORGANISATION", 0.96)
        for m in BANK_REGEX.finditer(text):
            add(m.start(), m.end(), "ORGANISATION", 0.96)
        for m in PERSON_TITLES_REGEX.finditer(text):
            add(m.start(), m.end(), "PERSON", 0.95)
        for m in LATE_PERSON_REGEX.finditer(text):
            add(m.start(1), m.end(1), "PERSON", 0.95)
        for m in PARTICLE_NAME_REGEX.finditer(text):
            if not PUBLIC_VENUE_OR_CLAUSE.search(m.group()):
                add(m.start(), m.end(), "PERSON", 0.92)
        for m in CAPS_HEADING_REGEX.finditer(original):
            add(m.start(1), m.end(1), "PERSON", 0.95)
        for m in SURNAME_FIRST_REGEX.finditer(original):
            add(m.start(), m.end(), "PERSON", 0.90)
        for m in ROLE_PREFIX_REGEX.finditer(text):
            if not any(w.lower() in NON_PERSON_ROLE_WORDS for w in m.group(1).split()):
                add(m.start(1), m.end(1), "PERSON", 0.75, "uncertain")
        for m in PARENTHETICAL_ROLE_REGEX.finditer(text):
            if not any(w.lower() in NON_PERSON_ROLE_WORDS for w in m.group(1).split()):
                add(m.start(1), m.end(1), "PERSON", 0.90)
        return out

    def _ner(self, blocks: Dict[str, str], ner_ids: Set[str], doc_lower_words: Set[str]) -> List[DetectedEntity]:
        """spaCy over every block, plus a normal-case reading of blocks that contain capitals."""
        items = list(blocks.items())
        caps_items = [(bid, t) for bid, t in items if needs_caps_pass(t)]
        docs = list(self.nlp.pipe([t for _, t in items] + [caps_normalised(t) for _, t in caps_items], batch_size=16))
        out: List[DetectedEntity] = []
        postcodes = {bid: [m.span() for m in PATTERNS["UK_POSTCODE"]["regex"].finditer(t)] for bid, t in items}

        for idx, ((bid, original), doc) in enumerate(zip(items + caps_items, docs)):
            from_caps_pass = idx >= len(items)
            for ent in doc.ents:
                if from_caps_pass and ent.label_ != "PERSON":
                    continue
                for seg_text, seg_start in self._split_lines(original[ent.start_char:ent.end_char], ent.start_char):
                    clean = re.sub(r"\s*\([^)]*\)?", "", seg_text)
                    clean = re.sub(r"^[•\-\*\s|:]+|[•\-\*\s|:]+$", "", clean).strip()
                    if len(clean) < 2 or re.fullmatch(r"[\d.\s\-_/]+", clean) or re.match(r"^\d+\.\d+", clean):
                        continue
                    low = clean.lower()
                    if all(w in LABEL_WORDS for w in re.findall(r"[\w.-]+", low)) or PUBLIC_VENUE_OR_CLAUSE.search(clean):
                        continue
                    clean = _strip_possessive(clean)
                    pos = seg_text.find(clean)
                    s = seg_start + (pos if pos != -1 else 0)
                    e = s + len(clean)

                    cand: Optional[DetectedEntity] = None
                    if any(_overlaps((s, e), pc) for pc in postcodes.get(bid, [])) and not has_org_indicator(clean):
                        continue                              # "Leicester LE2 7QP" / "Manchester M60" end an address; not a name
                    if ent.label_ == "PERSON":
                        if "+" in clean or (clean.isupper() and len(clean) <= 3):
                            continue
                        if re.search(r"(?i)\s(?:v|vs|and|&)\.?\s", f" {clean} "):
                            continue                          # "John v PATEL" spans two parties
                        if "," in clean and not SURNAME_FIRST_REGEX.fullmatch(clean):
                            continue
                        if from_caps_pass:
                            # Capitals read in normal case: only full names whose words are not
                            # ordinary words of this document ("WITNESS STATEMENT" is not a person).
                            words = [w for w in re.findall(r"[^\W\d_]+", clean) if len(w) >= 3 and w.lower() not in FUNCTION_WORDS]
                            if len(clean.split()) < 2 or not _has_caps_word(clean) or not words \
                                    or all(w.lower() in doc_lower_words or w.lower() in LABEL_WORDS for w in words):
                                continue
                        full = len(clean.split()) >= 2
                        cand = _entity(bid, s, e, clean, "PERSON", 0.92 if full else 0.70, "confident" if full else "uncertain")
                    elif ent.label_ in ("ORG", "FAC"):
                        if STREET_SUFFIX.search(clean) or "national insurance" in low:
                            continue
                        if re.match(r"^(?:Gmail|Outlook|Yahoo(?:\s+Mail)?|Apple\s+Mail|Thunderbird|Webmail)\s*[-–—]", clean, re.IGNORECASE):
                            continue
                        if clean.isupper() and re.search(r"memorandum|obligations|compliance|settlement|agreement", low):
                            continue
                        words = clean.split()
                        titled = words[0].strip(".,").lower() in TITLE_GENDER
                        celtic = len(words) in (2, 3) and bool(re.match(r"^(?:O'|Mc|Mac)[A-Z][a-z]+", words[-1]))
                        if titled or celtic:
                            cand = _entity(bid, s, e, clean, "PERSON", 0.95 if titled else 0.90)
                        elif has_org_indicator(clean):
                            cand = _entity(bid, s, e, clean, "ORGANISATION", 0.90)
                        else:
                            cand = _entity(bid, s, e, clean, "ORGANISATION", 0.75, "uncertain")
                    if cand:
                        ner_ids.add(cand.id)
                        out.append(cand)
        return out

    @staticmethod
    def _split_lines(text: str, base: int) -> List[Tuple[str, int]]:
        if "\n" not in text and "\r" not in text:
            return [(text, base)]
        out, cur = [], 0
        for line in text.splitlines(keepends=True):
            if line.strip():
                off = text.find(line, cur)
                if off != -1:
                    cur = off + len(line)
                    out.append((line, base + off))
        return out

    # ------------------------------------------------------------------------------------------
    # 3. Evidence filters
    # ------------------------------------------------------------------------------------------
    @staticmethod
    def _drop_public(cands: List[DetectedEntity], public: Dict[str, List[Tuple[int, int]]], ner_ids: Set[str]) -> List[DetectedEntity]:
        """
        NER guesses and organisation patterns that touch a public legal reference are dropped
        ('EC' inside 'Directive 95/46/EC'). Structured values are never dropped. Rule-based person
        matches (honorifics, roles) are dropped only when wholly inside a public span.
        """
        kept = []
        for c in cands:
            spans = public.get(c.block_id, [])
            if not spans or c.type in PATTERNS:
                kept.append(c)
                continue
            if c.id in ner_ids or c.type == "ORGANISATION":
                if any(_overlaps((c.start, c.end), s) for s in spans):
                    continue
            elif any(s[0] <= c.start and c.end <= s[1] for s in spans):
                continue
            kept.append(c)
        return kept

    @staticmethod
    def _reclassify_orgs_as_people(cands: List[DetectedEntity]) -> Dict[str, PersonName]:
        """
        spaCy often labels people as ORG. An ORG without an organisation word becomes a PERSON
        if it carries an honorific, ends in a surname confirmed elsewhere in the document, or
        matches a confirmed person's first name.
        """
        parsed = {c.id: parse_person(c.text) for c in cands if c.type == "PERSON"}
        confirmed = {p.surname.lower() for p in parsed.values()
                     if p.surname and len(p.surname) >= 3 and (p.is_full or p.honorific)}
        first_names = {p.first.lower() for p in parsed.values() if p.is_full and p.first and len(p.first) >= 3}
        full_names = {p.clean.lower() for p in parsed.values() if p.is_full}
        for c in cands:
            # "Oluwaseun Adeyemi of Flat 3" tagged ORG: keep the person, drop the address tail
            if c.type == "ORGANISATION" and not has_org_indicator(c.text) and " of " in c.text:
                left = c.text.split(" of ")[0].strip()
                if parse_person(left).clean.lower() in full_names:
                    c.text, c.end, c.type = left, c.start + len(left), "PERSON"
                    parsed[c.id] = parse_person(left)
                    continue
            if c.type == "ORGANISATION" and not has_org_indicator(c.text) and " " not in c.text.strip() \
                    and c.text.lower() in first_names:
                c.type, c.tier, c.confidence = "PERSON", "uncertain", 0.75
                parsed[c.id] = parse_person(c.text)
                continue
            if c.type == "ORGANISATION" and not has_org_indicator(c.text):
                p = parse_person(c.text)
                if p.honorific or (p.surname and p.surname.lower() in confirmed):
                    c.type = "PERSON"
                    parsed[c.id] = p
        return parsed

    def _drop_ordinary_words(self, cands: List[DetectedEntity], ner_ids: Set[str], parsed: Dict[str, PersonName],
                             doc_lower_words: Set[str], blocks: Dict[str, str]) -> List[DetectedEntity]:
        """
        Drop uncorroborated NER guesses that the document itself shows are ordinary words:
          - a single-word PERSON guess whose word also appears in lower case ('Request' when the
            document says 'this request'), unless it is a known first name or surname of someone
          - an uncertain ORG guess whose content words mostly appear in lower case
            ('Surcharge', 'Gmail - Your Immigration Health Surcharge')
          - an uncertain ALL-CAPS ORG guess that the document defines as the initials of
            lower-case words ('immigration health surcharge (IHS)')
        Organisations with a legal suffix, and anything a rule (honorific, role, pattern) found,
        are never dropped here.
        """
        # First names and surnames the document confirms (rule-based finds, or any full name)
        known_names: Set[str] = set()
        for c in cands:
            if c.type != "PERSON":
                continue
            p = parsed.get(c.id) or parse_person(c.text)
            if c.id not in ner_ids or p.is_full:
                known_names.update(x.lower() for x in (p.first, p.surname) if x)
        all_text = "\n".join(blocks.values())
        place_words = {w for c in cands if c.type == "PHYSICAL_ADDRESS" for w in re.findall(r"[A-Z][a-z]+", c.text)}

        def ordinary(word: str) -> bool:
            return word.lower() in doc_lower_words

        kept = []
        for c in cands:
            if c.id not in ner_ids or c.tier != "uncertain":
                kept.append(c)
                continue
            words = [w for w in re.findall(r"[^\W\d_]+", c.text) if len(w) >= 3 and w.lower() not in FUNCTION_WORDS]
            if c.type == "PERSON" and len(c.text.split()) == 1:
                if (ordinary(c.text) or c.text in place_words) and c.text.lower() not in known_names:
                    continue
            elif c.type == "ORGANISATION":
                if words and sum(ordinary(w) for w in words) / len(words) >= 0.75:
                    continue
                if c.text.isupper() and 2 <= len(c.text) <= 6 and self._is_acronym_of_ordinary_words(c.text, all_text, ordinary):
                    continue
            kept.append(c)
        return kept

    @staticmethod
    def _is_acronym_of_ordinary_words(acr: str, text: str, ordinary) -> bool:
        n = len(acr)
        rx = re.compile(r"((?:[^\W\d_]+[\s\-]+){%d})\(\s*%s\s*\)" % (n, re.escape(acr)))
        for m in rx.finditer(text):
            words = re.findall(r"[^\W\d_]+", m.group(1))
            if "".join(w[0] for w in words).upper() == acr and all(ordinary(w) for w in words):
                return True
        return False

    # ------------------------------------------------------------------------------------------
    # 4. People: clustering and aliases
    # ------------------------------------------------------------------------------------------
    @staticmethod
    def _cluster_people(cands: List[DetectedEntity], parsed: Dict[str, PersonName], blocks: Dict[str, str]):
        """
        Group person mentions into individuals by surname, then by first name. Titled mentions
        ('Mrs Patel') join the single compatible full-name cluster; if two are compatible the
        mention is left uncertain rather than guessed. Initials pick between same-surname people.
        """
        by_surname: Dict[str, List[DetectedEntity]] = {}
        for c in cands:
            if c.type == "PERSON":
                p = parsed.setdefault(c.id, parse_person(c.text))
                by_surname.setdefault((p.surname or p.clean).lower(), []).append(c)

        clusters: List[PersonCluster] = []
        assignment: Dict[str, PersonCluster] = {}

        def new_cluster(key: str, members: List[DetectedEntity], tier: str = "confident") -> PersonCluster:
            ps = [parsed[m.id] for m in members]
            canonical = max(members, key=lambda m: len(m.text)).text
            first = next((p.first for p in ps if p.first), None)
            cl = PersonCluster(cluster_id=f"cluster_{key}_{len(clusters)}", canonical_name=canonical,
                               surname=ps[0].surname or key, first_name=first,
                               initials={p.initial for p in ps if p.initial},
                               gender=next((p.gender for p in ps if p.gender != "U"), "U"),
                               tier=tier, confidence=max(m.confidence for m in members))
            clusters.append(cl)
            for m in members:
                assignment[m.id] = cl
            return cl

        def uncertain(c: DetectedEntity) -> None:
            c.tier, c.confidence = "uncertain", 0.70

        for skey, members in by_surname.items():
            full: Dict[str, List[DetectedEntity]] = {}
            titled: Dict[str, List[DetectedEntity]] = {}
            bare: List[DetectedEntity] = []
            for c in members:
                p = parsed[c.id]
                if p.is_full and p.first:
                    full.setdefault(p.first.lower(), []).append(c)
                elif p.honorific:
                    titled.setdefault(p.honorific.lower(), []).append(c)
                else:
                    bare.append(c)

            made: List[PersonCluster] = []
            if full:
                made = [new_cluster(f"{skey}_{fk}", ms) for fk, ms in full.items()]
                for title_key, ms in titled.items():
                    g = TITLE_GENDER.get(title_key, "U")
                    compatible = [cl for cl in made if g == "U" or cl.gender in ("U", g)]
                    for c in ms:
                        if len(compatible) == 1 and not is_relative_mention(blocks.get(c.block_id, ""), c.start, c.end):
                            if g != "U" and compatible[0].gender == "U":
                                compatible[0].gender = g
                            assignment[c.id] = compatible[0]
                        else:
                            uncertain(c)
            elif titled:
                genders = {TITLE_GENDER.get(t, "U") for t in titled} - {"U"}
                if len(genders) <= 1:
                    made = [new_cluster(f"{skey}_titled", [c for ms in titled.values() for c in ms])]
                else:
                    made = [new_cluster(f"{skey}_{t}", ms) for t, ms in titled.items()]
            elif bare:
                tier = "confident" if any(c.tier == "confident" for c in bare) else "uncertain"
                cl = new_cluster(f"{skey}_bare", bare, tier)
                cl.cluster_id += "_bare"
                continue

            for c in bare:
                p = parsed[c.id]
                by_initial = [cl for cl in made if p.initial and p.initial in cl.initials]
                target = by_initial[0] if len(by_initial) == 1 else (made[0] if len(made) == 1 else None)
                if target:
                    assignment[c.id] = target
                else:
                    uncertain(c)

        by_first: Dict[str, List[PersonCluster]] = {}
        for cl in clusters:
            if cl.first_name:
                by_first.setdefault(cl.first_name.lower(), []).append(cl)
        for cl in [c for c in clusters if c.cluster_id.endswith("_bare")]:
            owners = by_first.get(cl.surname.lower(), [])
            if len(owners) == 1 and " " not in cl.surname:
                for eid, assigned in list(assignment.items()):
                    if assigned is cl:
                        assignment[eid] = owners[0]
                clusters.remove(cl)
        return clusters, assignment

    @staticmethod
    def _person_aliases(blocks: Dict[str, str], clusters: List[PersonCluster], assignment: Dict[str, PersonCluster]) -> List[DetectedEntity]:
        """
        Find every further mention of each person: surname alone, with an honorific, with an
        initial, and the first name alone when no one else in the document shares it. Matches
        are in the name's own case or in capitals only. A gendered honorific that contradicts the
        person ('Mrs Hale' next to 'Mr Daniel Hale') is a different person and is kept apart.
        """
        out: List[DetectedEntity] = []
        surname_count: Dict[str, int] = {}
        first_count: Dict[str, int] = {}
        for cl in clusters:
            surname_count[cl.surname.lower()] = surname_count.get(cl.surname.lower(), 0) + 1
            if cl.first_name:
                first_count[cl.first_name.lower()] = first_count.get(cl.first_name.lower(), 0) + 1

        titles = ["Mr", "Mrs", "Ms", "Miss", "Dr", "Prof", "Lord", "Lady", "Sir", "Master", "Dame"]
        for cl in clusters:
            if len(cl.surname.replace(" ", "")) < 3:
                continue
            shared = surname_count[cl.surname.lower()] > 1
            forms = {cl.surname} | {f"{t}{d} {cl.surname}" for t in titles for d in ("", ".")}
            forms |= {f"{i}{sep}{cl.surname}" for i in cl.initials for sep in (". ", ".", " ")}
            if cl.first_name:
                forms.add(f"{cl.first_name} {cl.surname}")

            for bid, text in blocks.items():
                for form in forms:
                    for m in name_occurrences(text, form):
                        p = parse_person(m.group())
                        conf, tier, target = min(0.90, cl.confidence), cl.tier, cl
                        if p.initial and p.initial not in cl.initials:
                            continue                                    # another person's initial
                        g = TITLE_GENDER.get((p.honorific or "").lower(), "U")
                        if p.honorific and not p.first and is_relative_mention(text, m.start(), m.end()):
                            target, tier, conf = None, "uncertain", 0.70   # 'his wife, Mrs Vance'
                        elif g != "U" and cl.gender not in ("U", g):
                            target, tier, conf = None, "uncertain", 0.70   # gender contradicts: a different person
                        elif shared and not p.first and not p.initial:
                            same = [c for c in clusters if c.surname.lower() == cl.surname.lower() and g != "U" and c.gender == g]
                            target = same[0] if len(same) == 1 else None
                            if target is None:
                                tier, conf = "uncertain", 0.70
                        ent = _entity(bid, m.start(), m.end(), m.group(), "PERSON", conf, tier)
                        out.append(ent)
                        if target:
                            assignment[ent.id] = target

            if cl.first_name and len(cl.first_name) >= 3 and first_count.get(cl.first_name.lower()) == 1:
                for bid, text in blocks.items():
                    for m in name_occurrences(text, cl.first_name):
                        ent = _entity(bid, m.start(), m.end(), m.group(), "PERSON", 0.75, "uncertain")
                        out.append(ent)
                        assignment[ent.id] = cl
        return out

    @staticmethod
    def _defined_term_aliases(blocks: Dict[str, str], cands: List[DetectedEntity], assignment: Dict[str, PersonCluster],
                              alias_of: Dict[str, str]) -> List[DetectedEntity]:
        """
        'Ashworth Care Homes Limited ("Ashworth")': the defined short name is an alias of the full
        name, so every later 'Ashworth' gets the same placeholder. Only a term that shares words or
        initials with the full name counts; role terms such as ("the Company") are not aliases.
        """
        out: List[DetectedEntity] = []
        for c in cands:
            if c.type not in ("PERSON", "ORGANISATION"):
                continue
            m = _DEFINED_TERM.match(blocks.get(c.block_id, "")[c.end:])
            if not m or m.group(1):
                continue
            term = m.group(2).strip()
            full_words = re.findall(r"[^\W_]+", c.text)
            term_words = re.findall(r"[^\W_]+", term)
            initials = "".join(w[0] for w in full_words if w[0].isupper()).upper()
            if not term_words or not (set(w.lower() for w in term_words) <= set(w.lower() for w in full_words) or term.upper() == initials):
                continue
            for bid, text in blocks.items():
                for occ in name_occurrences(text, term):
                    ent = _entity(bid, occ.start(), occ.end(), occ.group(), c.type, 0.90)
                    out.append(ent)
                    if c.type == "PERSON" and c.id in assignment:
                        assignment[ent.id] = assignment[c.id]
                    alias_of[ent.id] = c.text
        return out

    @staticmethod
    def _org_aliases(blocks: Dict[str, str], cands: List[DetectedEntity]) -> List[DetectedEntity]:
        """'Halden' wherever 'Halden Logistics Ltd' was found."""
        stems = {org_stem(c.text) for c in cands if c.type == "ORGANISATION" and has_org_indicator(c.text)}
        out = []
        for stem in stems:
            if len(stem) < 3 or stem.lower() in FUNCTION_WORDS:
                continue
            for bid, text in blocks.items():
                for m in name_occurrences(text, stem):
                    out.append(_entity(bid, m.start(), m.end(), m.group(), "ORGANISATION", 0.85, "uncertain"))
        return out

    # ------------------------------------------------------------------------------------------
    # 6. Placeholders and 7. propagation
    # ------------------------------------------------------------------------------------------
    @staticmethod
    def _allocate(kept: List[DetectedEntity], assignment: Dict[str, PersonCluster], block_order: Dict[str, int],
                  alias_of: Dict[str, str]) -> None:
        """Numbered in reading order, from each span's final type."""
        registry = EntityRegistry()
        for e in sorted(kept, key=lambda e: (block_order.get(e.block_id, 0), e.start)):
            if e.type == "PERSON":
                cl = assignment.get(e.id)
                key = f"cluster:{cl.cluster_id}" if cl else f"text:{' '.join(alias_of.get(e.id, e.text).lower().split())}"
            elif e.type == "ORGANISATION":
                key = org_stem(alias_of.get(e.id, e.text))
            else:
                key = re.sub(r"[\s\-]", "", e.text)
            e.canonical_id, e.placeholder = registry.allocate(e.type, key)

    @staticmethod
    def _propagate(kept: List[DetectedEntity], blocks: Dict[str, str], public: Dict[str, List[Tuple[int, int]]]) -> List[DetectedEntity]:
        """
        Mask every other occurrence of each detected value with the same placeholder. Without
        this, NER tags 'IHS' in two places and misses three, and the outbound gate then blocks on
        the three it can see (lawyer test, IHS email).
        """
        taken: Dict[str, List[Tuple[int, int]]] = {}
        for e in kept:
            taken.setdefault(e.block_id, []).append((e.start, e.end))
        seen: Set[Tuple[str, str]] = set()
        added: List[DetectedEntity] = []
        for e in sorted(kept, key=lambda e: -len(e.text)):          # longest first, so 'Halden Ltd' beats 'Halden'
            key = (e.type, e.text)
            if key in seen or len(e.text.strip()) < 2:
                continue
            seen.add(key)
            for bid, text in blocks.items():
                if e.type in ("PERSON", "ORGANISATION"):
                    hits = name_occurrences(text, e.text)
                else:
                    hits = re.finditer(rf"(?<![\w@.]){re.escape(e.text)}(?![\w@])", text)
                for m in hits:
                    span = m.span()
                    if any(_overlaps(span, t) for t in taken.get(bid, [])):
                        continue
                    if e.type in ("PERSON", "ORGANISATION") and any(_overlaps(span, p) for p in public.get(bid, [])):
                        continue
                    copy = e.model_copy(update={"id": f"ent_{uuid.uuid4().hex[:10]}", "block_id": bid, "start": span[0],
                                                "end": span[1], "text": m.group(), "surface_forms": list(e.surface_forms)})
                    added.append(copy)
                    taken.setdefault(bid, []).append(span)
        return added

    @staticmethod
    def _surface_forms(kept: List[DetectedEntity], assignment: Dict[str, PersonCluster]) -> None:
        for e in kept:
            forms = list(e.surface_forms or [e.text])
            if e.type == "PERSON":
                cl = assignment.get(e.id)
                forms += sorted(person_forms(cl.canonical_name if cl else e.text))
            elif e.type == "ORGANISATION":
                stem = org_stem(e.text)
                if stem != e.text:
                    forms.append(stem)
            e.surface_forms = list(dict.fromkeys(f for f in forms if f))

    # ------------------------------------------------------------------------------------------
    # 5. Overlap resolution
    # ------------------------------------------------------------------------------------------
    def _deduplicate_spans(self, entities: List[DetectedEntity], block_texts: Dict[str, str]) -> List[DetectedEntity]:
        """
        Resolve overlapping spans per block. Structured values (NI, DOB, references...) always win
        and can never be swallowed; a name span that runs into one is trimmed before it.
        """
        by_block: Dict[str, List[DetectedEntity]] = {}
        for ent in entities:
            by_block.setdefault(ent.block_id, []).append(ent)

        result: List[DetectedEntity] = []
        for block_id, ents in by_block.items():
            text = block_texts.get(block_id, "")
            structured = [e for e in ents if e.type in PATTERNS]
            cleaned: List[DetectedEntity] = []
            for ent in ents:
                if ent.type in PATTERNS:
                    cleaned.append(ent)
                    continue
                hit = next((s for s in structured if _overlaps((ent.start, ent.end), (s.start, s.end))), None)
                if hit is None:
                    cleaned.append(ent)
                elif ent.start < hit.start:
                    trimmed = text[ent.start:hit.start].strip()
                    if len(trimmed) >= 3 and trimmed.lower() not in ("dob", "date of birth", "date", "tel", "acc", "account"):
                        ent.end, ent.text = ent.start + len(trimmed), trimmed
                        cleaned.append(ent)

            cleaned.sort(key=lambda x: (x.start, 0 if x.type in PATTERNS else 1, -x.confidence, -(x.end - x.start)))
            merged: List[DetectedEntity] = []
            for ent in cleaned:
                if not merged or ent.start >= merged[-1].end:
                    merged.append(ent)
                    continue
                prev = merged[-1]
                if ent.end <= prev.end:                                   # enclosed
                    if ent.type in PATTERNS and prev.type not in PATTERNS:
                        merged[-1] = ent
                    elif ent.confidence > prev.confidence and (ent.start, ent.end) == (prev.start, prev.end):
                        merged[-1] = ent
                    else:
                        prev.surface_forms = list(dict.fromkeys(prev.surface_forms + [ent.text] + ent.surface_forms))
                    continue
                if prev.type in PATTERNS or ent.type in PATTERNS:          # partial overlap with a structured value
                    if prev.type in PATTERNS:
                        ent.start = prev.end
                        ent.text = text[ent.start:ent.end].strip()
                        if len(ent.text) >= 3:
                            merged.append(ent)
                    else:
                        prev.end = ent.start
                        prev.text = text[prev.start:prev.end].strip()
                        prev.end = prev.start + len(prev.text)
                        if len(prev.text) < 3:
                            merged[-1] = ent
                        else:
                            merged.append(ent)
                    continue
                # Partial overlap of two name spans: merge
                new_start, new_end = min(prev.start, ent.start), max(prev.end, ent.end)
                new_text = text[new_start:new_end] if text else ent.text
                org_word = has_org_indicator(prev.text) or has_org_indicator(ent.text)
                if org_word or "ORGANISATION" in (prev.type, ent.type):
                    dom_type, conf, tier = "ORGANISATION", max(prev.confidence, ent.confidence), ("confident" if org_word else "uncertain")
                else:
                    best = prev if prev.confidence >= ent.confidence else ent
                    dom_type, conf, tier = best.type, best.confidence, best.tier
                prev.surface_forms = list(dict.fromkeys(prev.surface_forms + ent.surface_forms + [new_text, prev.text, ent.text]))
                prev.start, prev.end, prev.text = new_start, new_end, new_text
                prev.type, prev.confidence, prev.tier = dom_type, conf, tier
            result.extend(merged)
        return result
