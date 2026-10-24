# LegalTech AI Governance Gateway (MVP)

A safe-AI legal gateway enabling solicitors and law firms to use LLMs (OpenAI, Claude, Gemini) on client material without breaching UK GDPR, confidentiality, or SRA obligations.

---

## Architecture Overview

- **Frontend (`frontend/`):** Next.js (App Router, TypeScript, Tailwind CSS, Lucide Icons).
  - Pure client-side entity resolution & key restoration (original client details never leave the browser unmasked).
  - Side-by-side review interface (Original IR vs Protected Preview).
  - Fail-safe Gate indicators (Ready / Ready with Warnings / Blocked).
  - Outbound leakage guard and tamper-evident audit receipt.
- **Backend (`backend/`):** Python (FastAPI, uvicorn, pydantic, python-docx, openpyxl, pypdf).
  - Uniform Internal Representation (IR) parsing for `.docx`, `.xlsx`, `.pdf`, `.txt`.
  - Structured UK regex detection (National Insurance numbers, Sort Codes, Account numbers, Postcodes, Amounts, Matter references) + party name & company heuristics.
  - BYOK LLM proxy dispatch (OpenAI, Anthropic, Gemini, or simulated Demo Mode).

---

## Quick Start

### 1. Start the Python Backend

```bash
cd backend
# Virtual environment is already created in backend/venv
.\venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```
Backend runs at `http://localhost:8000`. Swagger API docs are at `http://localhost:8000/docs`.

### 2. Start the TypeScript Frontend

```bash
cd frontend
npm run dev
```
Frontend runs at `http://localhost:3000`.

---

## 4-Step User Journey

1. **Intake & Parse:** Upload a `.docx`, `.xlsx`, or `.pdf` file (or click **"Load Synthetic Case"** for an instant 1-click test).
2. **Review & Gate:** Inspect the side-by-side view, toggle between **Restorable** placeholders (`[PERSON 1]`) and **Permanent** redaction (`████`), and inspect/override individual entity protections.
3. **Outbound Guard & Dispatch:** Pre-flight gate automatically verifies zero raw client names leak into the payload or custom instructions. Choose your LLM provider (BYOK) or use the instant Demo Mode.
4. **Restored Summary & Audit Record:** Real client details are restored inside the browser session using the local key map. Review the tamper-evident cryptographic receipt with zero client data retention.
