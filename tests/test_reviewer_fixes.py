"""
test_reviewer_fixes.py - Verification tests for reviewer feedback.

Covers:
Part 1:
1. One person gets one placeholder (Jonathan Vance, Mrs/Ms O'Connor)
2. Alias regex case-sensitivity (no masking 'rose', 'grant', 'a Vance' not absorbing 'a')
3. Shared surnames marked uncertain (bare 'Smith' with John & Jane Smith)
4. Organisations without indicator words retained as uncertain (Northwind, Deloitte)
5. Line breaks split multiple persons (Aisha Rahman\\n- Kemi Adeyemi)
6. Offset calculation exact after character stripping
7. Span overlap deduplication merges covering spans (no trailing leak)
8. First names included in surface_forms and detected as uncertain aliases
9. Confidence and tier inheritance (single-word uncertain entities don't seed confident aliases)

Part 2 (New Reviewer Feedback):
10. Marcus Sterling (Executive) gets [PERSON 1] (not [ORG 1])
11. Morgan Stanley is NOT turned into a person when Morgan Lee is present
12. Role regex catches non-names (Director: Human Resources not a confident person)
13. First names alone share established person's placeholder ([PERSON 1])
14. Ambiguous Mrs Patel marked uncertain (not a confident third person)
15. Initial matching (P. Smith resolves to Peter Smith)
16. Halden stem derived for Halden Logistics and checked by guard
17. Structured values not swallowed by uncertain org span (DOB 01/02/1985)
18. Guard blocks raw PII even when active_entities is empty
19. Guard does NOT block lowercase ordinary words (rose, grant, will, grace, hope)
20. Phone with +44 (0) matched
"""

import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = WORKSPACE_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import DocumentIR, Block, SourceInfo, ParseReport, DetectedEntity, OutboundCheckRequest
from app.detector.engine import DetectionEngine
from app.guard.checker import GuardEngine


def make_doc_ir(text: str, doc_id: str = "test_doc") -> DocumentIR:
    return DocumentIR(
        doc_id=doc_id,
        source=SourceInfo(format="txt", filename="test.txt", size_bytes=len(text), sha256="abc", pages_or_sheets=1),
        blocks=[Block(id="b1", text=text, visibility="visible")],
        report=ParseReport(status="READY", summary="OK", total_blocks=1)
    )


# --- Part 1 Tests ---

def test_issue_1_single_placeholder_per_person():
    """Issue 1: Jonathan Vance, Mr. Jonathan Vance, Mr Vance, J. Vance must share ONE placeholder."""
    engine = DetectionEngine()
    text = (
        "Mr. Jonathan Vance attended the hearing. Jonathan Vance agreed to the settlement terms. "
        "Later, Mr Vance signed the document. J. Vance confirmed by email. Vance then departed. "
        "Mrs O'Connor spoke on behalf of Ms O'Connor regarding Siobhan O'Connor's claim."
    )
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    vance_ents = [e for e in res.entities if "Vance" in e.text]
    assert len(vance_ents) >= 4, f"Expected >= 4 Vance entities, got {len(vance_ents)}"
    vance_placeholders = {e.placeholder for e in vance_ents}
    assert len(vance_placeholders) == 1, f"Expected exactly 1 placeholder for Vance, got: {vance_placeholders}"
    assert "[PERSON 1]" in vance_placeholders

    oconnor_ents = [e for e in res.entities if "O'Connor" in e.text or "Siobhan" in e.text]
    oconnor_placeholders = {e.placeholder for e in oconnor_ents}
    assert len(oconnor_placeholders) == 1, f"Expected Mrs and Ms O'Connor to share 1 placeholder, got: {oconnor_placeholders}"
    print("[PASS] Issue 1: One person gets one consistent placeholder across all variations.")


