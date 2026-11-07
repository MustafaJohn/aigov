# Changelog: Project Legal

A high-level record of architectural decisions, customer feedback fixes, and deliverable milestones.

---

## [2026-11-07] - Week 2 (part 1): DOCX hidden-content ingestion (Engineer B)
- **Decision:** The DOCX parser now walks the WordprocessingML XML directly instead of relying on `python-docx` paragraph text, so every place a name can hide in a Word file reaches the detector.
- **Reason:** `paragraph.text` only reads runs that are direct children of the paragraph. Text inside a tracked insertion (`w:ins`) and deleted text (`w:delText`) were silently dropped, hidden-formatted runs (`w:vanish`) were merged into visible text with no flag, and comments, footnotes, headers, footers, text boxes and custom properties were never read at all. Document properties were captured as metadata but never turned into blocks, so author names never went through detection.
- **Key Changes:**
  - `backend/app/parser/docx_parser.py`: rewritten. New block types `tracked_insertion`, `tracked_deletion`, `hidden_text`, `comment`, `header_footer`, `footnote`, `endnote`, `textbox`, `metadata`. `visibility` stays within `visible` / `hidden` / `metadata` so the review screen and `restore.ts` need no change; the kind shows as the existing `[type]` badge. Tracked insertions are included in the visible paragraph (they are on the page) and also reported as their own flagged block with the author. Table rows keep the previous one-block-per-row shape; nested tables and tables inside headers are covered. All six header/footer variants per section. All core properties plus `docProps/custom.xml`. Comment authors recorded as metadata.
  - Warnings now name what was found ("1 deleted text block(s) still in the file, 1 review comment(s), …") and add a plain instruction when deleted or hidden text remains in the file.
  - `tests/synthetic/docx_depth/`: a synthetic attendance note seeding all 13 hidden-item types, its generator script, and `*.expected.json` ground truth.
  - `tests/eval_ingestion.py`: new harness; every seeded hidden item must surface in a block of the expected type; exit 1 on a miss so it can gate merges alongside `eval.py`. Result: 13/13.
  - `tests/eval.py` still passes (92/92 recall). PERSON precision moved 73.6% → 72.4% because property values are now detected on; this is the honest number.
  - Not in this PR: XLSX depth (next), PDF annotations and OCR (week 3).

---

