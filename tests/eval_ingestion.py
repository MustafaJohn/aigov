"""
Ingestion check, run from the tests/ directory:  python eval_ingestion.py

1. Seeded items: every item in tests/synthetic/**/*.expected.json must appear in the parsed IR,
   in a block of the expected type.
2. Gate outcome: when an expected.json gives expected_status (and optionally text the gate reason
   or a warning must contain), the intake gate must agree.
3. Gate cases: OCR page limit and OCR switched off must BLOCK a scanned document, never pass it.

Exit code 1 on any failure, so it can gate a merge like eval.py does.
"""
import glob
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.parser.intake import intake_file  # noqa: E402

HERE = Path(__file__).resolve().parent
failures = 0
checked = 0


def fail(msg: str) -> None:
    global failures
    failures += 1
    print(f"  [FAIL] {msg}")


for exp_path in sorted(glob.glob(str(HERE / "synthetic" / "**" / "*.expected.json"), recursive=True)):
    exp = json.loads(Path(exp_path).read_text())
    doc_path = Path(exp_path).parent / exp["document"]
    t0 = time.perf_counter()
    ir = intake_file(doc_path.name, doc_path.read_bytes())
    secs = time.perf_counter() - t0
    print(f"\n{doc_path.name}: {ir.report.status}, {len(ir.blocks)} blocks, {ir.report.hidden_items_count} hidden items, {secs:.1f}s")

    for item in exp["seeded"]:
        checked += 1
        hits = [b for b in ir.blocks if item["text"] in b.text]
        typed = [b for b in hits if b.type == item["type"]]
        if typed:
            print(f"  [OK]   {item['type']:18} {item['text']!r}")
        elif hits:
            fail(f"{item['type']:18} {item['text']!r} found but as {sorted({b.type for b in hits})}")
        else:
            fail(f"{item['type']:18} {item['text']!r} missing ({item['what']})")

    if "expected_status" in exp:
        checked += 1
        if ir.report.status == exp["expected_status"]:
            print(f"  [OK]   gate status {ir.report.status}")
        else:
            fail(f"gate status {ir.report.status}, expected {exp['expected_status']} ({ir.report.gate_reason})")
    if "expected_gate_contains" in exp:
        checked += 1
        if exp["expected_gate_contains"] in (ir.report.gate_reason or ""):
            print(f"  [OK]   gate reason mentions {exp['expected_gate_contains']!r}")
        else:
            fail(f"gate reason {ir.report.gate_reason!r} does not mention {exp['expected_gate_contains']!r}")
    if "expected_warning_contains" in exp:
        checked += 1
        if any(exp["expected_warning_contains"] in w for w in ir.report.warnings):
            print(f"  [OK]   warning mentions {exp['expected_warning_contains']!r}")
        else:
            fail(f"no warning mentions {exp['expected_warning_contains']!r}")


# ---- Gate cases that depend on server configuration -------------------------------------------------
GATE_CASES = [
    ("OCR page limit: 2-page scan with OCR_MAX_PAGES=1 must block page 2",
     "pdf_depth/scanned_letter_clear.pdf", {"OCR_MAX_PAGES": "1"}, "BLOCKED", "over the 1-page OCR limit"),
    ("OCR switched off: a scan must block, not pass with nothing screened",
     "pdf_depth/scanned_letter_clear.pdf", {"OCR_ENABLED": "false"}, "BLOCKED", "OCR is switched off"),
    ("No Tesseract on the server (Render free tier): a scan must block with a plain reason",
     "pdf_depth/scanned_letter_clear.pdf", {"TESSERACT_CMD": "/nonexistent/tesseract"}, "BLOCKED", "OCR is not installed"),
]
print("\nGate cases")
for label, rel, env, want_status, want_reason in GATE_CASES:
    checked += 1
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        p = HERE / "synthetic" / rel
        ir = intake_file(p.name, p.read_bytes())
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    if ir.report.status == want_status and want_reason in (ir.report.gate_reason or ""):
        print(f"  [OK]   {label}")
    else:
        fail(f"{label}: got {ir.report.status} / {ir.report.gate_reason!r}")

print(f"\nIngestion: {checked - failures}/{checked} checks passed.")
sys.exit(1 if failures else 0)