def test_issue_2_alias_case_sensitivity_and_articles():
    """Issue 2: Surnames matched case-sensitively; ordinary words like 'rose'/'grant' not masked; 'a Vance' doesn't absorb 'a'."""
    engine = DetectionEngine()
    text = (
        "The witness Marcus Grant stated that he saw a rose in the garden. "
        "They did not grant permission to enter. He spoke with a Vance representative."
    )
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    lower_rose = [e for e in res.entities if e.text == "rose"]
    lower_grant = [e for e in res.entities if e.text == "grant"]
    assert len(lower_rose) == 0, f"False positive: 'rose' was detected: {lower_rose}"
    assert len(lower_grant) == 0, f"False positive: 'grant' was detected: {lower_grant}"

    a_vance = [e for e in res.entities if e.text.lower() == "a vance"]
    assert len(a_vance) == 0, f"Error: initial absorbed article 'a': {a_vance}"
    print("[PASS] Issue 2: Alias regex is strictly case-sensitive and does not absorb articles.")


def test_issue_3_shared_surnames_marked_uncertain():
    """Issue 3: When a surname belongs to multiple known people, bare mentions are marked uncertain."""
    engine = DetectionEngine()
    text = (
        "John Smith and Jane Smith attended the conference. "
        "Mr Smith delivered the opening remarks. "
        "Ms Smith presented the financial report. "
        "Later, Smith signed the register."
    )
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    bare_smith = [e for e in res.entities if e.text == "Smith"]
    assert len(bare_smith) >= 1, "Bare 'Smith' was not detected"
    for bs in bare_smith:
        assert bs.tier == "uncertain", f"Bare Smith must be marked uncertain, got tier={bs.tier}"
        assert bs.confidence <= 0.75, f"Bare Smith confidence must be <= 0.75, got {bs.confidence}"
    print("[PASS] Issue 3: Shared surname bare mentions are marked uncertain.")


def test_issue_4_orgs_without_indicator_words_retained():
    """Issue 4: Organisations without statutory legal suffixes (Northwind, Deloitte) retained as uncertain."""
    engine = DetectionEngine()
    text = "The audit was conducted by Deloitte and Northwind provided logistics."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    org_texts = {e.text for e in res.entities if e.type == "ORGANISATION"}
    assert any("Deloitte" in t for t in org_texts) or any("Northwind" in t for t in org_texts), (
        f"Expected Deloitte or Northwind in detected orgs, got: {org_texts}"
    )
    for e in res.entities:
        if e.type == "ORGANISATION" and e.text in ("Deloitte", "Northwind"):
            assert e.tier == "uncertain", f"Org without indicator word must be uncertain, got tier={e.tier}"
    print("[PASS] Issue 4: Non-suffix organisations are retained with uncertain tier.")


def test_issue_5_newline_splitting():
    """Issue 5: Entities spanning newlines are split into separate individuals."""
    engine = DetectionEngine()
    text = "Attendees:\nAisha Rahman\n- Kemi Adeyemi\nEnd of list."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    person_texts = [e.text for e in res.entities if e.type == "PERSON"]
    assert any("Aisha Rahman" in t for t in person_texts), f"Aisha Rahman missed in: {person_texts}"
    assert any("Kemi Adeyemi" in t for t in person_texts), f"Kemi Adeyemi missed in: {person_texts}"
    assert not any("\n" in e.text for e in res.entities), "Entity contains un-split newline"
    print("[PASS] Issue 5: Entities spanning newlines are split cleanly.")


def test_issue_6_exact_offset_calculation():
    """Issue 6: Offsets calculated from clean_et position inside ent.text, not ent.start_char."""
    engine = DetectionEngine()
    text = "Meeting note: - Aisha Rahman joined the call."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    aisha = [e for e in res.entities if "Aisha" in e.text][0]
    assert text[aisha.start:aisha.end] == aisha.text, (
        f"Offset mismatch: text[{aisha.start}:{aisha.end}]='{text[aisha.start:aisha.end]}' != '{aisha.text}'"
    )
    assert not aisha.text.startswith("-"), "Leading bullet character was not stripped"
    print("[PASS] Issue 6: Character start and end offsets are 100% exact after stripping.")