## [2026-11-16] - Week 2/3: Identity Resolution, Reviewer Feedback & Guard Hardening (Engineer A - PR 5)
- **Decision:** Fully resolved all 13 issues and gaps raised in reviewer feedback across entity placeholders, alias resolution, outbound guard fail-safes, structured pattern protection, and pattern validators.
- **Reason:** Satisfies Phase 1 Week 2/3 core governance requirements: eliminates cross-category placeholder pollution, prevents over-aggressive entity conversion, secures the outbound guard fail-safe when active entities are omitted, stops false blocks on common English words, protects structured PII from being swallowed, and ensures strict adherence to Ground Rule 1 (zero hardcoded name lists).
- **Key Changes:**
  - `backend/app/detector/engine.py`:
    - **Typed Registry Key & Late Allocation:** Added `entity_type` to `EntityRegistry` key `(prefix, text)`. Allocated placeholders only after all candidate extraction, reclassification, identity clustering, and deduplication are complete. Completely prevents entities like `Marcus Sterling (Executive)` from receiving an organisation placeholder (`[ORG 1]`).
    - **Dropped First-Name Reclassification:** Dropped first-name cross-referencing for organisations so entities like `Morgan Stanley`, `John Lewis`, and `Marks & Spencer` are never converted to people based on first name alone.
    - **Role Regex Restraint & Punctuation:** Restricted `ROLE_PREFIX_REGEX` delimiters to `:` and `-` (excluding bare commas). Added non-person role filters (`resources`, `team`, `department`, `not provided`). Set unconfirmed role-based matches to `tier: "uncertain"` (0.75).
    - **Initial-Based Disambiguation:** Extended surname resolution to resolve initials (e.g. `P. Smith` resolves to `Peter Smith`, not `John Smith`).
    - **Ambiguous Titled Mentions:** Marked ambiguous titled references (e.g. `Mrs Patel` when both Meena and Priya are present) as `tier: "uncertain"` (0.70) rather than creating an artificial confident third cluster.
    - **Organisation Stemming & Alias Resolution:** Added `extract_org_stem` to derive distinctive core stems (e.g. `Halden` from `Halden Logistics`), added stem to `surface_forms`, and detected standalone stem mentions as uncertain aliases.
    - **Structured Span Protection:** In `_deduplicate_spans`, carved out absolute protection for structured patterns (`PATTERNS`). Structured values (e.g. `DOB 01/02/1985`) can never be swallowed, trimmed, or overridden by adjacent or enclosing uncertain spans.
    - **User-Authored Metadata Scanning:** Scanned user-authored metadata fields (`author`, `creator`, `last_modified_by`, `title`, `subject`) for PII entities while ignoring software generator metadata (`Producer`, `Application`).
    - **Honest Docstring:** Updated module docstrings to truthfully describe lexical determiners, legal syntax, and boilerplate filters.
  - `backend/app/guard/checker.py`:
    - **Defense-in-Depth Structured Scan:** Updated `check_outbound` to scan both document text and prompt for raw structured PII directly, ensuring the gate blocks unmasked PII even if `active_entities: []`.
    - **Case-Sensitive Word Boundary Matching:** Made name surface form matching case-sensitive so ordinary lowercase words (`rose`, `grant`, `will`, `grace`, `hope`, `may`, `wood`) are never falsely blocked.
    - **Organisation Stem Harmonization:** Updated corporate stem extraction to strip suffixes like `logistics`, `partners`, `services`, `solicitors`, and `systems`.
  - `backend/app/main.py`:
    - **Unconditional Outbound Guard:** Removed `if active_entities:` guard bypass in `/api/llm/summarize`; `GuardEngine.check_outbound` is now unconditionally enforced on every dispatch.
  - `backend/app/detector/patterns.py`:
    - **UK Phone Generalization:** Extended `PHONE` regex to match `+44 (0) ...` telephone formats.
    - **Contextual Sort Code Validation:** Restricted `SORT_CODE` regex to hyphenated pairs (`\d{2}-\d{2}-\d{2}`) or explicit sort code context, preventing random dates like `12 03 26` from triggering false positive sort codes.
  - `tests/test_reviewer_fixes.py`:
    - Implemented a 20-test automated verification suite covering all reviewer feedback items.
- **Verification:**
  - `tests/eval.py`: **100.0% Recall** across all 13 types, **98.3% PERSON Precision**, **100.0% ORGANISATION Precision**, **99.1% Overall Precision**, 0 misses, fail-safe gate passed.
  - `tests/test_reviewer_fixes.py`: **20 / 20 tests passing**.
  - `npm --prefix frontend run build`: **0 TypeScript / Turbopack build errors**.

---

## [2026-11-15] - Week 2: Statistical NER via spaCy & Deletion of Brittle Rules (Engineer A - PR 4)
- **Decision:** Replaced `seq_pattern` (capitalized sequences), `party_verb_pattern`, and arbitrary block-order heuristics in `engine.py` with statistical NER via a singleton spaCy `en_core_web_sm` model. Added `canonical_id`, `surface_forms`, and `tier` (`confident` / `uncertain` / `manual`) to `DetectedEntity`. Supported compact international phone numbers (`+\d{8,14}`). Restricted corporate regex to horizontal whitespace. Updated `SideBySideReview.tsx` uncertain review gate to be driven by `tier`. Updated `IntakeScreen.tsx` privacy claim.
- **Reason:** Fulfills Week 2 milestone: statistical NER eliminates test-suite tuning and removes the 14 false-positive backlog items (table row labels in `.xlsx` and capitalized titles in `.docx`) while maintaining 100% recall and staying within Render Free Tier memory limits (~120 MB RAM used of 512 MB). Also resolves real-world CV intake issues: compact unspaced phone numbers (`+91...`) and multi-line corporate bridging.
- **Key Changes:**
  - `backend/app/detector/spacy_loader.py`: Singleton `get_nlp()` loader initializing `en_core_web_sm` once with lemmatizer disabled and auto-download fallback.
  - `backend/app/detector/patterns.py`: Generalized `PHONE` regex to match compact international phone numbers (`+\d{8,14}`); restricted `COMPANY_REGEX` to horizontal whitespace (`[ \t]+`) to prevent multiline false merges.
  - `backend/app/detector/engine.py`: Refactored `DetectionEngine` to use spaCy for `PERSON` and `ORGANISATION` while preserving regex validators for structured UK PII. Deleted `seq_pattern`, `party_verb_pattern`, and arbitrary header heuristics. Added algorithmic alias and canonical resolution.
  - `backend/app/models.py`: Added `canonical_id: Optional[str]`, `surface_forms: List[str]`, and `tier: str` to `DetectedEntity`.
  - `frontend/lib/types.ts`: Synchronized TypeScript `DetectedEntity` interface with `canonical_id`, `surface_forms`, and `tier`.
  - `frontend/components/SideBySideReview.tsx`: Updated `isUncertain` gate calculation to check `ent.tier === 'uncertain'` rather than a hardcoded 0.94 cutoff.
  - `frontend/components/IntakeScreen.tsx`: Replaced legacy "Local & Ephemeral" statement with accurate server-side processing notice.
  - `PROJECT_CONTEXT_AND_RULES.md`: Established persistent ground rules and architecture reference.
