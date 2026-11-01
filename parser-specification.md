# Parser specification v0.2 (Governance MVP)

Status: draft for team review, 20 October 2026
Related: `legal-ai-project-brief.md`
Marking: **Proposed** = suggested by Claude, not yet agreed. **Open** = needs a team decision. Library names are options to evaluate, not decisions; check licences and maintenance status before adopting any.

---

## 1. Purpose and principles

The parser turns an uploaded file into one internal representation (IR). Detection, review, placeholders, LLM text and restore all work on the IR, never on the raw file.

Principles:

1. **One IR for all formats.** Downstream code never knows whether a block came from Word, Excel or PDF.
2. **Provenance on everything.** Every piece of text records where it came from, so a detection can be highlighted, replaced and restored without re-parsing.
3. **Nothing hidden is silently dropped or silently sent.** Hidden content is extracted, scanned and reported. Whether it is sent to the LLM is a visible decision (section 6).
4. **Fail-safe.** If the parser cannot read something reliably, it blocks and explains (decided in the brief).
5. **Deterministic.** Same file in, same IR out. No AI in the parser except OCR.
6. **Hostile input.** Every upload is treated as potentially malicious (section 8).
7. **Language-agnostic contract.** The IR is a JSON schema. The implementation can be Python or TypeScript, and can be ported, as long as it passes the same test corpus.

Scope v0 (basic support, as decided): `.docx`, `.xlsx`, `.pdf` (born-digital and scanned, via OCR), English only. Optional and trivial: `.txt`.
Out of scope v0: legacy `.doc` and `.xls`, macro-enabled files, password-protected files, other languages, handwriting recognition, pixel-faithful rendering of originals.

## 2. Pipeline

```
upload
  -> intake checks (size, type sniffing by content, not extension)
  -> sandboxed extraction (per format)
  -> normalisation into IR
  -> quality assessment (OCR confidence, reading order, mismatches)
  -> parse report (plain English)
  -> gate: Ready | Ready with warnings | Blocked
```

## 3. Internal representation (IR)

```jsonc
Document {
  "doc_id": "random per run",
  "source": { "format": "docx|xlsx|pdf|txt", "size_bytes": 0, "sha256": "...", "pages_or_sheets": 0 },
  "metadata": [ MetadataItem ],      // author, company, last-modified-by, etc.
  "blocks":   [ Block ],             // in reading order
  "report":   ParseReport
}

Block {
  "id": "b0001",
  "type": "paragraph|heading|list_item|table|cell|header|footer|footnote|endnote|comment|
           tracked_insertion|tracked_deletion|text_box|annotation|form_field|bookmark|
           hyperlink_target|alt_text|chart_text|sheet_name|defined_name|ocr_text|metadata",
  "text": "string",
  "visibility": "visible|hidden|deleted|metadata|non_printing",
  "locator": Locator,                // format-specific, see below
  "spans":  [ { "start": 0, "end": 0, "source_ref": "run/part id" } ],   // maps text offsets back to source runs
  "confidence": 1.0,                 // below 1.0 for OCR or uncertain reading order
  "parent_id": "b0000 or null",      // tables, cells, nested content
  "order": 0
}

Locator (examples)
  docx: { "part": "word/document.xml", "paragraph": 12, "runs": [3,4,5] }
  xlsx: { "sheet": "Sheet1", "sheet_state": "visible|hidden|veryHidden", "cell": "C14", "row_hidden": false, "col_hidden": false, "kind": "value|formula|comment|..." }
  pdf:  { "page": 3, "bbox": [x0,y0,x1,y1], "layer": "text|ocr|annotation|form|metadata", "invisible": false }
```

Rules:
- A detection is always `(block_id, start, end)`. Restore uses the same triple.
- Tables keep their grid (row, column), because LLM text rendering and review both need it.
- Excel formulas keep **both** formula text and cached value as separate blocks.
- Text is normalised for detection (merge split runs, normalise smart quotes, non-breaking and zero-width spaces) but spans keep the mapping back to the original runs.

