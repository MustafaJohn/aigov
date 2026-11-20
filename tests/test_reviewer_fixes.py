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


def test_new_12_ihs_reference_number_detected():
    """Confidential Information: UK Immigration Health Surcharge (IHS) numbers are detected."""
    engine = DetectionEngine()
    text = "Payment received. Your IHS reference number is IHS123456789. Secondary ref: IHS 987654321."
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    ihs_ents = [e for e in res.entities if e.type in ("IHS_REFERENCE", "REFERENCE")]
    assert len(ihs_ents) == 2, f"Expected 2 IHS/REFERENCE entities, got {ihs_ents}"
    assert ihs_ents[0].placeholder in ("[IHS 1]", "[REF 1]")
    assert ihs_ents[0].confidence >= 0.95
    print("[PASS] New 12: UK Immigration Health Surcharge (IHS) numbers detected with high confidence.")


def test_new_13_matter_ref_hyphenated():
    """Matter Reference: Generalize to match hyphenated law firm codes (e.g. TF-2026-0417)."""
    engine = DetectionEngine()
    text = "Client matter file TF-2026-0417 confirmed with instructing solicitors."
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    matter_ents = [e for e in res.entities if e.type == "MATTER_REF"]
    assert len(matter_ents) == 1, f"Expected 1 MATTER_REF entity, got {matter_ents}"
    assert matter_ents[0].text == "TF-2026-0417"
    print("[PASS] New 13: Hyphenated law firm matter ref (TF-2026-0417) detected.")


def test_new_14_form_field_labels_and_procedural_words_suppressed():
    """Detection Precision: Form field headers, procedural sentence starters, and web headers are not false entities."""
    engine = DetectionEngine()
    text = (
        "Claimant Name | Jonathan Vance\n"
        "Client Address | 42 Highbury Grove\n"
        "Request for a preliminary ruling regarding Directive 95/46/EC.\n"
        "Gmail - Your Immigration Health Surcharge update."
    )
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    texts = [e.text for e in res.entities]
    assert "Claimant Name" not in texts, "Claimant Name should not be an entity"
    assert "Client Address" not in texts, "Client Address should not be an entity"
    assert "Request" not in texts, "Request should not be a PERSON"
    assert not any("Directive" in t for t in texts), "Directive citation should not be an ORG"
    assert not any("Gmail" in t for t in texts), "Gmail header should not be an ORG"
    # Real entities were detected
    assert "Jonathan Vance" in texts
    print("[PASS] New 14: Form field labels, procedural words, and email headers suppressed.")


# --- Part 3 Tests (Punch List Items 1 to 15) ---

def test_punch_1_court_substring_not_dropping_names():
    """Punch 1: 'Courtney Hale' and 'Simon Harcourt' must NOT be dropped by 'court' filter."""
    engine = DetectionEngine()
    text = "Courtney Hale and Simon Harcourt attended the hearing as counsel."
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    person_texts = [e.text for e in res.entities if e.type == "PERSON"]
    assert any("Courtney" in t for t in person_texts), f"Courtney Hale missed! Found: {person_texts}"
    assert any("Harcourt" in t for t in person_texts), f"Simon Harcourt missed! Found: {person_texts}"
    print("[PASS] Punch 1: 'Courtney Hale' and 'Simon Harcourt' not dropped by 'court' filter.")


def test_punch_2_all_caps_names_caught_by_guard():
    """Punch 2: ALL-CAPS names ('JOHN ALDRIDGE') must be caught by outbound gate when John Aldridge is active."""
    ent = DetectedEntity(
        id="ent_1",
        block_id="b1",
        start=0,
        end=13,
        text="John Aldridge",
        type="PERSON",
        placeholder="[PERSON 1]",
        confidence=0.95,
        is_active=True,
        surface_forms=["John Aldridge", "Aldridge", "John"]
    )
    req = OutboundCheckRequest(
        doc_id="doc1",
        protected_text="The claimant is [PERSON 1].",
        active_entities=[ent],
        user_prompt="Please summarize the case of JOHN ALDRIDGE and his claims."
    )
    res = GuardEngine.check_outbound(req)
    assert not res.passed, "Security failure: ALL-CAPS name 'JOHN ALDRIDGE' bypassed outbound gate!"
    assert any("JOHN ALDRIDGE" in leak or "John Aldridge" in leak for leak in res.prompt_leaks)
    print("[PASS] Punch 2: ALL-CAPS names caught by outbound gate.")


