# 📘 LexGateway: Developer Architecture & Notion Workspace Guide

Welcome to the **LexGateway** developer guide! This document explains in simple, plain English what every single file in the project does, how the pieces fit together, and how the **Notion-style legal workspace** interface is structured.

---

## 🏛️ High-Level System Architecture

LexGateway is an **AI-Safe Legal Workspace** designed for law firms and lawyers. Rather than a static, linear website or wizard, it provides a full **Notion-like interactive legal workspace**:

```
┌─────────────────┬─────────────────────────────────────────────────────────────┬──────────────────┐
│ ⚖️ Notion        │ Top Breadcrumbs: LexGateway / [Doc] / Redaction Studio      │ ✨ Notion AI     │
│ Sidebar         ├─────────────────────────────────────────────────────────────┤ Copilot Drawer   │
│ (260px wide,    │ Notion Page Header: 📄 Title, Properties (Blocks, PII)      │ (Slide-over on   │
│ Collapsible)    │ View Tabs: [ Split Review | Redacted | AI | Database | Notes│ Right Side)      │
│                 ├─────────────────────────────────────────────────────────────┤                  │
│ - Quick Actions │                                                             │ - Self-Prompts   │
│ - Studio Views  │                  MAIN CONTENT CANVAS                        │ - Chat Follow-up │
│ - Session Files │                                                             │ - Add to Notes   │
│ - Recent Notes  │                                                             │                  │
│ - Model BYOK    │                                                             │                  │
└─────────────────┴─────────────────────────────────────────────────────────────┴──────────────────┘
```

---

## 📂 Project Directory Structure

```
LegalTech/
├── backend/
│   ├── app/
│   │   ├── detector/
│   │   │   ├── engine.py           # PII Detection & Random Jargon Token Generator
│   │   │   └── patterns.py         # Regex patterns for UK/International identifiers
│   │   ├── guard/
│   │   │   └── checker.py          # Pre-flight outbound leak verifier
│   │   ├── llm/
│   │   │   └── client.py           # Multi-provider LLM client (Demo, OpenAI, Claude, Gemini)
│   │   ├── parser/
│   │   │   ├── intake.py           # Universal document intake & gate manager
│   │   │   ├── docx_parser.py      # Word (.docx) extractor
│   │   │   ├── xlsx_parser.py      # Excel (.xlsx) extractor
│   │   │   ├── pdf_parser.py       # PDF (.pdf) extractor
│   │   │   └── txt_parser.py       # Plain text (.txt) extractor
│   │   ├── main.py                 # FastAPI entry point & API endpoints
│   │   └── models.py               # Pydantic data schemas
│   └── requirements.txt            # Python backend dependencies
│
├── frontend/
│   ├── app/
│   │   ├── layout.tsx              # Root HTML layout with font and CSS
│   │   ├── page.tsx                # Master workspace coordinator & view manager
│   │   └── globals.css             # Notion color palette & scrollbars
│   ├── components/
│   │   ├── NotionSidebar.tsx       # Collapsible left navigation bar
│   │   ├── NotionTopBar.tsx        # Top breadcrumb trail & action triggers
│   │   ├── NotionPageHeader.tsx    # Notion document title, properties & view tabs
│   │   ├── SideBySideReview.tsx    # Redaction Studio (Original vs Redacted Preview)
│   │   ├── RedactedOnlyView.tsx    # Clean full-page redacted document view
│   │   ├── AILegalStudio.tsx       # Full-page Notion AI Studio (Self-prompts & chat)
│   │   ├── AICopilotDrawer.tsx     # Notion AI slide-over drawer (usable on any page)
│   │   ├── EntityDatabaseTable.tsx # Notion-style database table of all PII tokens
│   │   ├── NotesPanel.tsx          # Notion-style case pages & legal notes
│   │   ├── IntakeScreen.tsx        # Clean drag-and-drop document intake
│   │   ├── GateBanner.tsx          # Document readiness indicator
│   │   └── ExportModal.tsx         # Central export & local download hub
│   ├── lib/
│   │   ├── restore.ts              # Redacted document compiler & download helper
│   │   ├── types.ts                # TypeScript data interfaces
│   │   └── syntheticSamples.ts     # Seeded synthetic test documents
│   └── package.json                # Next.js and frontend dependencies
│
├── DEVELOPER_GUIDE.md              # This documentation file
└── README.md                       # Quickstart guide
```

---

## 🎨 The Notion-Style UI Components