Renderings produced from the IR:
- **Review view, both sides:** original (IR rendering) and protected (IR plus decisions), as decided. Not pixel-faithful. For PDFs, an optional page image with highlight overlays is possible since positions are known (**Proposed**).
- **LLM text:** structured plain text. Tables as simple delimited text, spreadsheets with sheet and cell references.

## 4. Extraction checklist per format

### 4.1 Word (.docx)

| Item | Why it matters |
|---|---|
| Body, nested tables, list items | Core content |
| Headers and footers (all section variants) | Often contain client or matter names |
| Footnotes and endnotes | Case citations, party names |
| **Tracked changes**: insertions and deletions (deleted text lives in its own element) | Deleted text is still in the file |
| Revision authors and dates | Names and activity patterns |
| **Comments** and comment authors | Internal discussion, names |
| Text boxes and shapes | Often missed; also commonly stored twice (alternate-content fallback), so de-duplicate |
| Hidden text (vanish property) | Invisible on screen |
| Content controls, form fields | Prefilled client data |
| Field codes, hyperlinks and their targets | URLs can contain identifiers |
| Images: alt text, and the image itself | Signatures, ID scans |
| Document properties (core, app, custom): creator, last modified by, company, manager, custom fields | Metadata leaks |
| Embedded objects, linked templates, external relationships | Embedded files, outbound links |
| Macros (`vbaProject`) | **Block** (also catches renamed files) |
| Encryption or password | **Block** |

### 4.2 Excel (.xlsx)

| Item | Why it matters |
|---|---|
| Visible sheets, cell values (via shared strings) | Core content |
| **Hidden and very-hidden sheets** | Invisible in the normal UI |
| Hidden rows and columns | Often hold IDs or notes |
| **Formulas and cached values** (separate) | Formulas can embed literal names or numbers |
| Cell comments, notes and threaded comments, with authors | Internal discussion |
| Sheet names and defined names | Can contain client names |
| Data validation lists | Lists of names or values |
| Pivot caches (can hold the full source data even when the pivot looks summarised) | Large hidden data |
| Charts: titles, series names, cached data | Text inside visuals |
| Drawings, text boxes, images | As for Word |
| External links | Other file paths and names |
| Print headers and footers | Names and references |
| Document properties | Metadata leaks |
| Values stored as text: leading zeros, long numbers (account numbers, IBANs) | Must stay exact; avoid numeric coercion |
| Macros (`.xlsm`) | **Block** |
| Encryption or password | **Block** |
| Size limits (rows, columns, cells) | Protect the sandbox; see limits |

### 4.3 PDF

First classify **each page**: born-digital text, scanned image, or mixed.

| Item | Why it matters |
|---|---|
| Text layer with positions, fonts, sizes | Core content |
| Reading order (columns, tables, sidebars) | Wrong order scrambles summaries |
| **Scanned pages**: render and OCR (local engine) | No text layer |
| **Text layer produced by an earlier OCR tool** (invisible text over an image) | May be wrong; compare against fresh OCR |
| **Invisible or deceptive text**: white text, tiny fonts, off-page text, invisible rendering mode | Hidden content |
| **Bad redaction**: black boxes drawn over text that is still in the file | Classic leak; detect live text under filled rectangles |
| Annotations (comments, highlights with text, free text) and authors | Internal notes |
| Form fields and their values | Prefilled data |
| Embedded file attachments | **Block or flag** |
| Bookmarks and outlines | Can contain names |
| Metadata (info dictionary and XMP) | Author, software, dates |
| Optional content layers (hidden layers) | Hidden content |
| Digital signature fields | Signer names |
| JavaScript or launch actions | **Block**; never executed |
| Encryption: user password needed | **Block**; owner-password-only restrictions flagged |
| Images: signatures, stamps, photos | OCR or flag as non-text |

### 4.4 OCR (local only)

- Run locally; sending scans to a cloud OCR service would defeat the purpose.
- Pre-processing: render at suitable resolution, deskew, rotate, denoise.
- Record per-word and per-page confidence in the IR.
- **Threshold:** **Open.** Choose it from measured results on the test corpus, not by guesswork. The metric that matters is *identifier survival rate*: does a seeded identifier come out of OCR exactly?
- Regions that cannot be read (handwriting, stamps, signatures, very low quality) become "unreadable region" entries in the report and require acknowledgement.

