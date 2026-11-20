import os
import re
import logging
import httpx
from typing import Optional
from app.models import SummarizeRequest, SummarizeResponse

logger = logging.getLogger("aigov.llm")

# Default model per provider. Verified against each provider's published model list on 5 Nov 2026:
#   - claude-3-5-sonnet-20241022 was retired 28 Oct 2025; Anthropic names claude-sonnet-5-5 as the replacement.
#   - gpt-4o-mini shuts down 14 Jan 2027; OpenAI's deprecation page names gpt-6-luna as the replacement.
#   - gemini-1.5-flash is no longer listed; Google points new projects at gemini-3.8-flash.
# Override without a code change by setting the env var, e.g. DEFAULT_MODEL_OPENAI=gpt-6-luna.
DEFAULT_MODELS = {
    "openai": os.getenv("DEFAULT_MODEL_OPENAI", "gpt-6-luna"),
    "anthropic": os.getenv("DEFAULT_MODEL_ANTHROPIC", "claude-sonnet-5-5"),
    "gemini": os.getenv("DEFAULT_MODEL_GEMINI", "gemini-3.8-flash"),
}

PROVIDER_TIMEOUT_SECONDS = float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "90"))


def _provider_error(provider: str, model_name: str, status_code: Optional[int], body: str, api_key: str = "") -> SummarizeResponse:
    """
    Log the provider's error server-side (with the API key redacted; some providers echo it back)
    and return a generic, non-leaking message to the client. Provider error bodies can quote
    request content and must never reach the browser.
    """
    safe_body = body.replace(api_key, "[REDACTED KEY]") if api_key else body
    logger.warning("Provider %s (%s) returned HTTP %s: %s", provider, model_name, status_code, safe_body[:1000])
    if status_code in (401, 403):
        user_msg = f"{provider.capitalize()} rejected the API key. Check the key and try again."
    elif status_code == 404:
        user_msg = f"{provider.capitalize()} does not recognise the model '{model_name}'. Choose another model."
    elif status_code == 429:
        user_msg = f"{provider.capitalize()} rate limit or quota reached. Wait a moment and try again."
    elif status_code is None:
        user_msg = f"Could not reach {provider.capitalize()}. Check your connection and try again."
    else:
        user_msg = f"{provider.capitalize()} returned an error (HTTP {status_code}). Try again or choose another model."
    return SummarizeResponse(success=False, summary="", provider=provider, model=model_name, error=user_msg)