- **Verification:** Evaluated against 7 synthetic test documents with 105 seeded entities:
  - **Overall Recall:** **100.0%** (105 / 105)
  - **Overall Precision:** **100.0%** (105 / 105)
  - **PERSON Precision:** **100.0%** (0 false positives, meeting $\ge 90.0\%$ target)
  - **ORGANISATION Precision:** **100.0%** (meeting $\ge 85.0\%$ target)
  - **Outbound Fail-Safe Gate:** Passed
  - **Next.js Production Build:** Passed with 0 TypeScript errors.

---

## [2026-11-13] - Week 2: Dependency Preparation & Pattern Generalization (Engineer A - PR 3)
- **Decision:** Added `spacy>=3.8.0` dependency to `backend/requirements.txt`, removed test-specific words from patterns (`Priya`, `Parties Background`), generalized matter reference format for initials (`KB/2026/0912`), added hyphenated surname recognition (`Adebayo-Clarke`), and supported ampersands in law firm names (`Kingsley & Barr LLP`).
- **Reason:** Sets up the foundation for Week 2 statistical NER and prevents test-suite overfitting while expanding coverage for genuine UK legal documents.
- **Key Changes:**
  - `backend/requirements.txt`: Added `spacy>=3.8.0`.
  - `backend/app/detector/patterns.py`: Generalized `MATTER_REF` regex; updated `PERSON_TITLES_REGEX` and `ROLE_BASED_PERSON_REGEX` to support hyphenated names; updated `COMPANY_REGEX` to support ampersands in corporate entities.
  - `backend/app/detector/engine.py`: Updated party verb matching for hyphenated surnames; restricted noun-sequence matching to common names.
- **Verification:** Evaluated against 7 synthetic test documents with 105 seeded entities.

---

## [2026-11-13] - Week 1: Shared Models Schema - Inbound Warnings & Active Entities (Engineer A - PR 2)
- **Decision:** Updated shared schema in `backend/app/models.py` (`models.py` change) to make `active_entities: List[DetectedEntity]` an explicit field on `SummarizeRequest` and return `inbound_warnings: List[str]` as a dedicated structured field on `SummarizeResponse`.
- **Reason:** Inbound governance notices (flags for real identifiers or new tokens introduced by the model) were previously string-concatenated into the raw Markdown summary. Moving this to a structured schema separates governance telemetry from model output and enables clean UI alert rendering.
- **Key Changes:**
  - `backend/app/models.py`: Added `active_entities: List[DetectedEntity]` to `SummarizeRequest`; added `inbound_warnings: List[str]` to `SummarizeResponse`.
  - `backend/app/main.py`: Updated `/api/llm/summarize` to return `inbound_warnings` as a typed list rather than injecting warning text into `summary`.
  - `frontend/lib/types.ts`: Added `inbound_warnings?: string[]` to `AIChatMessage`.
  - `frontend/app/page.tsx`: Updated `handleExecutePrompt` to return `{ summary, inbound_warnings }`.
  - `frontend/components/AILegalStudio.tsx`: Rendered inbound warnings in a dedicated alert banner beside/above the output text; updated protection claim text to reflect server-side parsing and browser-side restoration.
  - `frontend/components/AICopilotDrawer.tsx`: Updated response handler to support structured summary payload.
