"""
eval.py - AI Governance Gateway Evaluation Harness

Purpose:
  Evaluates the intake and detection pipeline against ground-truth synthetic documents
  in tests/synthetic/. Calculates Recall and Precision per identifier type, checks
  hidden content ingestion, and outputs a detailed list of detection misses.

Usage:
  python tests/eval.py
"""

import os
import sys
import json
import glob
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Ensure backend app is in python path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = WORKSPACE_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from app.parser.intake import intake_file
    from app.detector.engine import DetectionEngine
    from app.models import DocumentIR, DetectedEntity
except ImportError as e:
    print(f"Error importing backend modules: {e}")
    print(f"PYTHONPATH: {sys.path}")
    sys.exit(1)


# Phase 1 Target Metrics
TARGETS = {
    "STRUCTURED": 100.0,  # 100% on validated structured identifiers
    "PERSON": 97.0,       # >= 97% on person names including all alias surface forms
    "ORGANISATION": 95.0, # >= 95% on organisations
    "HIDDEN_CONTENT": 100.0,
}

STRUCTURED_TYPES = {
    "NI_NUMBER", "SORT_CODE", "ACCOUNT_NUMBER", "CREDIT_CARD",
    "UK_POSTCODE", "PHYSICAL_ADDRESS", "EMAIL", "PHONE",
    "MATTER_REF", "MONETARY_AMOUNT", "DATE_OF_BIRTH", "PASSPORT", "DRIVING_LICENCE"
}


class MissRecord:
    """Represents a single detection miss for the backlog."""
    def __init__(self, doc_name: str, surface_form: str, ent_type: str, context: str, reason: str = "Not detected"):
        self.doc_name = doc_name
        self.surface_form = surface_form
        self.ent_type = ent_type
        self.context = context
        self.reason = reason


class TypeStats:
    """Statistics accumulator for an entity type."""
    def __init__(self):
        self.expected = 0
        self.detected = 0
        self.false_positives = 0

    @property
    def recall(self) -> float:
        if self.expected == 0:
            return 100.0
        return (self.detected / self.expected) * 100.0

    @property
    def precision(self) -> float:
        total_found = self.detected + self.false_positives
        if total_found == 0:
            return 100.0 if self.expected == 0 else 0.0
        return (self.detected / total_found) * 100.0


def find_occurrences(text: str, sub: str) -> List[Tuple[int, int]]:
    """Find all start and end positions of an entity surface form on word boundaries."""
    positions = []
    # Match on word boundary so we don't match substrings inside emails or alphanumeric IDs
    pattern = re.compile(rf"(?<!\w){re.escape(sub)}(?!\w)", re.IGNORECASE)
    for m in pattern.finditer(text):
        start, end = m.start(), m.end()
        # Avoid matching inside an email address (e.g. ward@domain)
        if start > 0 and text[start - 1] in "@.":
            continue
        if end < len(text) and text[end] in "@.":
            continue
        positions.append((start, end))
    return positions


def run_evaluation(synthetic_dir: Path) -> Tuple[Dict[str, TypeStats], List[MissRecord], List[str]]:
    """
    Runs intake and detection over all synthetic test cases in tests/synthetic/.
    Returns:
      - stats_by_type: stats per identifier type
      - misses: list of missed entities with context
      - ingestion_warnings: list of hidden content ingestion issues
    """
    engine = DetectionEngine()
    gt_files = sorted(synthetic_dir.glob("*.json"))

    if not gt_files:
        print(f"No ground-truth (.json) files found in {synthetic_dir}")
        return {}, [], []

    stats_by_type: Dict[str, TypeStats] = {}
    misses: List[MissRecord] = []
    ingestion_warnings: List[str] = []

    for gt_path in gt_files:
        with open(gt_path, "r", encoding="utf-8") as f:
            gt_data = json.load(f)

        doc_filename = gt_data["document"]
        doc_path = synthetic_dir / doc_filename

        if not doc_path.exists():
            print(f"Warning: Document {doc_filename} referenced in {gt_path.name} does not exist.")
            continue

        with open(doc_path, "rb") as f:
            content = f.read()

        # 1. Run intake
        doc_ir: DocumentIR = intake_file(doc_filename, content)

        # 2. Check hidden content surfacing (comments, tracked changes, metadata, hidden sheets)
        seeded_hidden = gt_data.get("hidden_content", [])
        if seeded_hidden:
            extracted_hidden_texts = [
                b.text.lower() for b in doc_ir.blocks if b.visibility in ("hidden", "metadata", "deleted")
            ]
            extracted_metadata = [
                f"{m.key}: {m.value}".lower() for m in doc_ir.metadata
            ]
            all_hidden_str = " ".join(extracted_hidden_texts + extracted_metadata)

            for item in seeded_hidden:
                if item.lower() not in all_hidden_str:
                    ingestion_warnings.append(
                        f"[{doc_filename}] Hidden item '{item}' was NOT surfaced by intake."
                    )

        # 3. Run detection
        detection_res = engine.detect(doc_ir)
        detected_entities = detection_res.entities

        # Group detected entities by block_id
        detected_by_block: Dict[str, List[DetectedEntity]] = {}
        for ent in detected_entities:
            detected_by_block.setdefault(ent.block_id, []).append(ent)

        # 4. Check ground truth seeded entities
        for ent_def in gt_data.get("entities", []):
            ent_type = ent_def["type"]
            surface_forms = ent_def.get("surface_forms", [ent_def.get("canonical", "")])

            if ent_type not in stats_by_type:
                stats_by_type[ent_type] = TypeStats()

            for surface in surface_forms:
                if not surface:
                    continue

                # Search through all blocks for occurrences of this surface form
                for block in doc_ir.blocks:
                    block_text = block.text
                    occurrences = find_occurrences(block_text, surface)

                    for start, end in occurrences:
                        stats_by_type[ent_type].expected += 1

                        # Check if any detected entity overlaps with this span
                        matched = False
                        wrong_type = None

                        block_ents = detected_by_block.get(block.id, [])
                        for det in block_ents:
                            # Overlap check: max(start1, start2) < min(end1, end2)
                            if max(start, det.start) < min(end, det.end):
                                if det.type == ent_type:
                                    matched = True
                                    break
                                elif det.type == "ORGANISATION" and ent_type == "PERSON" and (det.end - det.start > end - start):
                                    # Person surname is covered inside a detected organization (e.g. Pendelton Chambers LLP)
                                    matched = True
                                    break
                                else:
                                    wrong_type = det.type

                        if matched:
                            stats_by_type[ent_type].detected += 1
                        else:
                            # Context snippet around the miss for the team's backlog
                            ctx_start = max(0, start - 25)
                            ctx_end = min(len(block_text), end + 25)
                            snippet = block_text[ctx_start:ctx_end].replace("\n", " ").strip()
                            reason = f"Mislabelled as {wrong_type}" if wrong_type else "Not detected"
                            misses.append(MissRecord(
                                doc_name=doc_filename,
                                surface_form=surface,
                                ent_type=ent_type,
                                context=f"...{snippet}...",
                                reason=reason
                            ))

        # 5. Check for false positives (detected items not in ground truth)
        all_gt_surfaces = set()
        for ent_def in gt_data.get("entities", []):
            for s in ent_def.get("surface_forms", []):
                all_gt_surfaces.add(s.strip().lower())
            if "canonical" in ent_def:
                all_gt_surfaces.add(ent_def["canonical"].strip().lower())

        for det in detected_entities:
            det_text = det.text.strip().lower()
            is_valid = any(gt_val in det_text or det_text in gt_val for gt_val in all_gt_surfaces)
            if not is_valid:
                det_type = det.type
                if det_type not in stats_by_type:
                    stats_by_type[det_type] = TypeStats()
                stats_by_type[det_type].false_positives += 1

    return stats_by_type, misses, ingestion_warnings


