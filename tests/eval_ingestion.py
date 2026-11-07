"""
Ingestion check: every seeded hidden item in tests/synthetic/*/ *.expected.json must appear in the
parsed IR, in a block of the expected type. Run from the tests/ directory:  python eval_ingestion.py
Exit code 1 on any miss, so it can gate a merge like eval.py does.
"""
import json
import sys
import glob
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.parser.intake import intake_file  # noqa: E402

misses = 0
checked = 0
for exp_path in sorted(glob.glob(str(Path(__file__).parent / "synthetic" / "**" / "*.expected.json"), recursive=True)):
    exp = json.loads(Path(exp_path).read_text())
    doc_path = Path(exp_path).parent / exp["document"]
    ir = intake_file(doc_path.name, doc_path.read_bytes())
    print(f"\n{doc_path.name}: {ir.report.status}, {len(ir.blocks)} blocks, {ir.report.hidden_items_count} hidden items")
    for item in exp["seeded"]:
        checked += 1
        hits = [b for b in ir.blocks if item["text"] in b.text]
        typed = [b for b in hits if b.type == item["type"]]
        if typed:
            print(f"  [OK]   {item['type']:18} {item['text']!r}")
        elif hits:
            print(f"  [TYPE] {item['type']:18} {item['text']!r}  found but as {sorted({b.type for b in hits})}")
            misses += 1
        else:
            print(f"  [MISS] {item['type']:18} {item['text']!r}  ({item['what']})")
            misses += 1

print(f"\nIngestion: {checked - misses}/{checked} seeded hidden items surfaced.")
sys.exit(1 if misses else 0)