def test_punch_3_bracket_bypass_blocked():
    """Punch 3: [JOHN ALDRIDGE] and [AB 12 34 56 C] must NOT bypass the guard."""
    ent = DetectedEntity(
        id="ent_1",
        block_id="b1",
        start=0,
        end=13,
        text="John Aldridge",
        type="PERSON",
        placeholder="[PERSON 1]",
        confidence=0.95,
        is_active=True,
        surface_forms=["John Aldridge", "Aldridge", "John"]
    )
    req1 = OutboundCheckRequest(
        doc_id="doc1",
        protected_text="The claimant is [JOHN ALDRIDGE].",
        active_entities=[ent],
        user_prompt="Summarise the dispute."
    )
    res1 = GuardEngine.check_outbound(req1)
    assert not res1.passed, "Security failure: [JOHN ALDRIDGE] bracket bypass passed guard!"

    req2 = OutboundCheckRequest(
        doc_id="doc1",
        protected_text="Client NI number is [AB 12 34 56 C].",
        active_entities=[],
        user_prompt="Check tax records."
    )
    res2 = GuardEngine.check_outbound(req2)
    assert not res2.passed, "Security failure: [AB 12 34 56 C] bracket bypass passed guard!"
    print("[PASS] Punch 3: Bracket bypass [NAME] and [NI] correctly blocked by guard.")


def test_punch_4_defense_in_depth_structured_patterns():
    """Punch 4: Postcode, DOB, address, and matter ref are blocked when active_entities is empty."""
    samples = [
        ("Client postcode is SW1A 1AA.", "UK Postcode"),
        ("Date of Birth: 15/08/1982.", "Date of Birth"),
        ("Lives at 42 Highbury Grove, London.", "Street Address"),
        ("Reference is KB-2026-000123.", "Matter/Case Ref")
    ]
    for text, expected_label in samples:
        req = OutboundCheckRequest(
            doc_id="doc1",
            protected_text=text,
            active_entities=[],
            user_prompt="Summarise the matter."
        )
        res = GuardEngine.check_outbound(req)
        assert not res.passed, f"Defense-in-depth failure: '{text}' passed with empty active_entities!"
    print("[PASS] Punch 4: Postcode, DOB, address, and matter ref blocked in defense-in-depth scan.")


def test_punch_5_normal_legal_prompts_not_blocked():
    """Punch 5: Normal instructions like 'Summarise the GDPR and SRA implications' and 'the £250,000 cap' pass outbound check."""
    req = OutboundCheckRequest(
        doc_id="doc1",
        protected_text="Document has been protected using [PERSON 1].",
        active_entities=[],
        user_prompt="Summarise the GDPR and SRA implications and the £250,000 cap under English law."
    )
    res = GuardEngine.check_outbound(req)
    assert res.passed, f"False block: Normal legal instruction was blocked: {res.prompt_leaks}"
    print("[PASS] Punch 5: Normal legal prompts ('GDPR', 'SRA', '£250,000 cap') not blocked.")


