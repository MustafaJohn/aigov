"""
Shared name logic for the detector and the outbound guard.

One place for: honorifics, surname particles, organisation suffixes, how a person mention is
parsed, which alias forms a name has, and how a form is matched in text. The engine and the
guard previously each had their own copy and they disagreed (see review issue 36).

Everything here is generic English/UK legal-drafting vocabulary. No client, matter or test
document values belong in this file.
"""
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set

# Honorific -> gender hint ("U" = unknown)
TITLE_GENDER = {
    "mr": "M", "lord": "M", "sir": "M", "master": "M",
    "mrs": "F", "ms": "F", "miss": "F", "lady": "F", "dame": "F", "baroness": "F",
    "dr": "U", "prof": "U", "justice": "U", "judge": "U", "hon": "U",
}

# Lower-case surname particles: van der Berg, de Souza, Ní Bhriain, bin Rashid
PARTICLES = {"van", "von", "der", "den", "de", "da", "di", "du", "del", "della", "le", "la",
             "ní", "nic", "mac", "ó", "ua", "uí", "bin", "bint", "al", "el", "ap"}

# Words that mark a span as an organisation. Matched as whole words, never substrings
# ("inc" must not fire on "Vincent", "bank" not on "Fairbanks").
ORG_SUFFIXES = (
    "llp", "ltd", "limited", "plc", "llc", "inc", "corp", "corporation", "holdings", "partners",
    "chambers", "solicitors", "law firm", "bank", "school", "academy", "college", "university",
    "hospital", "clinic", "care home", "council", "association", "agency", "trust", "foundation",
    "centre", "center", "factory", "systems", "logistics", "services", "group",
)
_SUFFIX_ALT = "|".join(re.escape(s).replace(r"\ ", r"\s+") + "s?" for s in ORG_SUFFIXES)
_ORG_SUFFIX_RE = re.compile(r"\b(?:" + _SUFFIX_ALT + r")\b\.?", re.I)
_ORG_TRAILING_SUFFIX_RE = re.compile(r"(?:\s+\b(?:" + _SUFFIX_ALT + r")\b\.?)+$", re.I)

# One Unicode-aware name token: Siobhán, Ní, O'Neill, Adebayo-Clarke, D'Souza
NAME_TOKEN = r"[A-ZÀ-ÖØ-Þ][a-zß-öø-ÿ]*(?:['’][A-ZÀ-ÖØ-Þ]?[a-zß-öø-ÿ]+)?(?:-[A-ZÀ-ÖØ-Þ][a-zß-öø-ÿ'’]+)?"
PARTICLE_RE = r"(?i:" + "|".join(sorted((re.escape(p) for p in PARTICLES), key=len, reverse=True)) + r")"


def has_org_indicator(text: str) -> bool:
    return bool(_ORG_SUFFIX_RE.search(text))


def org_stem(text: str) -> str:
    """'Halden Logistics Ltd' -> 'Halden'. Returns the input if stripping leaves < 3 chars."""
    stem = _ORG_TRAILING_SUFFIX_RE.sub("", text.strip()).strip(" ,.&")
    stem = re.sub(r"(?i)^the\s+", "", stem)
    return stem if len(stem) >= 3 and stem.lower() not in _LEADING_NOISE else text.strip()


