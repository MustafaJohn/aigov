# Changelog: Project Legal

A high-level record of architectural decisions, customer feedback fixes, and deliverable milestones.

---

## [Unreleased / Latest] - Project Legal Branding & File Cleanup
- **Decision:** Removed hardcoded proprietary names (`LexGateway`, `Notion AI Studio`) in favor of generic working title **Project Legal**.
- **Reason:** Permanent product branding is not yet finalized; avoids customer confusion and lock-in.
- **Key Changes:**
  - Renamed frontend components: `NotionSidebar.tsx` → `Sidebar.tsx`, `NotionTopBar.tsx` → `TopBar.tsx`, `NotionPageHeader.tsx` → `DocumentHeader.tsx`.
  - Updated UI labels, export headers, documentation, and `localStorage` keys to `Project Legal`.

---

## [2026-11-01] - Deliverable 0: Evaluation Harness & Synthetic Benchmark
- **Decision:** Built an automated, multi-format objective evaluation test suite before shipping further detector modifications.
- **Reason:** Adheres to Phase 1 governance (*"Nothing ships without a test-set number"*); prevents regression without hardcoding detector logic.
- **Key Changes:**
  - Created `tests/eval.py` to ingest test files and compute Precision, Recall, and F1 per category.
  - Added multi-format synthetic corpus (`.txt`, `.docx`, `.xlsx`, `.pdf`) covering 11 UK/international PII categories in `tests/synthetic/`.
  - **Baseline Result:** 100% recall (92/92 target entities detected, 0 misses).

---

## [2026-11-01] - Customer Testing Feedback Fixes (Lawyer User Testing)

### 1. Dynamic Document Summarization
- **Decision:** Replaced static offline litigation template in `backend/app/llm/client.py` with dynamic text/entity extraction.
- **Reason:** Lawyers testing contracts, deeds, or court orders were confused by canned dispute summaries about unrelated parties.

### 2. Enhanced Name & Alias Resolution
- **Decision:** Expanded entity detection in `patterns.py` and `engine.py` to support single-surname honorifics, signatory prefixes, capitalized headings, and full-name alias chaining.
- **Reason:** Testing missed solo surnames (e.g., "Mrs Patel"), roles ("Sworn by"), title headings, and failed to link subsequent first-name mentions to full names.

### 3. PDF Intake & Scanned Form Handling
- **Decision:** Upgraded `pdf_parser.py` to use layout mode and extract AcroForm interactive form fields; flagged image-only scans as `READY_WITH_WARNINGS`.
- **Reason:** Official forms and court orders had empty text in standard extractors; hard errors on scanned docs blocked user workflows.

### 4. Direct Save & Inline Matter Notes
- **Decision:** Added 1-click **Save Document** download in top bar and an **Add Note to Matter** modal directly in `SideBySideReview.tsx`.
- **Reason:** Improved legal review workflow by enabling lawyers to download protected text and log notes without leaving the review screen.