def test_issue_7_overlap_merging():
    """Issue 7: Overlapping spans merged into one covering span so trailing text doesn't leak."""
    engine = DetectionEngine()
    text = "The matter was transferred to Mr Vance Holdings Ltd today."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    covering_org = [e for e in res.entities if "Holdings Ltd" in e.text]
    assert len(covering_org) == 1, f"Expected 1 covering entity for Holdings Ltd, got: {covering_org}"
    ent = covering_org[0]
    assert text[ent.start:ent.end] == ent.text
    assert ent.type == "ORGANISATION"
    print("[PASS] Issue 7: Overlapping spans merged into a single covering entity.")


def test_issue_8_first_names_in_surface_forms():
    """Issue 8: First names alone are in surface_forms and detected as uncertain aliases."""
    engine = DetectionEngine()
    text = "Siobhan O'Connor gave evidence. Siobhan stated that she was present."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    siobhan_first = [e for e in res.entities if e.text == "Siobhan"]
    assert len(siobhan_first) >= 1, "Bare first name 'Siobhan' was not detected"
    assert siobhan_first[0].tier == "uncertain", "Bare first name must be uncertain"

    full_ent = [e for e in res.entities if "O'Connor" in e.text][0]
    assert "Siobhan" in full_ent.surface_forms, f"First name missing from surface_forms: {full_ent.surface_forms}"

    guard_forms = GuardEngine.get_surface_forms(full_ent)
    assert "Siobhan" in guard_forms, f"GuardEngine failed to derive first name: {guard_forms}"
    print("[PASS] Issue 8: First names included in surface forms and flagged uncertain.")


def test_issue_9_confidence_and_tier_inheritance():
    """Issue 9: Single-word uncertain entities do not seed confident surname aliases."""
    engine = DetectionEngine()
    text = "Monzo was used for payments. Later, Monzo confirmed the transaction."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    monzo_ents = [e for e in res.entities if "Monzo" in e.text]
    for m in monzo_ents:
        if m.type == "PERSON":
            assert m.tier == "uncertain", f"Monzo should not be confident person: {m}"
            assert m.confidence < 0.85, f"Monzo confidence too high: {m.confidence}"
    print("[PASS] Issue 9: Uncertainty is preserved; single words do not seed confident aliases.")


# --- Part 2 Tests (New Reviewer Feedback) ---

def test_new_1_marcus_sterling_gets_person_placeholder():
    """New Issue 1: Marcus Sterling (Executive) must receive a [PERSON] placeholder, never [ORG]."""
    engine = DetectionEngine()
    text = "The agreement is between Apex Ltd and Marcus Sterling (Executive)."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    sterling = [e for e in res.entities if "Marcus Sterling" in e.text][0]
    assert sterling.type == "PERSON", f"Expected PERSON, got {sterling.type}"
    assert sterling.placeholder.startswith("[PERSON"), f"Expected [PERSON n], got {sterling.placeholder}"
    print("[PASS] New 1: Marcus Sterling (Executive) receives PERSON placeholder [PERSON 1], not [ORG 1].")


def test_new_2_morgan_stanley_not_person():
    """New Issue 2: First-name cross-referencing dropped so 'Morgan Stanley' is NOT converted to a person."""
    engine = DetectionEngine()
    text = "Morgan Lee is an analyst at Morgan Stanley."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    ms_ents = [e for e in res.entities if "Morgan Stanley" in e.text]
    for ms in ms_ents:
        assert ms.type == "ORGANISATION", f"Morgan Stanley was wrongly turned into {ms.type}"
    print("[PASS] New 2: First-name matching does not turn Morgan Stanley into a person.")


def test_new_3_role_regex_non_names():
    """New Issue 3: Role labels followed by non-names (e.g. Human Resources, Not Provided) are not confident persons."""
    engine = DetectionEngine()
    text = "Director: Human Resources attended. Name: Not Provided in report."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    hr_ents = [e for e in res.entities if "Human Resources" in e.text and e.type == "PERSON"]
    assert len(hr_ents) == 0, f"Human Resources wrongly tagged as PERSON: {hr_ents}"

    np_ents = [e for e in res.entities if "Not Provided" in e.text and e.type == "PERSON"]
    assert len(np_ents) == 0, f"Not Provided wrongly tagged as PERSON: {np_ents}"
    print("[PASS] New 3: Non-name department phrases after role labels are not confident persons.")