def is_all_caps(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


def name_case(s: str) -> str:
    """Canonical display case for a name token that arrived in capitals (SMITH -> Smith)."""
    return s.title() if is_all_caps(s) else s


@dataclass
class PersonName:
    raw: str
    clean: str
    honorific: Optional[str] = None
    first: Optional[str] = None
    middle: List[str] = field(default_factory=list)
    surname: Optional[str] = None
    initial: Optional[str] = None
    gender: str = "U"
    is_full: bool = False


_LEADING_NOISE = {"the", "a", "an", "this", "that", "in", "for", "with", "from", "and", "or"}


def parse_person(text: str) -> PersonName:
    """
    Split a mention into honorific / first / middle / surname. Handles surname-first lists
    ("SMITH, John"), multi-word surnames with particles ("van der Berg", "Ní Bhriain") and
    capitals ("JOHN ALDRIDGE" -> John / Aldridge).
    """
    raw = text.strip()
    if raw.count(",") == 1:                              # "SMITH, John" -> "John SMITH"
        left, right = (p.strip() for p in raw.split(","))
        if left and right and is_all_caps(left):
            raw_order = f"{right} {left}"
        else:
            raw_order = raw.replace(",", " ")
    else:
        raw_order = raw
    words = raw_order.split()
    honorific, gender = None, "U"
    if words and words[0].strip(".,").lower() in TITLE_GENDER:
        honorific = words[0].strip(".,")
        gender = TITLE_GENDER[honorific.lower()]
        words = words[1:]

    tokens = [w.strip(".,") for w in words if w.strip(".,")]
    while tokens and tokens[0].lower() in _LEADING_NOISE:
        tokens.pop(0)
    if not tokens:
        return PersonName(raw=raw, clean=raw, honorific=honorific, gender=gender)

    tokens = [name_case(t) for t in tokens]
    conjoined = any(t.lower() in ("and", "or", "&", "v", "vs") for t in tokens)

    # Surname = last token plus any particles directly before it
    s_idx = len(tokens) - 1
    while s_idx > 0 and tokens[s_idx - 1].lower() in PARTICLES:
        s_idx -= 1
    surname = " ".join(tokens[s_idx:])
    given = tokens[:s_idx]

    first = initial = None
    middle: List[str] = []
    is_full = bool(given) and not conjoined
    if is_full:
        if len(given[0]) == 1:
            initial = given[0].upper()
        else:
            first = given[0]
            initial = first[0].upper()
        middle = given[1:]

    return PersonName(raw=raw, clean=" ".join(tokens), honorific=honorific, first=first, middle=middle,
                      surname=surname, initial=initial, gender=gender, is_full=is_full)


def person_forms(text: str) -> Set[str]:
    """Every way the same person is commonly written. Used to mask aliases and by the guard."""
    p = parse_person(text)
    forms: Set[str] = {text.strip(), p.clean}
    if p.surname and len(p.surname.replace(" ", "")) >= 3:
        forms.add(p.surname)
        for t in ("Mr", "Mrs", "Ms", "Miss", "Dr"):
            forms.update({f"{t} {p.surname}", f"{t}. {p.surname}"})
        if p.first:
            forms.add(f"{p.first} {p.surname}")
            if len(p.first) >= 3:
                forms.add(p.first)
        if p.initial:
            forms.update({f"{p.initial}. {p.surname}", f"{p.initial}.{p.surname}", f"{p.initial} {p.surname}"})
            if p.middle:
                m = p.middle[0][0]
                forms.update({f"{p.initial}. {m}. {p.surname}", f"{p.initial}.{m}. {p.surname}"})
    return {f for f in forms if f and len(f) >= 2}


ORDINARY_NAME_WORDS = {
    "grant", "will", "rose", "may", "hope", "grace", "march", "brown", "white", "green",
    "major", "bill", "mark", "dean", "field", "ward", "lane", "short", "long", "young", "cross"
}


def is_strong_form(form: str, entity_text: str, context: str = "") -> bool:
    """
    A multi-word form, or the entity's own text, identifies the person on its own and is a hard
    block in the guard. A bare first name or surname that is also an ordinary dictionary word
    ('Grant', 'Will') or part of a legal phrase ('Grant of probate') goes to the lawyer as a
    review item instead. Distinctive single-word surnames ('Vance', 'Aldridge') are hard blocks.
    """
    form_clean = form.strip()
    if form_clean == entity_text.strip() or len(form_clean.split()) >= 2:
        return True
    if context and re.search(rf"\b{re.escape(form_clean)}\s+of\b", context, re.IGNORECASE):
        return False
    if form_clean.lower() in ORDINARY_NAME_WORDS:
        return False
    p = parse_person(entity_text)
    if p.surname and form_clean.lower() == p.surname.lower():
        return True
    return False


def name_occurrences(text: str, form: str) -> Iterable[re.Match]:
    """
    Occurrences of a name form on word boundaries, in its own case or in ALL CAPITALS.
    Lower-case prose never matches ('rose', 'grant', 'will'), capitalised headings always do
    ('BETWEEN: JOHN ALDRIDGE').
    """
    form = form.strip()
    if len(form) < 2:
        return
    for m in re.finditer(rf"(?<!\w){re.escape(form)}(?!\w)", text, re.IGNORECASE):
        if m.group() == form or m.group().isupper():
            yield m


def name_in(text: str, form: str) -> bool:
    return next(iter(name_occurrences(text, form)), None) is not None


_ADDRESSES = re.compile(r"\S+@\S+|https?://\S+|www\.\S+|\S+\.(?:com|org|net|uk|gov|io)\S*", re.IGNORECASE)


def lowercase_words(text: str) -> Set[str]:
    """
    Words that appear in lower case in running prose (used to spot ordinary words). Email
    addresses and URLs are excluded: 'robert.foster@...' must not make 'Foster' look ordinary.
    """
    prose = _ADDRESSES.sub(" ", text)
    return set(re.findall(r"(?<![\w\-.@/])[a-zß-öø-ÿ]{3,}(?![\w\-@])", prose))
