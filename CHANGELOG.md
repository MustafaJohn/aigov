# Changelog: Project Legal

A high-level record of architectural decisions, customer feedback fixes, and deliverable milestones.

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
