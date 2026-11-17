# Proposal: `AuditEvent` (deliverable 10)

Author: Rishi · Reviewer: Amaan · Status: **for review** · 17 November 2026

This proposes the shape of one audit record. Nothing here is in `models.py` yet; once Amaan agrees the
fields his guard code fills, I'll add the model, the table and the endpoint in week 4 (the shared-model
change will be named in that PR's title).

## What the audit log is for

A firm must be able to show, per matter, *what was sent to which AI provider, when, by whom, under what
protection, and what the checks found* — without the log itself becoming a second copy of the client's
confidential material. So every record is **metadata only**, and records are **hash-chained** so that
deleting or editing one breaks the chain visibly.

## The record

| Field | Type | Filled by | Notes |
| --- | --- | --- | --- |
| `id` | str (uuid4) | Rishi | |
| `matter_id` | str | Rishi | Chain is per matter, so a matter's log exports on its own |
| `seq` | int | Rishi | 1, 2, 3 … within the matter |
| `created_at` | ISO 8601 UTC | Rishi | Server clock, never the browser's |
| `user_id` | str | Rishi | From the signed-in session |
| `event` | enum | both | `document_parsed`, `dispatch_blocked`, `summary_returned`, `output_exported` |
| `document_sha256` | str | Rishi | From `SourceInfo.sha256`; identifies the file without naming it |
| `document_format` | str | Rishi | `docx` / `xlsx` / `pdf` / `txt` |
| `intake_status` | str | Rishi | `READY` / `READY_WITH_WARNINGS` / `BLOCKED` |
| `hidden_items_count` | int | Rishi | From `ParseReport` |
| `ocr_pages` | int | Rishi | Pages read by OCR, 0 if none |
| `ocr_min_confidence` | float \| null | Rishi | Lowest page confidence, null if no OCR |
| `warnings_acknowledged` | bool | Rishi | The lawyer clicked "I have reviewed these notices" |
| `protection_mode` | str | Amaan | `restorable` / `permanent` |
| `entities_by_type` | dict[str, int] | Amaan | Counts only, e.g. `{"PERSON": 4, "NI_NUMBER": 1}` |
| `entities_active` | int | Amaan | After the lawyer's toggles |
| `entities_manual` | int | Amaan | Added by hand on the review screen |
| `entities_dismissed` | int | Amaan | Detected but switched off by the lawyer |
| `uncertain_resolved` | int | Amaan | Uncertain items confirmed or dismissed before send |
| `outbound_passed` | bool \| null | Amaan | null when nothing was dispatched |
| `outbound_leak_count` | int | Amaan | Count only (see "What is never stored") |
| `prompt_screen_passed` | bool \| null | Amaan | |
| `inbound_warning_count` | int | Amaan | `len(SummarizeResponse.inbound_warnings)` |
| `provider` | str \| null | Rishi | `openai` / `anthropic` / `gemini` / `demo` |
| `model` | str \| null | Rishi | Exact model ID used |
| `sent_text_sha256` | str \| null | Amaan | Hash of the protected text actually sent |
| `prompt_sha256` | str \| null | Amaan | Hash of the lawyer's instructions as sent |
| `response_sha256` | str \| null | Amaan | Hash of the raw (placeholder) answer received |
| `app_version` | str | Rishi | Git commit of the deployed build |
| `prev_hash` | str | Rishi | `record_hash` of the previous record in this matter; 64 zeros for the first |
| `record_hash` | str | Rishi | SHA-256 of the canonical JSON of every field above (keys sorted, no whitespace) |

## What is never stored

- Document text, protected text, the prompt, the AI's answer: hashes only.
- Entity values, placeholder mappings or the restore key.
- **The file name.** Legal file names routinely carry client names (`Thornfield_witness_statement.pdf`).
  The document is identified by `document_sha256`; the matter page shows the name from the session
  while it lasts, and nothing persists it.
- The leaked values in a blocked dispatch. Today `summarize` returns them in the error message
  (`"Details: Vance, …"`), which is right for the lawyer on screen, but the audit record keeps the count.

## How the chain is checked

```python
def verify(records):            # records for one matter, ordered by seq
    prev = "0" * 64
    for r in records:
        body = {k: v for k, v in r.items() if k != "record_hash"}
        if r["prev_hash"] != prev or sha256(canonical_json(body)) != r["record_hash"]:
            return False, r["seq"]
        prev = r["record_hash"]
    return True, None
```

The export (JSON and CSV per matter) includes a `verify` result line, so a firm can show the log is intact.

## Questions for Amaan

1. Are the six counts you fill (`entities_*`, `uncertain_resolved`, `outbound_leak_count`,
   `inbound_warning_count`) available in one place at the end of `summarize`, or does some live only in
   the frontend (the toggles and manual adds do)? If frontend-only, the client sends them with the
   summarise request and the server records them; I'd rather the server recompute what it can.
2. Should `dispatch_blocked` events be logged? I think yes: a blocked send is exactly the evidence a firm
   wants ("the tool stopped this").
3. `summarize` currently returns blocked leaks inside `error`. Fine for the screen; can we also return
   `outbound_leak_count` as a number so the audit writer never has to parse the message?