### 4.5 Plain text (.txt, optional)
Detect encoding. Block if it cannot be decoded reliably. Apply size limits.

## 5. Parse report (what the lawyer sees)

Plain English. Each finding links to its location in the review screen.

```
File: <name>        Result: Ready with warnings

Readable        14 pages (12 text, 2 scanned and read by OCR: 97% average confidence)
Included        Body text, 3 tables, 2 footnotes
Hidden content  14 tracked changes (including 5 deleted passages), 6 comments by 2 authors,
                document properties: author, company
Not text        2 images (1 looks like a signature). They cannot be protected.
Warnings        Page 9 scan quality is low: 3 words unreadable.
What happens    Hidden content is scanned for sensitive data. By default it is NOT sent to the AI.
                You can include it.
```

Gate outcomes:
- **Ready:** nothing notable.
- **Ready with warnings:** hidden content, non-text elements or minor OCR issues. The lawyer must acknowledge.
- **Blocked:** a reason and a suggested next step ("Save as a text PDF", "Remove the password", "Exclude page 9").

## 6. Block and warn rules (fail-safe)

| Condition | Action |
|---|---|
| Content does not match the extension, or type unsupported | Block |
| Encrypted or password-protected | Block |
| Macros, embedded executables or embedded attachments | Block |
| JavaScript or launch actions in a PDF | Block |
| Corrupted or only partly readable | Block |
| Exceeds limits (size, pages, sheets, cells, decompressed size) | Block (limits **Open**) |
| Zero extractable text | Block |
| OCR below threshold on a page | Proceed with a warning (**Decided**). Safeguard (**Proposed**): the page is marked low confidence in review, its text is excluded from sending by default, and it is included only if the lawyer explicitly opts in. Reason: garbled OCR can leave partly recognisable identifiers that detection misses |
| Large mismatch between text layer and fresh OCR | Warn; require acknowledgement |
| Text found under black boxes (bad redaction) | Warn; include in detection |
| Hidden content found (comments, tracked changes, hidden sheets, metadata) | Warn; always scan; excluded from sending by default; lawyer may opt in (**Decided**) |
| Embedded images (photos, signatures, screenshots) | Warn; images are never sent as images and are excluded from sending by default. OCR is not run by default but is supported on request when the lawyer needs the text, and that text then goes through detection (**Decided** in principle; details **Proposed**). If a file has almost no text but large images (for example a scan pasted into Word), offer OCR instead of blocking |
| Language appears not to be English | Warn (detection quality unknown) |

## 7. Output rules for downstream steps