### 1. `frontend/components/NotionSidebar.tsx`
- **Collapsible Sidebar:** Toggled with `PanelLeft` / `PanelLeftClose` (like Notion's `Ctrl+\`).
- **Workspace Switcher:** Branded *"⚖️ LexGateway Legal"* with workspace metadata.
- **Quick Action Buttons:** 1-Click *"Intake New Document"* and *"New Note Page"*.
- **Workspace Views:** Links to **Intake**, **Redaction Studio**, **Entity Database (Table)**, **Notion AI Copilot**, and **Case Notes**.
- **Active Document Section:** Displays currently open file with status indicator (`● Ready`).
- **Notes Pages Sub-tree:** Lists all created notes with categorized Notion emojis (`📝`, `⚠️`, `⚖️`, `💡`).
- **Footer:** Model status badge (`Model: Demo / BYOK`).

### 2. `frontend/components/NotionTopBar.tsx`
- **Breadcrumbs:** Shows navigational path: `LexGateway / Documents / [Filename] / [Active View]`.
- **Top Right Actions:**
  - `✨ Ask AI`: Toggles the Notion AI Copilot side-drawer from any screen!
  - `⬇️ Export`: Opens the Export & Download Hub.
  - `🔄 Reset`: Starts a fresh intake.

### 3. `frontend/components/NotionPageHeader.tsx`
- Displays the document like a Notion page:
  - Large title with emoji icon: `📄 Commercial_Dispute_Memo.txt`.
  - Notion-style database properties block:
    - `Status`: `● Ready`
    - `Protection`: `XXX / XYZ Jargon`
    - `Blocks`: `18 blocks`
    - `PII Items`: `17 masked`
  - Notion view tab switcher:
    - `[ 📄 Side-by-Side Review ]`
    - `[ 🛡️ Redacted Text Only ]`
    - `[ 🤖 Notion AI Studio ]`
    - `[ 🗃️ Entity Database ]`
    - `[ 📝 Case Notes ]`

### 4. `frontend/components/EntityDatabaseTable.tsx`
- An authentic **Notion Database Table view** for all PII items:
  - Columns: Checkbox (`Status`), Original Value (`Sensitive Value`), Category (`PII Classification`), Replacement (`Jargon Token` like `XXX_1`), `Confidence`, `Origin` (`Auto` vs `Manual`), and Delete action.
  - Search box and PII Type dropdown filter.
  - Quick *"Add redaction term"* form to redact custom phrases across the document.
  - *"Export CSV"* button to download the entity manifest.

### 5. `frontend/components/AICopilotDrawer.tsx`
- A slide-over right drawer (width ~380px) matching Notion AI:
  - Users can read the document on the left and query the AI on the right simultaneously!
  - Includes the **1-Click Self-Prompts** grid.
  - Interactive chat for follow-up legal queries.
  - *"Save to Notes"* and *"Download Markdown"* buttons on each response.

### 6. `frontend/components/ExportModal.tsx`
- Central download hub modal allowing 1-click downloads for:
  - 📄 **Redacted Document** (`.txt`)
  - 🗃️ **Entity Database Manifest** (`.csv`)
  - 📝 **All Case Notes** (`.md`)
  - 📦 **Complete Matter Bundle** (`.md` containing full document + tokens + notes)

### 7. `frontend/components/SideBySideReview.tsx` (Redaction Studio)
- Left side: Original parsed text with **interactive mouse selection** (*"Redact Selection as XXX/XYZ"*), click-to-toggle highlights, and custom phrase input.
- Middle: Entities inspector with search and type filters.
- Right side: Live preview showing text with `XXX` and `XYZ` random jargon tokens.

### 8. `frontend/components/NotesPanel.tsx` (Case Notes)
- Notion-style sub-pages with categorized emojis (`📝`, `⚠️`, `⚖️`, `💡`, `📌`).
- Live page title and content editor.
- Automatically saved to browser `localStorage` and downloadable as Markdown.

---

## 🔍 Backend Architecture

### 1. `backend/app/detector/patterns.py` & `engine.py`
- Detects UK/international PII using regular expressions:
  - **Account Numbers:** Requires banking context keywords (no more false positives on random 8-digit numbers).
  - **Person Names:** Honorifics (`Mr. Jonathan Vance`), role-based (`Claimant: Jonathan Vance`), and common first names + surnames.
  - **Organisations:** Constrained to 1–4 words before legal suffixes (`LLP`, `Ltd`, `PLC`, `Holdings`, `Chambers`, `Solicitors`) and banks (`Barclays Bank`, `HSBC`), excluding "National Insurance".
  - **Addresses & Postcodes:** UK postcodes (`N5 2EF`) and street addresses (`42 Highbury Grove, London`).
  - **NI Numbers, Sort Codes, Phones, Emails, Monetary Amounts, Matter Refs, Dates of Birth.**
- Replaces entities with consistent random jargon tokens (`XXX_1`, `XYZ_2`, `XXX_3`, etc.) rather than `[REDACTED]`.

### 2. `backend/app/parser/intake.py`
- Coordinates parsing for `.docx`, `.xlsx`, `.pdf`, and `.txt`.
- Immediately issues `status = "READY"` when text is extracted, eliminating annoying warning barriers.

### 3. `backend/app/llm/client.py`
- Multi-provider client supporting OpenAI, Anthropic Claude, Google Gemini, and a built-in instant local Demo simulator.
- Pre-configured with UK legal reasoning for all 6 self-prompt scenarios.

---

## 🚀 How to Run

### 1. Backend:
```powershell
cd D:\Amaan\LegalTech\backend
.\venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend:
```powershell
cd D:\Amaan\LegalTech\frontend
npm run dev
```
Open your browser at `http://localhost:3000`.
