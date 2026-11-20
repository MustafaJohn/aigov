import re

from app.detector.names import NAME_TOKEN, PARTICLE_RE


def luhn_ok(value: str) -> bool:
    """Payment card check digit. A 16-digit number that fails it is a reference, not a card."""
    digits = [int(c) for c in value if c.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# UK and International PII regular expression patterns
PATTERNS = {
    "NI_NUMBER": {
        "regex": re.compile(r"\b(?:[A-CEGHJ-PR-TW-Z]{2}|QQ)\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.IGNORECASE),
        "label": "National Insurance No.",
    },
    "SORT_CODE": {
        # UK Sort Code: hyphenated pairs (e.g. 20-45-12) or explicit sort code context (avoids misclassifying dates like 12 03 26)
        "regex": re.compile(r"(?i:\b(?:sort\s+code|s\/c)\s*[:\-–]?\s*)(\d{2}[-\s]\d{2}[-\s]\d{2})\b|\b(\d{2}-\d{2}-\d{2})\b"),
        "label": "Sort Code",
    },
    "ACCOUNT_NUMBER": {
        # Require bank/account context: Account, Account Number, Account No, A/C, Bank Acc
        "regex": re.compile(r"(?i:\b(?:acc(?:ount)?(?:\s+(?:no\.?|number))?|a\/c|bank\s+acc(?:ount)?)\s*[:#\-|]?\s*)(\d{8,10})\b"),
        "label": "Bank Account No.",
    },
    "CREDIT_CARD": {
        "regex": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        "label": "Card Number",
        "validate": luhn_ok,
    },
    "UK_POSTCODE": {
        "regex": re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE),
        "label": "UK Postcode",
    },
    "PHYSICAL_ADDRESS": {
        "regex": re.compile(
            r"\b\d{1,4}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Street|Road|Avenue|Lane|Drive|Grove|Way|Close|Gardens|Court|Boulevard|Hill|Walk|Terrace|Square|Crescent)(?:,\s*[A-Z][a-z]+)?\b"
        ),
        "label": "Street Address",
    },
    "EMAIL": {
        "regex": re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b"),
        "label": "Email Address",
    },
    "PHONE": {
        "regex": re.compile(
            r"(?<![\w£$€])(?:"
            # 1. UK Mobile & Landline: +44, 0044 (with optional (0)), or domestic 0
            r"(?:(?:\+44|0044)[\s.-]?(?:\(0\)[\s.-]?)?|0)"
            r"(?:"
            r"7\d{3}[\s.-]?\d{3}[\s.-]?\d{3}"           # 07xxx xxx xxx (UK mobile)
            r"|7\d{3}[\s.-]?\d{6}"                      # 07xxx xxxxxx (UK mobile standard)
            r"|7\d{2}[\s.-]?\d{3}[\s.-]?\d{4}"          # 07xx xxx xxxx (UK mobile)
            r"|7\d{8,9}"                                # 07xxxxxxxxx (UK mobile compact)
            r"|2\d[\s.-]?\d{4}[\s.-]?\d{4}"             # 020 xxxx xxxx (London)
            r"|1\d{2,4}[\s.-]?\d{3,4}[\s.-]?\d{3,4}"   # 01xxx xxxxxx (UK Geographic)
            r"|1\d{8,9}"                                # 01xxxxxxxxx (compact geographic)
            r"|3\d{2}[\s.-]?\d{3,4}[\s.-]?\d{3,4}"     # 03xx xxx xxxx (UK Business)
            r"|800[\s.-]?\d{3,4}[\s.-]?\d{3,4}"        # 0800 xxx xxxx (UK Freephone)
            r"|8\d{2}[\s.-]?\d{3,4}[\s.-]?\d{3,4}"     # 08xx xxx xxxx (UK Special)
            r")"
            # 2. Bracketed UK area / mobile codes: (07xxx) xxxxxx, (020) xxxx xxxx, (01xxx) xxxxxx
            r"|\((?:07\d{3}|02\d|01\d{2,4})\)[\s.-]?\d{3,4}[\s.-]?\d{3,4}"
            # 3. International format (+ followed by country code and 7-15 grouped digits)
            r"|\+[1-9]\d{0,2}[\s.-]?(?:\(\d{1,4}\)[\s.-]?)?(?:\d{1,4}[\s.-]?){2,4}\d{2,4}"
            # 4. North American NANP: (xxx) xxx-xxxx, xxx-xxx-xxxx, +1-xxx-xxx-xxxx
            r"|(?:\+?1[\s.-]?)?\(\d{3}\)[\s.-]?\d{3}[\s.-]?\d{4}"
            r"|(?:\+?1[\s.-])?\d{3}[.-]\d{3}[.-]\d{4}"
            r"|\+1[\s.-]\d{3}[\s.-]\d{3}[\s.-]\d{4}"
            r")(?![\w£$€])"
            # 5. Labelled phone or mobile numbers (group 1 extracts phone value)
            r"|(?i:\b(?:tel(?:ephone)?|phone|mob(?:ile)?|cell(?:phone)?|contact(?:\s+(?:no|number|details))?|whats\s?app|direct\s+dial|direct\s+line|d\.d\.|fax|ph)\b\.?"
            r"\s*(?:no\b\.?|number|num)?\s*[:\-–]?\s*)"
            r"((?:\+?\d{1,4}[\s.-]?)?(?:\(?\d{2,5}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?:[\s.-]?\d{1,4})?)"
        ),
        "label": "Phone Number",
    },
    "PASSPORT": {
        "regex": re.compile(r"(?i:\b(?:passport|ppt|passport\s+no\.?|passport\s+number)\s*[:#\-–]?\s*)([A-Z0-9]{8,10})\b"),
        "label": "Passport Number",
    },
    "DRIVING_LICENCE": {
        "regex": re.compile(r"(?i:\b(?:driving\s+licence|driver\s+licence|licence\s+no\.?)\s*[:#-]?\s*)([A-Z0-9\s]{8,18})\b|\b([A-Z]{5}\d{6}[A-Z0-9]{5})\b"),
        "label": "Driving Licence No.",
    },
    "MATTER_REF": {
        # Matter references: uppercase legal prefixes (MAT, REF, CLM, FILE, CAS, CASE, ACT, EMP) or uppercase law firm initials with year/number (e.g. KB/2026/0912)
        # HMCTS claim numbers (KB-2026-000123, CL-2025-000045) are publicly searchable and identify the matter.
        "regex": re.compile(r"\b(?:(?:MAT|REF|CLM|FILE|CAS|CASE|ACT|EMP)[\/-][A-Za-z0-9\/-]{4,15}|[A-Z]{2,4}[\/-]\d{4}[\/-][A-Za-z0-9\/-]{3,10}|[A-Z]{1,3}\d{0,2}-\d{4}-\d{6})\b"),
        "label": "Matter/Case Ref",
    },
    "REFERENCE": {
        # Personal reference numbers, defined by shape rather than by scheme so unseen schemes are covered:
        #   1. a labelled value: "Policy number: PX-77120-B", "Booking ref: 8KQ2ZT", "UAN 3434-..."
        #   2. letters then 6+ digits: IHS204518736, GWF071234567, BRP ZU1234567, IHSC..., NHS-style prefixes
        #   3. four groups of four digits that fail the card check (UAN 3434-0459-5933-5592)
        #   4. exhibit marks (MP/1), which are the witness's initials
        # Values must contain a digit, so "reference to Article 3" or "Ref: see above" never match.
        "regex": re.compile(
            r"(?i:\b(?:(?:reference|ref|application|policy|claim|case|booking|customer|client|patient|membership|"
            r"transaction|order|invoice|payment|account\s+ref|visa\s+application|certificate|registration|licence|permit)\s*(?:no\b\.?|number|num|id|ref(?:erence)?\b)?|"
            r"UAN|GWF|BRP(?:\s+(?:no\b\.?|number))?|UTR|NHS(?:\s+(?:no\b\.?|number|id))?)\.?\s*(?:is\s+)?[:#]?\s*)"
            r"((?=[A-Z0-9\-/.\s]*\d)[A-Z0-9][A-Z0-9\-/.]{2,10}\s+\d{6,12}[A-Z]?|(?=[A-Z0-9\-/.]*\d)[A-Z0-9][A-Z0-9\-/.]{4,24}[A-Z0-9]|\d{3}[\s.-]?\d{3}[\s.-]?\d{4})(?![\w-])"
            r"|\b(?:IHS|GWF|BRP|UAN|UTR)[-\s]?\d{6,12}[A-Z]?\b"
            r"|\b[A-Z]{2,5}\d{6,12}[A-Z]?\b"
            r"|\b\d{4}(?:[-\s]\d{4}){3}\b"
            r"|\b[A-Z]{2,3}/\d{1,3}\b(?!/)"          # exhibit marks carry the witness's initials: MP/1, JRS/12
        ),
        "label": "Reference Number",
    },
    "MONETARY_AMOUNT": {
        "regex": re.compile(r"(?:£|\$|€)\s?\d+(?:,\d{3})*(?:\.\d{2})?(?:\s*(?:million|billion|thousand|k|m))?\b", re.IGNORECASE),
        "label": "Financial Amount",
    },
    "DATE_OF_BIRTH": {
        "regex": re.compile(
            r"(?i:\b(?:DOB|D\.O\.B\.|Date\s+of\s+Birth|birth\s+date|born(?:\s+on)?(?:\s+the)?)\s*(?:is\s+)?[:\-–]?\s*)"
            r"(\d{4}[-\/.]\d{1,2}[-\/.]\d{1,2}|\d{1,2}[-\/.]\d{1,2}[-\/.]\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]+\d{2,4})\b"
        ),
        "label": "Date of Birth",
    }
}

# Placeholder prefix per entity type: what the LLM sees, e.g. [PERSON 1], [REF 2]
PLACEHOLDER_PREFIX = {
    "PERSON": "PERSON", "ORGANISATION": "ORG", "NI_NUMBER": "NI NUMBER", "SORT_CODE": "SORT CODE",
    "ACCOUNT_NUMBER": "ACCOUNT", "CREDIT_CARD": "CARD", "UK_POSTCODE": "POSTCODE", "PHYSICAL_ADDRESS": "ADDRESS",
    "EMAIL": "EMAIL", "PHONE": "PHONE", "PASSPORT": "PASSPORT", "DRIVING_LICENCE": "DRIVING LICENCE",
    "MATTER_REF": "MATTER", "MONETARY_AMOUNT": "AMOUNT", "DATE_OF_BIRTH": "DATE", "REFERENCE": "REF",
}
# Only placeholders this system issues are treated as already masked; "[JOHN SMITH]" is not a placeholder.
PLACEHOLDER_REGEX = re.compile(r"\[(?:" + "|".join(sorted(set(PLACEHOLDER_PREFIX.values()), key=len, reverse=True)) + r") \d+\]")

_NAME = NAME_TOKEN
_NAME_SEQ = rf"{_NAME}(?:[ \t]+(?:{PARTICLE_RE}[ \t]+)*{_NAME}){{0,2}}"

# Honorific + name: "Mrs Patel", "Dr Anne-Marie O'Neill", "Ms Ní Bhriain", "Mr van der Berg"
PERSON_TITLES_REGEX = re.compile(
    rf"\b(?:Mr\.?|Mrs\.?|Ms\.?|Miss|Dr\.?|Prof\.?|Lord|Lady|Sir|Dame|Justice|Judge|Baroness|Master|Hon\.?)[ \t]+(?:{PARTICLE_RE}[ \t]+)*{_NAME_SEQ}(?!\w)"
)

# A deceased person: "the late Margaret Anne Foster", "Deceased: John Smith"
LATE_PERSON_REGEX = re.compile(rf"(?i:\bthe\s+late|\bdeceased\s*:)[ \t]+({_NAME_SEQ})(?!\w)")

# Given name + particle surname spaCy misses: "Siobhan Ní Bhriain", "Pieter van der Berg"
PARTICLE_NAME_REGEX = re.compile(rf"\b{_NAME}[ \t]+(?:{PARTICLE_RE}[ \t]+)+{_NAME}(?!\w)")

# Surname-first court/hearing lists: "SMITH, John", "PATEL, Meena Kumari". Surname must be in capitals.
SURNAME_FIRST_REGEX = re.compile(rf"\b([A-ZÀ-Þ]{{2,}}(?:[-'’][A-ZÀ-Þ]{{2,}})?),[ \t]+({_NAME}(?:[ \t]+{_NAME})?)(?!\w)")

# Company & organisation names ending in a legal/organisational suffix
COMPANY_REGEX = re.compile(
    r"\b(?!(?:UK\s+)?National\s+Insurance)(?:(?:[A-Z][A-Za-z0-9'.-]+|&|\([A-Z][A-Za-z0-9 '&.-]*\))[ \t]+){1,5}(?:LLP|Ltd\.?|LTD|Limited|LIMITED|PLC|plc|LLC|Inc\.?|Corp\.?|Corporation|Holdings|Partners|Chambers|Solicitors|Law\s+Firm|Assurance|Insurance|Group|School|Primary\s+School|Secondary\s+School|Academy|College|University|Hospital|Clinic|Care\s+Home|Council|Association|Agency|Trust|Foundation|Centre|Center|Factory|Systems)\b"
)

# Major UK banks (public institutions; masked because they reveal where a client banks)
BANK_REGEX = re.compile(
    r"\b(?:Barclays(?:\s+Bank)?(?:\s+PLC)?|HSBC(?:\s+Bank)?(?:\s+PLC)?|Lloyds(?:\s+Bank)?(?:\s+PLC)?|NatWest(?:\s+Bank)?|Santander|Standard\s+Chartered)\b",
    re.IGNORECASE
)

# ---------------------------------------------------------------------------------------------
# Public legal references. These are never confidential, and masking them destroys the analysis
# ("Directive [ORG 142][ORG 7]"). Spans matching here are excluded from NER-based detection.
# Structured PII (NI, emails, reference numbers...) is never excluded.
# ---------------------------------------------------------------------------------------------
_DASH = r"[\-‐‑–]"
PUBLIC_LEGAL_REFERENCE_REGEX = re.compile(
    r"\b(?:Council\s+|Commission\s+)?(?:Directive|Regulation|Decision|Framework\s+Decision)\s+(?:\((?:EU|EC|EEC|Euratom)\)\s+)?(?:No\.?\s+)?\d{1,4}/\d{1,4}(?:/(?:EU|EC|EEC|Euratom|JHA))?\b"
    r"|\b(?:ECLI:)?[A-Z]{2}:[A-Z]{1,5}:\d{4}:\d+\b"                                   # ECLI:EU:C:2018:551, EU:C:2018:335
    rf"|\b(?:Case\s+)?[CTF]{_DASH}\d{{1,4}}/\d{{2}}(?:\s*P)?\b"                         # C-25/17, C‑426/16, T-1/99
    r"|\[\d{4}\]\s+(?:UKSC|UKPC|UKHL|EWCA\s+(?:Civ|Crim)|EWHC|EWFC|EWCOP|UKUT|UKFTT|UKEAT|EAT|CSIH|CSOH|NICA|NIQB)\s+\d+(?:\s*\([A-Za-z]+\))?"
    r"|\[\d{4}\]\s+\d{0,2}\s*(?:AC|QB|KB|Ch|Fam|WLR|All\s+ER|ICR|IRLR|BCLC|Cr\s+App\s+R)\s+\d+"
    r"|\bOJ\s+\d{4}\s+[LC]\s+\d+"
    r"|\b(?:[A-Z][a-z]+\s+){1,6}(?:Act|Order|Rules|Regulations)\s+\d{4}\b"
    r"|\bArticles?\s+\d+[a-z]?(?:\(\d+\))?(?:\([a-z]\))?"
    # Court titles: "IN THE COUNTY COURT AT MANCHESTER", "Family Court sitting at Leeds"
    r"|(?i:\b(?:county|crown|high|family|magistrates['’]?|supreme|civil\s+justice)\s+(?:court|centre)(?:\s+of\s+justice)?(?:\s+(?:at|in|of|sitting\s+at))?)\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?"
)

# Supranational and parliamentary institutions; never client parties
PUBLIC_INSTITUTION_REGEX = re.compile(
    r"\b(?:(?:the\s+)?(?:European\s+(?:Union|Parliament|Commission|Council|Court\s+of\s+Human\s+Rights|Convention(?:\s+[a-z]+){0,3}\s+(?:on|for)\s+[A-Z][\w\s]+?Rights(?:\s+and\s+Fundamental\s+Freedoms)?))"
    r"|Council\s+of\s+(?:the\s+European\s+Union|Europe)|United\s+Nations|Court\s+of\s+Justice(?:\s+of\s+the\s+European\s+Union)?"
    r"|Charter\s+of\s+Fundamental\s+Rights(?:\s+of\s+the\s+European\s+Union)?|(?:Grand|First|Second|Third|Fourth|Fifth)\s+Chamber"
    r"|EU|UN|EEA|EFTA)\b"
)

# A foreign or unfamiliar body name followed by its English gloss, as judgments write them:
#   "the Korkein hallinto-oikeus (Supreme Administrative Court)"
#   "the Tietosuojavaltuutettu (Data Protection Supervisor, Finland)"
# The gloss must itself be a body name: capitalised words ending in Court/Tribunal, or in an
# authority head noun followed by ", <Country>". A person's role in brackets never qualifies.
GLOSSED_PUBLIC_BODY_REGEX = re.compile(
    r"(?<![A-Za-z])([A-Za-zÀ-ÿ][\w’'\-]*(?:[ \t]+[a-zà-ÿ][\w’'\-]*){0,3})[ \t]*"
    r"\(((?:[A-Z][a-z]+[ \t]+){0,4}(?:Court|Tribunal)(?:,[ \t]*[A-Z][a-z]+)?"
    r"|(?:[A-Z][a-z]+[ \t]+){0,4}(?:Supervisor|Authority|Board|Commissioner|Ombudsman|Ministry|Regulator|Office),[ \t]*[A-Z][a-z]+)\)"
)

# Party names inside a citation of a reported case are public record:
#   "(judgment of 29 May 2018, Liga van ... VZW and Others, C-426/16, ...)"   (CJEU style)
#   "Smith v Jones [2019] EWCA Civ 123"                                       (UK style)
# The UK form takes only the unbroken run of capitalised words around "v", so in
# "My client John Doe relies on Smith v Jones [2019] ..." the client's name is not included.
CITED_CASE_NAME_REGEX = re.compile(
    rf"judgment\s+of\s+\d{{1,2}}\s+[A-Z][a-z]+\s+\d{{4}},\s+([^,;()]{{3,200}}),\s+(?:Case\s+)?[CTF]{_DASH}\d{{1,4}}/\d{{2}}"
    r"|((?:[A-Z][\w’'.&-]*[ \t]+){1,5}v\.?[ \t]+(?:[A-Z][\w’'.&-]*[ \t]+){1,5})\[\d{4}\]"
)
