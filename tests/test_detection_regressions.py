"""
Regression suite for detection + outbound gate. Run:  pytest tests/test_detection_regressions.py -q

Three invariants are checked for every case:
  1. must_mask:      every occurrence of the string is inside a detected span
  2. must_not_mask:  no detected span touches the string
  3. gate parity:    masking every detected span and running the outbound guard PASSES.
                     If this fails, the lawyer sees "Security gate blocked dispatch" on a
                     document the tool itself redacted (lawyer test, IHS email).
"""
import os, re, sys
try:
    import pytest
except ImportError:
    class _MockPytest:
        class mark:
            @staticmethod
            def parametrize(*args, **kwargs):
                def decorator(fn):
                    return fn
                return decorator
    pytest = _MockPytest()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from app.parser.intake import intake_file                      # noqa: E402
from app.detector.engine import DetectionEngine                # noqa: E402
from app.guard.checker import GuardEngine                      # noqa: E402
from app.models import OutboundCheckRequest                    # noqa: E402
from detection_cases import CASES, SAME_PERSON, DIFFERENT_PEOPLE  # noqa: E402

ENGINE = DetectionEngine()
_cache = {}


def run(case):
    if case["name"] not in _cache:
        ir = intake_file(f"{case['name']}.txt", case["text"].encode("utf-8"))
        _cache[case["name"]] = (ir, ENGINE.detect(ir))
    return _cache[case["name"]]


def occurrences(text, s):
    return [(m.start(), m.end()) for m in re.finditer(re.escape(s), text)]


def spans_by_block(det):
    out = {}
    for e in det.entities:
        out.setdefault(e.block_id, []).append(e)
    return out


def protected_text(ir, det):
    """What the review screen sends: every block with every detected span replaced by its placeholder."""
    by_block = spans_by_block(det)
    parts = []
    for b in ir.blocks:
        t = b.text
        for e in sorted(by_block.get(b.id, []), key=lambda e: e.start, reverse=True):
            t = t[:e.start] + e.placeholder + t[e.end:]
        parts.append(t)
    return "\n\n".join(parts)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_must_mask(case):
    ir, det = run(case)
    by_block = spans_by_block(det)
    missed = []
    for s in case["must_mask"]:
        for b in ir.blocks:
            for (a, z) in occurrences(b.text, s):
                if not any(e.start <= a and z <= e.end for e in by_block.get(b.id, [])):
                    missed.append(f"{s!r} in {b.id}")
    assert not missed, f"unmasked: {missed}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_must_not_mask(case):
    ir, det = run(case)
    by_block = spans_by_block(det)
    wrong = []
    for s in case["must_not_mask"]:
        for b in ir.blocks:
            for (a, z) in occurrences(b.text, s):
                hits = [e for e in by_block.get(b.id, []) if e.start < z and a < e.end]
                wrong += [f"{s!r} hit by {e.type}:{e.text!r}" for e in hits]
    assert not wrong, f"over-masked: {wrong}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_gate_parity(case):
    ir, det = run(case)
    res = GuardEngine.check_outbound(OutboundCheckRequest(
        doc_id=ir.doc_id, protected_text=protected_text(ir, det),
        active_entities=det.entities, user_prompt="Summarise this document."))
    assert res.passed, f"gate blocked its own redaction: {res.leaked_items[:5]}"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_type_matches_placeholder(case):
    _, det = run(case)
    bad = [(e.text, e.type, e.placeholder) for e in det.entities
           if (e.type == "PERSON") != e.placeholder.startswith("[PERSON")
           or (e.type == "ORGANISATION") != e.placeholder.startswith("[ORG")]
    assert not bad, bad


def _placeholder(case_name, text):
    case = next(c for c in CASES if c["name"] == case_name)
    _, det = run(case)
    hits = {e.placeholder for e in det.entities if e.text == text}
    assert hits, f"{text!r} not detected"
    return hits


@pytest.mark.parametrize("case_name,a,b", SAME_PERSON)
def test_same_person(case_name, a, b):
    assert _placeholder(case_name, a) == _placeholder(case_name, b)


@pytest.mark.parametrize("case_name,a,b", DIFFERENT_PEOPLE)
def test_different_people(case_name, a, b):
    assert not (_placeholder(case_name, a) & _placeholder(case_name, b))


# ---------------- Outbound guard ----------------
from app.models import DetectedEntity  # noqa: E402


def _ent(text, typ="PERSON", ph="[PERSON 1]"):
    return DetectedEntity(id="e", block_id="b", start=0, end=len(text), text=text, type=typ, placeholder=ph)


def _check(doc, ents, prompt=""):
    return GuardEngine.check_outbound(OutboundCheckRequest(doc_id="d", protected_text=doc, active_entities=ents, user_prompt=prompt))


def test_guard_blocks_all_caps_name():
    assert not _check("BETWEEN: JOHN ALDRIDGE Claimant", [_ent("John Aldridge")]).passed


def test_guard_blocks_bracketed_name_and_ni():
    assert not _check("Witness: [JOHN ALDRIDGE]", [_ent("John Aldridge")]).passed
    assert not _check("NI: [AB 12 34 56 C]", []).passed


def test_guard_ignores_issued_placeholders():
    assert _check("[PERSON 1] wrote to [ORG 2].", [_ent("John Aldridge"), _ent("Acme Ltd", "ORGANISATION", "[ORG 2]")]).passed


@pytest.mark.parametrize("raw", ["DOB: 01/02/1985", "Lives at BS1 4DJ", "Ref IHS204518736"])
def test_guard_structured_without_entities(raw):
    assert not _check(raw, []).passed


def test_guard_single_word_alias_is_review_not_block():
    res = _check("[PERSON 1] applied. Grant of probate was issued.", [_ent("Rose Grant")])
    assert res.passed and res.review_items


def test_guard_does_not_flag_lowercase_words():
    assert _check("Prices rose after the grant.", [_ent("Rose Grant")]).passed


if __name__ == "__main__":
    print("=" * 70)
    print("RUNNING DETECTION REGRESSION SUITE")
    print("=" * 70)
    for case in CASES:
        print(f"[CASE] Testing {case['name']}...")
        test_must_mask(case)
        test_must_not_mask(case)
        test_gate_parity(case)
        test_type_matches_placeholder(case)
    for case_name, a, b in SAME_PERSON:
        test_same_person(case_name, a, b)
    for case_name, a, b in DIFFERENT_PEOPLE:
        test_different_people(case_name, a, b)
    test_guard_blocks_all_caps_name()
    test_guard_blocks_bracketed_name_and_ni()
    test_guard_ignores_issued_placeholders()
    for raw in ["DOB: 01/02/1985", "Lives at BS1 4DJ", "Ref IHS204518736"]:
        test_guard_structured_without_entities(raw)
    test_guard_single_word_alias_is_review_not_block()
    test_guard_does_not_flag_lowercase_words()
    print("=" * 70)
    print("ALL DETECTION REGRESSION SUITE CASES PASSED!")
    print("=" * 70)