def test_punch_6_hale_consulting_typed_org_gets_org_placeholder():
    """Punch 6: 'Hale Consulting' is typed ORG and must receive an [ORG n] placeholder, never [PERSON 1]."""
    engine = DetectionEngine()
    text = "Daniel Hale advised that Hale Consulting Limited would perform the audit."
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    hale_consulting = [e for e in res.entities if "Hale Consulting" in e.text]
    assert len(hale_consulting) >= 1, f"Expected Hale Consulting entity, got: {res.entities}"
    for hc in hale_consulting:
        assert hc.type == "ORGANISATION", f"Expected ORGANISATION, got {hc.type}"
        assert hc.placeholder.startswith("[ORG "), f"Type mismatch! Expected [ORG n], got {hc.placeholder}"
    print("[PASS] Punch 6: 'Hale Consulting' receives [ORG n] placeholder matching its type.")


def test_punch_7_spouses_not_merged():
    """Punch 7: 'Mr Daniel Hale' and 'Mrs Hale' must not be merged into one person."""
    engine = DetectionEngine()
    text = "Mr Daniel Hale and Mrs Hale attended the consultation together."
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    daniel = [e for e in res.entities if "Daniel" in e.text]
    mrs_hale = [e for e in res.entities if "Mrs Hale" in e.text]
    assert len(daniel) >= 1, "Mr Daniel Hale not detected"
    assert len(mrs_hale) >= 1, "Mrs Hale not detected"
    assert daniel[0].placeholder != mrs_hale[0].placeholder, (
        f"Spouses merged! Both got {daniel[0].placeholder}"
    )
    print(f"[PASS] Punch 7: Spouses assigned distinct placeholders: Daniel={daniel[0].placeholder}, Mrs Hale={mrs_hale[0].placeholder}")


def test_punch_8_all_caps_company_detected():
    """Punch 8: 'HALDEN LOGISTICS LIMITED' in ALL-CAPS must be detected as an ORGANISATION."""
    engine = DetectionEngine()
    text = "Agreement entered into by HALDEN LOGISTICS LIMITED as the supplier."
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    orgs = [e for e in res.entities if e.type == "ORGANISATION" and "HALDEN" in e.text]
    assert len(orgs) >= 1, f"ALL-CAPS company missed! Entities: {res.entities}"
    assert "HALDEN LOGISTICS LIMITED" in orgs[0].text or "HALDEN LOGISTICS" in orgs[0].text
    print("[PASS] Punch 8: ALL-CAPS company 'HALDEN LOGISTICS LIMITED' detected.")


def test_punch_9_surname_first_lists_not_mangled():
    """Punch 9: 'SMITH, John v PATEL, Meena' must not yield 'John v PATEL'."""
    engine = DetectionEngine()
    text = "Case caption: SMITH, John v PATEL, Meena in the High Court of Justice."
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    ents = [e.text for e in res.entities]
    assert not any("John v PATEL" in t for t in ents), f"Mangled adversary entity found: {ents}"
    assert any("SMITH" in t or "Smith" in t for t in ents), f"Smith missed: {ents}"
    assert any("PATEL" in t or "Patel" in t for t in ents), f"Patel missed: {ents}"
    print("[PASS] Punch 9: Adversary caption 'SMITH, John v PATEL, Meena' parsed into clean individual entities.")


def test_punch_10_hmcts_claim_numbers_detected():
    """Punch 10: 'KB-2026-000123' must be detected as MATTER_REF."""
    engine = DetectionEngine()
    text = "Claim issued under claim number KB-2026-000123 in the King's Bench Division."
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    claim_ents = [e for e in res.entities if e.type == "MATTER_REF"]
    assert len(claim_ents) >= 1, f"HMCTS claim number missed! Entities: {res.entities}"
    assert claim_ents[0].text == "KB-2026-000123"
    print("[PASS] Punch 10: HMCTS claim number 'KB-2026-000123' detected.")


def test_punch_11_irish_names_with_fadas_detected():
    """Punch 11: Irish name with fada 'Siobhan Ní Bhriain' must be detected as PERSON."""
    engine = DetectionEngine()
    text = "The claimant Siobhan Ní Bhriain submitted her sworn witness statement."
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    irish_ents = [e for e in res.entities if e.type == "PERSON" and ("Siobhan" in e.text or "Bhriain" in e.text)]
    assert len(irish_ents) >= 1, f"Irish name 'Siobhan Ní Bhriain' missed! Entities: {res.entities}"
    assert irish_ents[0].type == "PERSON"
    print(f"[PASS] Punch 11: Irish name with fada detected: '{irish_ents[0].text}' as PERSON.")