def test_new_4_first_name_same_placeholder():
    """New Issue 5: Bare first name shares the established person's placeholder ([PERSON 1]) instead of creating [PERSON 2]."""
    engine = DetectionEngine()
    text = "Jonathan Vance attended the meeting. Jonathan called later."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    jonathan_full = [e for e in res.entities if "Jonathan Vance" in e.text][0]
    jonathan_bare = [e for e in res.entities if e.text == "Jonathan"][0]

    assert jonathan_bare.placeholder == jonathan_full.placeholder, (
        f"Bare first name placeholder {jonathan_bare.placeholder} != {jonathan_full.placeholder}"
    )
    assert jonathan_bare.tier == "uncertain"
    print("[PASS] New 4: Standalone first name shares established person's placeholder ([PERSON 1]).")


def test_new_5_mrs_patel_ambiguous_uncertain():
    """New Issue 6: Mrs Patel ambiguous between Meena and Priya is marked uncertain (not confident third cluster)."""
    engine = DetectionEngine()
    text = "Meena Patel and Priya Patel arrived. Mrs Patel gave evidence."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    mrs_patel = [e for e in res.entities if "Mrs Patel" in e.text][0]
    assert mrs_patel.tier == "uncertain", f"Ambiguous Mrs Patel must be uncertain, got: {mrs_patel.tier}"
    print("[PASS] New 5: Ambiguous Mrs Patel is marked uncertain, not a confident third person.")


def test_new_6_initial_matching_p_smith():
    """New Issue 7: P. Smith resolves to Peter Smith (using initial), not an ambiguous new placeholder."""
    engine = DetectionEngine()
    text = "Peter Smith and John Smith arrived. P. Smith delivered the statement."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    peter = [e for e in res.entities if "Peter Smith" in e.text][0]
    p_smith = [e for e in res.entities if "P. Smith" in e.text][0]
    assert p_smith.placeholder == peter.placeholder, (
        f"P. Smith placeholder {p_smith.placeholder} != Peter Smith {peter.placeholder}"
    )
    print("[PASS] New 6: Initial matching correctly resolves P. Smith to Peter Smith.")


def test_new_7_halden_logistics_stem_guard():
    """New Issue 8: Stem 'Halden' is derived for Halden Logistics and checked by the outbound guard."""
    engine = DetectionEngine()
    text = "Halden Logistics filed the claim."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    halden_org = [e for e in res.entities if "Halden Logistics" in e.text][0]
    assert "Halden" in halden_org.surface_forms, f"Stem 'Halden' missing from surface forms: {halden_org.surface_forms}"

    # Verify GuardEngine blocks unmasked "Halden"
    guard_req = OutboundCheckRequest(
        doc_id="d1",
        protected_text="The matter was handled by Halden today.",
        active_entities=[halden_org],
        user_prompt=""
    )
    guard_res = GuardEngine.check_outbound(guard_req)
    assert not guard_res.passed, "Guard failed to block unmasked stem 'Halden'"
    print("[PASS] New 7: Halden stem is derived and guarded against leakage.")


def test_new_8_structured_value_not_swallowed():
    """New Issue 9: DOB 01/02/1985 is NOT swallowed by an uncertain organisation span."""
    engine = DetectionEngine()
    text = "Client DOB 01/02/1985 registered."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    dob_ents = [e for e in res.entities if e.type == "DATE_OF_BIRTH"]
    assert len(dob_ents) == 1, f"Expected 1 DATE_OF_BIRTH entity, got: {dob_ents}"
    assert dob_ents[0].text == "01/02/1985"
    assert dob_ents[0].placeholder == "[DATE 1]"
    print("[PASS] New 8: Structured DOB 01/02/1985 is preserved and not swallowed.")