- Detection runs on all extracted text, including hidden content, even if hidden content is not sent.
- The protected view is built from the IR plus the lawyer's decisions.
- Restore works on the answer text only (decided: no rebuilding of original files).
- The IR lives in memory for the duration of the run and is not persisted by the service. Any stored run record contains only what the storage design allows (encrypted under the firm's key).

## 8. Security and sandboxing (because the service is hosted)

- Detect type by content (magic bytes and structure), never by extension.
- Parse in an isolated worker or container: no network, read-only file system, in-memory scratch space, strict CPU, memory and time limits, destroyed after each run.
- Hardened XML parsing: disable external entities and DTDs (XXE protection).
- Archive safety for Office files: limits on entry count, total uncompressed size and compression ratio; reject path traversal.
- Never execute anything: no macros, no PDF JavaScript, no rendering engines with scripting enabled.
- Logging allow-list: counts, durations and error codes only. No document text, no filenames in logs, no content in crash dumps or error trackers, no content in backups.
- Delete raw bytes and the IR when the run ends.

## 9. Test plan

### 9.1 Synthetic corpus
Generate files programmatically so the ground truth is known. Never use real client data. Real-world layouts can come from public documents (court-published, already anonymised, licence permitting) for realism only.

Seeded identifiers (all fake): full names and aliases ("John Smith", "Mr Smith", "J. Smith"), addresses and postcodes, emails, phone numbers, dates of birth, UK national insurance number format, passport numbers, sort code and account number, IBAN, client and matter references, company names.

Each test file has a ground-truth manifest (JSON) listing: expected blocks, where each seeded identifier sits (including hidden locations), expected report entries and expected gate decision.

### 9.2 Starter cases

| Format | Cases |
|---|---|
| Word | Plain letter; tracked deletions containing a name; comments with author names; text box (with duplicated fallback); header and footer names; footnotes; hidden text; names split across formatting runs; nested tables; document properties with company; renamed file with macros; password-protected |
| Excel | Hidden sheet; very-hidden sheet; hidden columns of IDs; formula with a literal name; comments; identifiers stored as text with leading zeros; pivot cache with source data; chart with names in series; sheet named after a client; external link; large sheet near the limit |
| PDF | Born-digital letter; two-column layout; table-heavy; scanned clean; scanned skewed, rotated and low resolution; scan with prior OCR layer that contains errors; white-on-white text; bad redaction (black box over live text); annotations with names; form fields; embedded attachment; JavaScript; bookmarks with names; password-protected |
| Mixed and edge | Text file in odd encoding; file with wrong extension; zip bomb; XXE sample; empty file; non-English page |

### 9.3 Metrics

- **Text recall:** share of seeded visible identifiers extracted exactly.
- **Hidden-content recall:** share of seeded hidden identifiers found and correctly labelled.
- **OCR identifier survival rate** by scan quality.
- **Gate accuracy:** correct block, warn and pass decisions.
- **False-block rate** on clean files.
- Parse time and peak memory per file size.
- **Regression rule:** no change merges if any metric drops against the stored baseline.

## 10. Library options to evaluate (not decisions)

| Need | Python options | TypeScript / browser options |
|---|---|---|
| Word | Raw XML via `lxml` (needed for tracked changes and comments); `python-docx` for convenience | Zip and XML parsing libraries; `mammoth` is lossy for these purposes |
| Excel | `openpyxl` (separate runs for formulas and cached values) | SheetJS and similar |
| PDF | `pikepdf`, `pdfminer.six`, `pdfplumber`; **`PyMuPDF` is strong but AGPL-licensed or commercial: check before use in a commercial product** | `pdf.js` |
| OCR | Tesseract, PaddleOCR, docTR; `ocrmypdf` for pipelines | `tesseract.js` (slower, limited) |

Note: if detection moves into the browser (still **Open**), the parser must run there too, which favours the TypeScript column. A Python parser cannot practically run in the browser. Keeping the IR schema and the test corpus as the contract makes a later port straightforward.

## 11. Milestones and exit criteria

| Milestone | Deliverable | Exit criterion |
|---|---|---|
| M0 | IR JSON schema and corpus generator with ground-truth manifests | Schema reviewed by team; corpus v0 generated |
| M1 | Word parser | Hits agreed recall targets on all Word cases |
| M2 | Excel parser | Same for Excel cases |
| M3 | PDF text parser including bad-redaction and hidden-text checks | Same for born-digital PDFs |
| M4 | OCR pipeline | OCR identifier survival measured per scan quality; threshold chosen from data |
| M5 | Parse report and gate | Gate accuracy and false-block targets met |

Recall targets and thresholds are **Open** and should be set by the team after M0 baselines.

## 12. Open questions for the team

Resolved on 20 October 2026:
- Hidden content: always scanned, never sent unless the lawyer opts in.
- Embedded images: never sent as images; OCR only on request.
- Low-confidence OCR pages: proceed with a warning (with the proposed safeguard in section 6).

Still open:
1. Limits: maximum file size, pages, sheets and cells for the MVP.
2. The OCR confidence level at which a page counts as low confidence.
3. Whether `.txt` is in the MVP.
4. Language: warn or block for non-English content.
5. Where the parser runs (tied to the browser-versus-server detection decision).
6. Excel scale: how to handle very large sheets for LLM text without overflowing the model context.