def _generate_demo_legal_briefing(doc_text: str, prompt: str) -> str:
    """
    Synthesizes a document-grounded, professional UK legal briefing for offline / demo mode.
    Directly answers practitioner prompts ('explain the document to me', 'summarise',
    'assess risks', 'extract obligations') using the document's actual substantive content
    and protected typed placeholders.
    """
    lower_t = doc_text.lower()
    lower_p = prompt.lower()

    # Extract all issued placeholders and structured tokens
    persons = list(dict.fromkeys(re.findall(r"\[PERSON \d+\]", doc_text)))
    orgs = list(dict.fromkeys(re.findall(r"\[ORG \d+\]", doc_text)))
    refs = list(dict.fromkeys(re.findall(r"\[(?:REF|MATTER|ACCOUNT|CARD|NI NUMBER|SORT CODE|POSTCODE|ADDRESS|PASSPORT|DRIVING LICENCE) \d+\]", doc_text)))
    amounts = list(dict.fromkeys(re.findall(r"(?:£|\$|€)\s?\d+(?:,\d{3})*(?:\.\d{2})?(?:\s*(?:million|billion|thousand|k|m))?|\[AMOUNT \d+\]", doc_text, re.IGNORECASE)))
    dates = list(dict.fromkeys(re.findall(r"\[DATE \d+\]|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}\b", doc_text, re.IGNORECASE)))
    all_tokens = list(dict.fromkeys(persons + orgs + refs + amounts))

    # Semantic Document Classification
    if "immigration health surcharge" in lower_t or "uk visas & immigration" in lower_t or "ihs" in lower_t:
        doc_class = "UK Visas & Immigration (UKVI) Health Surcharge Confirmation"
        doc_purpose = (
            "An official electronic confirmation notice from UK Visas & Immigration (UKVI) verifying "
            "successful payment of the Immigration Health Surcharge (IHS) linked to a UK visa application."
        )
        lead_person = persons[0] if persons else "[PERSON 1]"
        parties_desc = f"Applicant {lead_person} (Payer) under UKVI / Home Office immigration jurisdiction."
        key_provisions = [
            "Official confirmation that Immigration Health Surcharge payment has been received and processed.",
            "Allocation of a unique IHS reference number required to validate and submit the linked visa application.",
            "Requirement to present the IHS reference at any scheduled UKVI premium service centre or biometric appointment."
        ]
        next_steps = [
            "Input the issued IHS reference number into the pending online visa application form prior to declaration.",
            "Ensure the applicant presents the IHS reference number if attending an in-person biometric appointment.",
            "Retain payment proof and separate Worldpay transaction receipt on file for client immigration audit."
        ]
    elif "service agreement" in lower_t or "employment contract" in lower_t or ("employment" in lower_t and "remuneration" in lower_t):
        doc_class = "Executive Service Agreement / Employment Contract"
        doc_purpose = (
            "A legally binding employment agreement setting out executive duties, compensation, "
            "statutory obligations, confidentiality covenants, and post-termination restrictions."
        )
        co = orgs[0] if orgs else "[ORG 1]"
        exec_p = persons[0] if persons else "[PERSON 1]"
        parties_desc = f"Contracting parties: {co} (Company) and {exec_p} (Executive)."
        key_provisions = [
            "Formal appointment, reporting hierarchy, and core executive responsibilities.",
            "Remuneration package, benefits entitlement, and discretionary bonus structure.",
            "Post-termination restrictive covenants, non-solicitation, and intellectual property assignment."
        ]
        next_steps = [
            "Verify execution formalities and confirm counterpart exchange dates.",
            "Ensure payroll and benefits parameters are configured in accordance with contractual terms.",
            "Review enforceability of restrictive covenants under applicable employment law."
        ]
    elif "dispute" in lower_t or "escrow" in lower_t or "settlement" in lower_t or "claimant" in lower_t:
        doc_class = "Commercial Dispute & Settlement Memorandum"
        doc_purpose = (
            "A privileged legal memorandum reviewing ongoing commercial litigation, settlement terms, "
            "financial liabilities, and escrow disbursement preconditions."
        )
        parties_desc = f"Dispute parties: {', '.join(persons + orgs) if (persons or orgs) else 'Claimant and Defendant entities'}."
        key_provisions = [
            "Summary of contractual dispute background and monetary claims asserted.",
            "Agreed settlement terms, liability releases, and mutual discharge of claims.",
            "Escrow verification undertakings and regulatory conditions precedent to fund release."
        ]
        next_steps = [
            "Verify bank account and sort code credentials under UK MLR 2017 before executing disbursement.",
            "Secure senior partner verification for all formal undertakings to opposing solicitors.",
            "Finalise consent order documentation for filing with the court."
        ]
    elif "witness statement" in lower_t or "statement of truth" in lower_t:
        doc_class = "Witness Statement / Evidentiary Pleading"
        doc_purpose = (
            "A formal witness statement prepared under CPR Part 32 in support of judicial proceedings, "
            "setting out factual evidence and contemporaneous communications."
        )
        parties_desc = f"Deponent and parties: {', '.join(persons + orgs) if (persons or orgs) else 'Witness and litigation parties'}."
        key_provisions = [
            "Factual chronology of events and contemporaneous communications.",
            "Evidentiary exhibits cited in support of witness testimony.",
            "Signed statement of truth confirming personal belief in the veracity of the evidence."
        ]
        next_steps = [
            "Verify compliance with CPR Part 32 formal witness statement requirements.",
            "Ensure all exhibit references are cross-indexed against the trial bundle.",
            "Serve verified statement in accordance with court timetable directions."
        ]
    else:
        # Extract first non-header line as title
        clean_lines = [l.strip() for l in doc_text.splitlines() if l.strip() and not re.match(r"(?i)^(?:gmail|outlook|date:|from:|to:|subject:)", l)]
        doc_class = clean_lines[0][:80] if clean_lines else "Legal Matter Document"
        doc_purpose = f"A formal legal document concerning {doc_class}."
        parties_desc = f"{', '.join(persons + orgs) if (persons or orgs) else 'Parties as identified in matter record'}."
        key_provisions = [
            "Substantive rights, responsibilities, and terms as set out in the document.",
            "Operational provisions governing compliance, delivery, and performance.",
            "Statutory governance and professional record-keeping requirements."
        ]
        next_steps = [
            "Review substantive terms against client matter instructions.",
            "Ensure all confidential identifiers remain masked in accordance with SRA guidelines.",
            "Proceed with procedural requirements as indicated in the client matter file."
        ]

    # Prompt-Specific Delivery
    if "risk" in lower_p or "liabilit" in lower_p:
        body = [
            "### ⚖️ Legal Risk & Liability Assessment",
            f"**Document Classification:** {doc_class}",
            f"**Matter Scope:** {doc_purpose}",
            "",
            "#### 1. Core Contractual & Commercial Exposures",
            f"- **Financial Exposure:** {', '.join(amounts) if amounts else 'No direct monetary exposure identified in the current text.'}",
            f"- **Enforceability & Breach Risks:** Review of substantive clauses indicates active undertakings governing {parties_desc}",
            "- **Procedural Default Risk:** Non-compliance with stipulated conditions or deadlines may trigger financial penalties, enforcement actions, or statutory interest.",
            "",
            "#### 2. Regulatory & Governance Assessment",
            f"- **SRA Confidentiality:** {len(all_tokens)} sensitive identifiers remain safely masked under client-side control.",
            "- **AML / MLR Compliance:** Verify that all identity preconditions and client due diligence requirements are satisfied prior to formal commitment.",
            "",
            "#### 3. Recommended Risk Mitigation Actions",
            f"- {next_steps[0]}",
            f"- {next_steps[1]}",
            "- Conduct thorough cross-check of all exhibit and reference records before client dispatch."
        ]
        return "\n".join(body)

    elif "obligation" in lower_p or "deadline" in lower_p or "timetable" in lower_p:
        body = [
            "### 📅 Key Legal Obligations, Terms & Timetable",
            f"**Document Classification:** {doc_class}",
            f"**Matter Scope:** {doc_purpose}",
            "",
            "#### 1. Summary of Undertakings & Conditions Precedent",
            f"- Identified binding terms and obligations governing {parties_desc}",
            "- All reference numbers, accounts, and financial values remain masked and audit-compliant.",
            "",
            "#### 2. Key Procedural Obligations",
            f"- **Primary Obligation:** {key_provisions[0]}",
            f"- **Secondary Condition:** {key_provisions[1]}",
            f"- **Operational Requirement:** {key_provisions[2]}",
            "",
            "#### 3. Recommended Action Schedule",
            f"- 1. {next_steps[0]}",
            f"- 2. {next_steps[1]}",
            f"- 3. {next_steps[2]}"
        ]
        return "\n".join(body)

    elif "gdpr" in lower_p or "sra" in lower_p or "compliance" in lower_p:
        body = [
            "### 🛡️ Regulatory & SRA Governance Assessment",
            f"**Document Classification:** {doc_class}",
            "**Governance Framework:** UK GDPR, Data Protection Act 2018, SRA Standards & Regulations",
            "",
            "#### 1. Outbound Data Protection & PII Isolation",
            f"- **Zero-Exposure Guarantee:** {len(all_tokens)} sensitive identifiers were replaced with typed placeholders before dispatch.",
            "- **LLM Provider Isolation:** The external AI provider processes only typed tokens (`[PERSON 1]`, `[REF 1]`, etc.), preventing third-party data ingestion or training on client matter PII.",
            "",
            "#### 2. SRA Confidentiality & Conduct Compliance",
            "- Strict adherence to **SRA Code of Conduct Principle 2** (public trust) and **Principle 6.3** (client confidentiality).",
            "- Complete audit record maintained browser-side; unmasked restoration occurs strictly on the practitioner's local device.",
            "",
            "#### 3. Substantive Document Overview",
            f"- **Document Purpose:** {doc_purpose}",
            f"- **Involved Parties:** {parties_desc}"
        ]
        return "\n".join(body)

    else:
        # Universal plain-English legal executive briefing answering "explain the document to me"
        body = [
            "### 📋 Legal Executive Briefing",
            f"**Document Classification:** {doc_class}",
            "**Analysis Scope:** Document-Grounded Legal Explanation",
            "",
            "#### 1. Executive Summary & Purpose",
            doc_purpose,
            "",
            "#### 2. Key Parties & Protected Entities",
            f"- **Primary Parties / Roles:** {parties_desc}"
        ]
        if persons:
            body.append(f"- **Individuals Identified:** {', '.join(persons)}")
        if orgs:
            body.append(f"- **Organisations Identified:** {', '.join(orgs)}")
        body.append("")
        body.append("#### 3. Key Substantive References & Figures")
        if refs:
            body.append(f"- **Reference & Matter Numbers:** {', '.join(refs)}")
        if amounts:
            body.append(f"- **Financial Sums / Figures:** {', '.join(amounts)}")
        if dates:
            body.append(f"- **Key Dates / Milestones:** {', '.join(dates)}")
        if not refs and not amounts and not dates:
            body.append("- *No specific numerical reference or financial figures detected in protected text.*")
        body.append("")
        body.append("#### 4. Substantive Provisions & Legal Summary")
        for p in key_provisions:
            body.append(f"- {p}")
        body.append("")
        body.append("#### 5. Recommended Procedural Next Steps")
        for s in next_steps:
            body.append(f"- {s}")
        body.append("")
        body.append("---")
        body.append(f"*Note: All {len(all_tokens)} client-identifying details in this briefing remain masked with typed placeholders in compliance with SRA client confidentiality.*")
        return "\n".join(body)