def test_new_9_guard_outbound_empty_entities():
    """New Issue 12: Guard blocks raw PII even when active_entities is empty."""
    guard_req = OutboundCheckRequest(
        doc_id="d1",
        protected_text="The claimant NI number is QQ 12 34 56 A.",
        active_entities=[],
        user_prompt="Summarise the matter."
    )
    guard_res = GuardEngine.check_outbound(guard_req)
    assert not guard_res.passed, "Guard failed to block raw NI number when active_entities was empty"
    print("[PASS] New 9: Guard blocks raw PII when active_entities is empty.")


def test_new_10_guard_ordinary_words_not_blocked():
    """New Issue 13: Outbound guard does NOT block lowercase ordinary words (rose, grant, will, grace, hope)."""
    # Create entity for person named "Marcus Grant" and "Emily Rose"
    grant_ent = DetectedEntity(
        id="e1", block_id="b1", start=0, end=12, text="Marcus Grant", type="PERSON",
        placeholder="[PERSON 1]", surface_forms=["Marcus Grant", "Grant"]
    )
    rose_ent = DetectedEntity(
        id="e2", block_id="b1", start=0, end=10, text="Emily Rose", type="PERSON",
        placeholder="[PERSON 2]", surface_forms=["Emily Rose", "Rose"]
    )

    clean_text = "The committee will grant permission to view the rose in the garden with grace and hope."
    guard_req = OutboundCheckRequest(
        doc_id="d1",
        protected_text=clean_text,
        active_entities=[grant_ent, rose_ent],
        user_prompt=""
    )
    guard_res = GuardEngine.check_outbound(guard_req)
    assert guard_res.passed, f"False positive block on lowercase ordinary words: {guard_res.leaked_items}"
    print("[PASS] New 10: Guard does NOT block lowercase ordinary words (rose, grant, will, grace, hope).")


def test_new_11_phone_with_parenthesis_zero():
    """New Issue 10: Phone numbers with +44 (0) are matched."""
    engine = DetectionEngine()
    text = "Call +44 (0) 20 7946 0192 for inquiries."
    doc_ir = make_doc_ir(text)
    res = engine.detect(doc_ir)

    phone_ents = [e for e in res.entities if e.type == "PHONE"]
    assert len(phone_ents) == 1, f"Expected 1 PHONE entity, got {phone_ents}"
    assert "+44 (0) 20 7946 0192" in phone_ents[0].text
    print("[PASS] New 11: Phone number with +44 (0) is detected.")


def run_all():
    print("=" * 70)
    print("RUNNING UNIT TESTS FOR REVIEWER FEEDBACK FIXES")
    print("=" * 70)
    # Part 1
    test_issue_1_single_placeholder_per_person()
    test_issue_2_alias_case_sensitivity_and_articles()
    test_issue_3_shared_surnames_marked_uncertain()
    test_issue_4_orgs_without_indicator_words_retained()
    test_issue_5_newline_splitting()
    test_issue_6_exact_offset_calculation()
    test_issue_7_overlap_merging()
    test_issue_8_first_names_in_surface_forms()
    test_issue_9_confidence_and_tier_inheritance()
    # Part 2 (New Issues)
    test_new_1_marcus_sterling_gets_person_placeholder()
    test_new_2_morgan_stanley_not_person()
    test_new_3_role_regex_non_names()
    test_new_4_first_name_same_placeholder()
    test_new_5_mrs_patel_ambiguous_uncertain()
    test_new_6_initial_matching_p_smith()
    test_new_7_halden_logistics_stem_guard()
    test_new_8_structured_value_not_swallowed()
    test_new_9_guard_outbound_empty_entities()
    test_new_10_guard_ordinary_words_not_blocked()
    test_new_11_phone_with_parenthesis_zero()
    print("=" * 70)
    print("ALL 20 VERIFICATION TESTS PASSING!")
    print("=" * 70)


if __name__ == "__main__":
    run_all()