- **Verification:** `npx tsc --noEmit` passed with 0 errors.

---

## [2026-11-13] - Week 1: Evaluation Harness Honesty & Unseen Benchmark (Engineer A - PR 1)
- **Decision:** Added unseen test documents from the review and upgraded `tests/eval.py` to measure Precision alongside Recall and print a complete false-positive backlog with sentence context.
- **Reason:** Satisfies Phase 1 Week 1 mandate: "Make the harness honest. Record the real baseline. Print the false-positive backlog."
- **Key Changes:**
  - `tests/synthetic/test_06_adebayo_attendance_note.txt` & `.json`: Attendance note exercising hyphenated surnames (`Adebayo-Clarke`), law firms with ampersands (`Kingsley & Barr LLP`), child/client distinction, and un-prefixed surname aliases.
  - `tests/synthetic/test_07_no_personal_data_clause.txt` & `.json`: Zero-PII commercial contract boilerplate (governing law, jurisdiction, severability) to evaluate false positive rates.
  - `tests/eval.py`: Added `FalsePositiveRecord` accumulator; added precision targets (`PERSON: >= 90%`, `ORGANISATION: >= 85%`); prints detailed false-positive backlog table with document name and sentence context; gates build failure on precision drop.
- **Verification:** Baseline recorded on 7 synthetic test documents (105 seeded entities). Baseline surfaced false-positive backlog items to be resolved via statistical NER in Week 2.

---