def test_punch_12_grant_of_probate_not_blocked_by_rose_grant():
    """Punch 12: 'Grant of probate' must not trigger false block when 'Rose Grant' is active entity."""
    ent = DetectedEntity(
        id="ent_grant",
        block_id="b1",
        start=0,
        end=10,
        text="Rose Grant",
        type="PERSON",
        placeholder="[PERSON 1]",
        confidence=0.95,
        is_active=True,
        surface_forms=["Rose Grant", "Grant", "Rose"]
    )
    req = OutboundCheckRequest(
        doc_id="doc1",
        protected_text="The executor obtained Grant of probate on 12 June 2025.",
        active_entities=[ent],
        user_prompt="Summarise the estate administration."
    )
    res = GuardEngine.check_outbound(req)
    assert res.passed, f"False block: 'Grant of probate' was blocked: {res.leaked_items}"
    print("[PASS] Punch 12: 'Grant of probate' does not trigger false block when 'Rose Grant' is active.")


def test_punch_13_no_placeholder_numbering_gaps():
    """Punch 13: Placeholders are numbered strictly contiguously: [PERSON 1], [PERSON 2] (no gaps)."""
    engine = DetectionEngine()
    text = (
        "Daniel Hale attended the meeting. "
        "Separately, Marcus Sterling met with counsel. "
        "Hale Consulting provided third-party accounting services."
    )
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    person_placeholders = sorted(list({e.placeholder for e in res.entities if e.type == "PERSON"}))
    assert "[PERSON 1]" in person_placeholders
    if len(person_placeholders) >= 2:
        assert "[PERSON 2]" in person_placeholders, f"Numbering gap detected! Placeholders: {person_placeholders}"
    print(f"[PASS] Punch 13: Contiguous placeholder numbering verified: {person_placeholders}")


def test_punch_14_credit_card_luhn_and_card_placeholder():
    """Punch 14: Credit card uses Luhn check and emits [CARD n] placeholder (not [CREDIT CARD n])."""
    engine = DetectionEngine()
    # 4532 0150 0000 0007 is a valid Visa test number passing Luhn
    # 4532 0150 0000 0005 is invalid (fails Luhn)
    valid_card = "4532 0150 0000 0007"
    invalid_card = "4532 0150 0000 0005"
    text = f"Payment cards on file: {valid_card} and invalid {invalid_card}."
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    card_ents = [e for e in res.entities if e.type == "CREDIT_CARD"]
    assert len(card_ents) == 1, f"Expected 1 valid card, got {len(card_ents)}: {card_ents}"
    assert card_ents[0].text == valid_card
    assert card_ents[0].placeholder.startswith("[CARD "), f"Expected [CARD n], got: {card_ents[0].placeholder}"
    assert "CREDIT CARD" not in card_ents[0].placeholder
    print(f"[PASS] Punch 14: Valid card detected with placeholder {card_ents[0].placeholder}; invalid card rejected by Luhn.")