def print_report(stats: Dict[str, TypeStats], misses: List[MissRecord], ingestion_warnings: List[str]):
    print("\n" + "=" * 78)
    print(" AI GOVERNANCE GATEWAY — EVALUATION HARNESS REPORT")
    print("=" * 78)

    # Summary Table
    print(f"\n{'Identifier Type':<20} | {'Expected':<9} | {'Detected':<9} | {'Recall':<8} | {'Precision':<9} | Target")
    print("-" * 78)

    total_expected = 0
    total_detected = 0
    total_fp = 0

    ordered_types = sorted(stats.keys(), key=lambda t: (0 if t == "PERSON" else 1 if t == "ORGANISATION" else 2, t))

    for ent_type in ordered_types:
        st = stats[ent_type]
        total_expected += st.expected
        total_detected += st.detected
        total_fp += st.false_positives

        if ent_type == "PERSON":
            target_str = ">= 97%"
            status_icon = "[OK]" if st.recall >= 97.0 else "[X]"
        elif ent_type == "ORGANISATION":
            target_str = ">= 95%"
            status_icon = "[OK]" if st.recall >= 95.0 else "[X]"
        elif ent_type in STRUCTURED_TYPES:
            target_str = "100%"
            status_icon = "[OK]" if st.recall >= 100.0 else "[X]"
        else:
            target_str = "-"
            status_icon = " "

        print(
            f"{ent_type:<20} | {st.expected:<9} | {st.detected:<9} | "
            f"{st.recall:>6.1f}%  | {st.precision:>7.1f}%  | {target_str:<7} {status_icon}"
        )

    print("-" * 78)
    overall_recall = (total_detected / total_expected * 100.0) if total_expected > 0 else 100.0
    overall_precision = (total_detected / (total_detected + total_fp) * 100.0) if (total_detected + total_fp) > 0 else 100.0
    print(
        f"{'TOTAL OVERALL':<20} | {total_expected:<9} | {total_detected:<9} | "
        f"{overall_recall:>6.1f}%  | {overall_precision:>7.1f}%  |"
    )
    print("=" * 78)

    # Ingestion Warnings
    if ingestion_warnings:
        print(f"\n[!] INGESTION WARNINGS ({len(ingestion_warnings)} items missed):")
        for warn in ingestion_warnings:
            print(f"   * {warn}")

    # Detection Miss Backlog
    if misses:
        print(f"\n[-] DETECTION MISS LIST / BACKLOG ({len(misses)} misses):")
        print(f"{'Doc':<25} | {'Type':<15} | {'Surface Form':<20} | Context / Reason")
        print("-" * 78)
        for m in misses:
            print(f"{m.doc_name:<25} | {m.ent_type:<15} | {m.surface_form:<20} | {m.reason} in: {m.context}")
    else:
        print("\n[+] Zero detection misses across test set!")

    print("\n" + "=" * 78 + "\n")


def main():
    synthetic_dir = WORKSPACE_ROOT / "tests" / "synthetic"
    if not synthetic_dir.exists():
        print(f"Error: {synthetic_dir} does not exist.")
        sys.exit(1)

    stats, misses, warnings = run_evaluation(synthetic_dir)
    print_report(stats, misses, warnings)


if __name__ == "__main__":
    main()