async def execute_llm_summary(req: SummarizeRequest) -> SummarizeResponse:
    provider = req.provider.lower()
    prompt = req.instructions or "Please provide a concise legal summary of this protected document."

    system_prompt = (
        "You are an expert UK legal assistant reviewing a document that has been protected before being sent to you. "
        "Sensitive items have been replaced with typed placeholders in square brackets, such as [PERSON 1], [ORG 2], "
        "[ACCOUNT 1], [ADDRESS 1] or [DATE 1]. The same placeholder always refers to the same underlying item. "
        "Reason using these placeholders exactly as written: never guess, infer or invent the real values, never ask for them, "
        "and never alter or renumber a placeholder. Keep every placeholder you mention in the exact form it appears. "
        "Deliver professional, structured UK legal analysis."
    )

    # 1. Mock / Demo Mode for instant offline testing without API keys
    # Generates a document-grounded, professional UK legal briefing
    if req.api_key.strip() in ["", "demo", "mock", "test"]:
        doc_text = req.protected_text.strip()
        briefing = _generate_demo_legal_briefing(doc_text, prompt)
        return SummarizeResponse(
            success=True,
            summary=briefing,
            provider="demo-provider",
            model="simulated-legal-ai"
        )

    # 2. OpenAI Provider
    if provider == "openai":
        model_name = req.model or DEFAULT_MODELS["openai"]
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {req.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{prompt}\n\nDocument Text:\n{req.protected_text}"}
            ],
            "temperature": 0.2
        }
        try:
            async with httpx.AsyncClient(timeout=PROVIDER_TIMEOUT_SECONDS) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code != 200:
                    return _provider_error(provider, model_name, res.status_code, res.text, req.api_key)
                data = res.json()
                summary_text = data["choices"][0]["message"]["content"]
                return SummarizeResponse(success=True, summary=summary_text, provider=provider, model=model_name)
        except Exception as e:
            logger.exception("OpenAI call failed")
            return _provider_error(provider, model_name, None, repr(e), req.api_key)

    # 3. Anthropic Provider
    elif provider == "anthropic":
        model_name = req.model or DEFAULT_MODELS["anthropic"]
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": req.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": model_name,
            "max_tokens": 2000,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": f"{prompt}\n\nDocument Text:\n{req.protected_text}"}
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=PROVIDER_TIMEOUT_SECONDS) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code != 200:
                    return _provider_error(provider, model_name, res.status_code, res.text, req.api_key)
                data = res.json()
                summary_text = "".join([c.get("text", "") for c in data.get("content", [])])
                return SummarizeResponse(success=True, summary=summary_text, provider=provider, model=model_name)
        except Exception as e:
            logger.exception("Anthropic call failed")
            return _provider_error(provider, model_name, None, repr(e), req.api_key)

    # 4. Google Gemini Provider
    elif provider == "gemini":
        model_name = req.model or DEFAULT_MODELS["gemini"]
        # Key goes in a header, not the query string, so it never lands in access logs.
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {"x-goog-api-key": req.api_key, "Content-Type": "application/json"}
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {"parts": [{"text": f"{prompt}\n\nDocument Text:\n{req.protected_text}"}]}
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=PROVIDER_TIMEOUT_SECONDS) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code != 200:
                    return _provider_error(provider, model_name, res.status_code, res.text, req.api_key)
                data = res.json()
                summary_text = data["candidates"][0]["content"]["parts"][0]["text"]
                return SummarizeResponse(success=True, summary=summary_text, provider=provider, model=model_name)
        except Exception as e:
            logger.exception("Gemini call failed")
            return _provider_error(provider, model_name, None, repr(e), req.api_key)

    return SummarizeResponse(
        success=False,
        summary="",
        provider=provider,
        model="unknown",
        error=f"Unsupported provider: '{provider}'."
    )