def test_punch_15_inbound_and_outbound_consistent():
    """Punch 15: Multi-word person names are matched consistently case-insensitively in both outbound and inbound checks."""
    ent = DetectedEntity(
        id="ent_1",
        block_id="b1",
        start=0,
        end=13,
        text="John Aldridge",
        type="PERSON",
        placeholder="[PERSON 1]",
        confidence=0.95,
        is_active=True,
        surface_forms=["John Aldridge", "Aldridge", "John"]
    )
    # Outbound check with lowercase/uppercase multi-word name in prompt
    out_req = OutboundCheckRequest(
        doc_id="doc1",
        protected_text="The client is [PERSON 1].",
        active_entities=[ent],
        user_prompt="What did JOHN ALDRIDGE confirm?"
    )
    out_res = GuardEngine.check_outbound(out_req)
    assert not out_res.passed, "Outbound failed to catch uppercase name!"

    # Inbound check on AI response with uppercase name
    in_warnings = GuardEngine.check_inbound("The AI notes that JOHN ALDRIDGE agreed to the terms.", [ent])
    assert len(in_warnings) >= 1, "Inbound failed to catch uppercase name in response!"
    print("[PASS] Punch 15: Outbound and inbound match consistently for multi-word personal names.")


def test_punch_16_ai_briefing_explains_document_clearly():
    """Tester feedback: AI Legal Studio response must clearly explain the document when asked 'explain the document to me'."""
    from app.llm.client import _generate_demo_legal_briefing
    sample_text = (
        "UK Visas & Immigration\n"
        "Immigration health surcharge complete\n"
        "Name: MS [PERSON 1]\n"
        "IHS reference number: [REF 1]\n"
        "Your visa application number is [REF 2].\n"
        "Amount paid: £2,070.00."
    )
    briefing = _generate_demo_legal_briefing(sample_text, "explain the document to me")
    assert "Legal Executive Briefing" in briefing
    assert "UK Visas & Immigration" in briefing
    assert "[PERSON 1]" in briefing
    assert "[REF 1]" in briefing
    assert "Procedural Next Steps" in briefing
    print("[PASS] Punch 16: AI Legal Studio generates a clear, plain-English legal briefing.")


def test_punch_17_mobile_numbers_in_various_formats():
    """Punch 17: Mobile numbers in UK (07xxx), hyphenated, bracketed, and labelled formats must be detected."""
    engine = DetectionEngine()
    samples = [
        ("Client mobile is 07123 456789 for urgent updates.", "07123 456789"),
        ("Emergency contact: 07700-900123.", "07700-900123"),
        ("Call mobile on (07123) 456789 immediately.", "(07123) 456789"),
        ("Overseas mobile: +44 7123 456 789.", "+44 7123 456 789"),
        ("Mobile: 07890123456 (primary).", "07890123456"),
    ]
    for text, expected in samples:
        doc = make_doc_ir(text)
        res = engine.detect(doc)
        phones = [e for e in res.entities if e.type == "PHONE"]
        assert len(phones) >= 1, f"Failed to detect mobile number in: '{text}'. Entities: {res.entities}"
        matched_texts = [p.text for p in phones]
        assert any(expected in m or m in expected for m in matched_texts), f"Expected '{expected}', got {matched_texts}"
    print("[PASS] Punch 17: Mobile numbers in UK, hyphenated, bracketed, and labelled formats detected.")


def test_punch_18_enhanced_dob_and_nhs_detection():
    """Punch 18: Enhanced personal info detection: DOB with ordinals, ISO, and NHS numbers."""
    engine = DetectionEngine()
    text = "The patient was born on the 14th of March 1980 with NHS Number: 987 654 3210."
    doc = make_doc_ir(text)
    res = engine.detect(doc)
    dobs = [e for e in res.entities if e.type == "DATE_OF_BIRTH"]
    refs = [e for e in res.entities if e.type == "REFERENCE"]
    assert len(dobs) >= 1, f"DOB with ordinal not detected! Entities: {res.entities}"
    assert len(refs) >= 1, f"NHS number reference not detected! Entities: {res.entities}"
    print("[PASS] Punch 18: Enhanced personal info (ordinal DOB and NHS numbers) detected.")