## [2026-11-05] - Week 1 Hygiene: Fail-Safe Gate Enforcement, CORS, Error Handling & Model Defaults (Engineer B)
- **Decision:** Closed the week-1 hygiene items from the Phase 1 plan: the fail-safe gate is now enforced end to end, the API only answers the frontend origin, no exception text or provider error body reaches the browser, and the three provider defaults point at models that still exist.
- **Reason:** `GateBanner` was imported but never rendered, so intake warnings and blocks were invisible and the AI view was reachable from the sidebar regardless of document state. CORS was `*` with credentials. Intake and provider errors echoed internals (including, in OpenAI's case, the API key). All three default model IDs were retired or scheduled for shutdown.
- **Key Changes:**
  - `frontend/app/page.tsx`: single `gatePassed` rule (not `BLOCKED`, warnings acknowledged, zero unresolved uncertain items). All view changes go through `selectView`, which refuses the AI view until the gate passes; `handleExecutePrompt` refuses too, so the Copilot drawer cannot bypass it. `GateBanner` is now rendered above `DocumentHeader`.
  - `frontend/components/GateBanner.tsx`: `READY_WITH_WARNINGS` shows an "I have reviewed these notices" acknowledgement; `BLOCKED` can never proceed.
  - `frontend/components/Sidebar.tsx`, `DocumentHeader.tsx`: `aiLocked` prop disables the AI buttons with a tooltip until the gate passes.
  - `frontend/components/SideBySideReview.tsx`: reports unresolved uncertain count upward via `onUnresolvedUncertainChange`.
  - `frontend/components/AILegalStudio.tsx`, `AICopilotDrawer.tsx`: `ENABLE_PHASE2_EXTENDED_TASKS` now read from `NEXT_PUBLIC_ENABLE_PHASE2_TASKS` (default off).
  - `backend/app/main.py`: CORS origins from `ALLOWED_ORIGINS` env var plus localhost; `allow_credentials=False`; methods limited to GET/POST/OPTIONS. Intake failures logged server-side, generic message returned.
  - `backend/app/parser/intake.py`: parse exceptions logged; `gate_reason` no longer quotes the exception.
  - `backend/app/llm/client.py`: `_provider_error` logs the provider body with the API key redacted and returns a plain message by status (bad key, unknown model, rate limit, unreachable). Gemini key moved from the URL query string to the `x-goog-api-key` header. Defaults `claude-sonnet-5-5`, `gpt-6-luna`, `gemini-3.8-flash` (sources in code comment), overridable via `DEFAULT_MODEL_OPENAI|ANTHROPIC|GEMINI`. System prompt updated from `XXX_1` jargon to typed placeholders.
  - **Deployment note:** set `ALLOWED_ORIGINS=https://aigov-frontend.onrender.com` on the Render backend before deploying, or the live frontend will be refused.
  - Verification: `next build` clean; `tests/eval.py` 92/92 recall, fail-safe gate OK; CORS preflight accepts the configured origin and rejects others; bogus-key and corrupt-file paths return generic messages with the key redacted in logs.

---

## [2026-11-04] - Deliverables 5, 6, 8 & 9: Server-Side Fail-Safe, Output Review & Review Gating
- **Decision:** Integrated server-side fail-safe outbound check, inbound output scanning, task lock to Summarise, output review side-by-side mode, and review screen deduplication with uncertain items gating.
- **Reason:** Satisfies Phase 1 exit criteria: outbound check must catch deliberately unmasked aliases; prompt must be screened; single task focus; side-by-side raw/restored review with restore count; and review screen must deduplicate repeated entities and gate on unresolved items.
- **Key Changes:**
  - `backend/app/guard/checker.py`: Algorithmic alias and surface form generation (surnames, honorific + surname, initial + surname, corporate suffixes, compact formats) with word-boundary regex matching (`\b...\b`). Zero hardcoding.
  - `backend/app/main.py`: Server-side outbound guard and prompt screening directly inside `/api/llm/summarize`. Any unmasked alias in text or prompt aborts dispatch before LLM inference. Inbound scan verification on response. Models schema kept frozen.
  - `frontend/components/AILegalStudio.tsx` & `AICopilotDrawer.tsx`: Feature-flagged off 5 extra workflows (`ENABLE_PHASE2_EXTENDED_TASKS = false`), locking Phase 1 to Executive Legal Summary. Added outbound gate status badge beside custom prompt input.
  - `frontend/components/AILegalStudio.tsx`: Implemented Deliverable 9 Output Review with toggleable/split views (Restored View, Protected AI Output, Side-by-Side), live placeholder restoration counter, and unrestored token alert badges.
  - `frontend/components/SideBySideReview.tsx`: Deduplicated entity list by unique value with mention counter (e.g. `Apex Global Solutions (3×)`). Added Uncertain Items Gate with mandatory Confirm/Dismiss resolution. Gated the "Open in AI Assistant" button until all uncertain items are resolved. Updated preview header to `PROTECTED PREVIEW (TYPED PLACEHOLDERS)`.
  - `tests/eval.py`: Added automated harness test for deliberately unmasked aliases (`run_fail_safe_harness_test`), verifying that leaving an unmasked alias in document text or prompt triggers a block. Added build failure exit code.
  - Verification: `tests/eval.py` passed with 100% recall (92/92, 0 misses) and `[OK] Outbound Fail-Safe Gate`. TypeScript check passed with 0 errors.

---

## [2026-11-02] - Deliverables 2 & 4: Typed Placeholders & Pattern De-hardcoding
- **Decision:** Replaced random jargon tokens (`XXX_1`, `XYZ_2`) with semantic typed placeholders (`[PERSON 1]`, `[ORG 2]`, `[ACCOUNT 1]`).
- **Reason:** In legal analysis, the AI must understand semantic roles (employer vs employee, bank vs claim amount) while keeping client data 100% masked.
- **Key Changes:**
  - Implemented `EntityRegistry` in `engine.py` with universal dynamic type fallback (zero crashes on unknown/custom types) and alias unification (linking `Mr Vance` and `Vance` to `Jonathan Vance`'s placeholder).
  - Cleaned `patterns.py`: completely removed test-specific surnames from `COMMON_FIRST_NAMES` and fixed role regex prefix case-sensitivity.
  - Implemented `restoreProtectedText()` and typed placeholder generation in `frontend/lib/restore.ts`.
  - Updated all UI components, database tables, and exports to typed placeholders.
  - Verification: 100% target recall (92/92 detected, 0 misses, 73.6% precision).

---

## [2026-11-01] - Project Legal Branding & File Cleanup
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