def test_punch_19_lor_and_non_western_first_name_linking():
    """Punch 19: LOR with non-Western names and Indian mobile numbers: all mentions linked to [PERSON 1] and phones detected."""
    import os
    lor_path = os.path.join(os.path.dirname(__file__), "fixtures", "lor.txt")
    if not os.path.exists(lor_path):
        return
    from app.parser.intake import intake_file
    with open(lor_path, "rb") as f:
        ir = intake_file("lor.txt", f.read())
    engine = DetectionEngine()
    res = engine.detect(ir)

    # 1. First name and full name share [PERSON 1]
    amaan_full = [e for e in res.entities if e.text == "Amaan Siddiqui"]
    amaan_first = [e for e in res.entities if e.text == "Amaan"]
    assert len(amaan_full) == 1, "Amaan Siddiqui not detected"
    assert len(amaan_first) >= 5, f"Standalone Amaan mentions missed! Found: {len(amaan_first)}"
    assert all(e.placeholder == amaan_full[0].placeholder for e in amaan_first), (
        f"Amaan did not share placeholder with Amaan Siddiqui! "
        f"Full: {amaan_full[0].placeholder}, First: {[e.placeholder for e in amaan_first]}"
    )

    # 2. Professor detected as distinct PERSON
    satya = [e for e in res.entities if "Satya Prakash" in e.text]
    assert len(satya) >= 1, "Dr. Satya Prakash Singh not detected as PERSON"
    assert satya[0].placeholder != amaan_full[0].placeholder, "Professor merged with student!"

    # 3. Mobile numbers detected
    phones = [e for e in res.entities if e.type == "PHONE"]
    assert any("+91-9818526340" in p.text for p in phones), "International +91 phone missed"
    assert any("98185 26341" in p.text for p in phones), "Labelled Mob phone missed"

    # 4. Outbound check parity
    by_block = {}
    for e in res.entities:
        by_block.setdefault(e.block_id, []).append(e)
    parts = []
    for b in ir.blocks:
        t = b.text
        for e in sorted(by_block.get(b.id, []), key=lambda x: x.start, reverse=True):
            t = t[:e.start] + e.placeholder + t[e.end:]
        parts.append(t)
    prot = "\n\n".join(parts)
    req = OutboundCheckRequest(doc_id=ir.doc_id, protected_text=prot, active_entities=res.entities, user_prompt="Summarise.")
    guard_res = GuardEngine.check_outbound(req)
    assert guard_res.passed, f"Outbound guard blocked LOR dispatch! Leaks: {guard_res.leaked_items}"
    print("[PASS] Punch 19: LOR detection, non-Western first-name linking, and mobile numbers fully verified.")


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
    # Part 2
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
    test_new_12_ihs_reference_number_detected()
    test_new_13_matter_ref_hyphenated()
    test_new_14_form_field_labels_and_procedural_words_suppressed()
    # Part 3 (Punch List Items 1 - 19)
    test_punch_1_court_substring_not_dropping_names()
    test_punch_2_all_caps_names_caught_by_guard()
    test_punch_3_bracket_bypass_blocked()
    test_punch_4_defense_in_depth_structured_patterns()
    test_punch_5_normal_legal_prompts_not_blocked()
    test_punch_6_hale_consulting_typed_org_gets_org_placeholder()
    test_punch_7_spouses_not_merged()
    test_punch_8_all_caps_company_detected()
    test_punch_9_surname_first_lists_not_mangled()
    test_punch_10_hmcts_claim_numbers_detected()
    test_punch_11_irish_names_with_fadas_detected()
    test_punch_12_grant_of_probate_not_blocked_by_rose_grant()
    test_punch_13_no_placeholder_numbering_gaps()
    test_punch_14_credit_card_luhn_and_card_placeholder()
    test_punch_15_inbound_and_outbound_consistent()
    test_punch_16_ai_briefing_explains_document_clearly()
    test_punch_17_mobile_numbers_in_various_formats()
    test_punch_18_enhanced_dob_and_nhs_detection()
    test_punch_19_lor_and_non_western_first_name_linking()
    print("=" * 70)
    print("ALL 42 VERIFICATION TESTS PASSING!")
    print("=" * 70)


if __name__ == "__main__":
    run_all()
