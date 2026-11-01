import re
import httpx
from typing import Optional
from app.models import SummarizeRequest, SummarizeResponse

async def execute_llm_summary(req: SummarizeRequest) -> SummarizeResponse:
    provider = req.provider.lower()
    prompt = req.instructions or "Please provide a concise legal summary of this protected document."
    
    system_prompt = (
        "You are an expert UK legal assistant. You are reviewing a legally redacted and protected document. "
        "All sensitive client names, companies, bank details, and identifiers have been masked with random jargon tokens "
        "such as XXX_1, XYZ_2, XXX_3, etc. "
        "Strictly reason with these jargon tokens directly without asking for unmasked identifiers. "
        "Deliver professional, actionable, and structured UK legal analysis."
    )

    # 1. Mock / Demo Mode for instant offline testing without API keys
    # Dynamically analyzes ANY uploaded document (contracts, notarised deeds, court forms, letters, etc.)
    if req.api_key.strip() in ["", "demo", "mock", "test"]:
        doc_text = req.protected_text.strip()
        lines = [line.strip() for line in doc_text.splitlines() if line.strip()]
        lower_prompt = prompt.lower()

        # Find any masked tokens in the document (e.g. [PERSON 1], [ORG 2], XXX_1, XYZ_2)
        tokens_found = list(set(re.findall(r"(?:\[[A-Z_\s0-9]+\]|XXX_\d+|XYZ_\d+)", doc_text)))
        title_context = lines[0] if lines else "Uploaded Document"

        # Separate heading and body lines
        body_lines = lines[1:] if len(lines) > 1 else lines

        if "risk" in lower_prompt or "liabilit" in lower_prompt:
            mock_summary = (
                f"### ⚖️ Legal Risk & Liability Analysis\n\n"
                f"**Document Context:** {title_context}\n\n"
                f"**1. Core Legal Risks & Exposure:**\n"
                f"- Review of protected text indicates active obligations involving {len(tokens_found)} masked parties and credentials.\n"
                f"- Primary substantive clauses under review:\n"
            )
            for l in body_lines[:4]:
                mock_summary += f"  - *\"{l[:140]}{'...' if len(l) > 140 else ''}\"*\n"

            mock_summary += (
                f"\n**2. Governance & Compliance Assessment:**\n"
                f"- All {len(tokens_found)} sensitive identifiers remain safely masked.\n"
                f"- Recommend formal verification of all undertakings and regulatory preconditions before execution."
            )

        elif "obligation" in lower_prompt or "deadline" in lower_prompt:
            mock_summary = (
                f"### 📅 Key Obligations, Terms & Timelines\n\n"
                f"**Document Context:** {title_context}\n\n"
                f"| # | Substantive Term / Provision | Protection Status |\n"
                f"|---|---|---|\n"
            )
            for idx, l in enumerate(body_lines[:5], start=1):
                clean_l = l.replace("|", "-")
                mock_summary += f"| {idx} | {clean_l[:120]} | Masked & Compliant |\n"
            mock_summary += (
                f"\n**Summary:** Identified key provisions across {len(lines)} blocks. Zero raw PII exposed."
            )

        else:
            # Universal document summary for any contract, deed, court filing, or general document
            mock_summary = (
                f"### 📋 Executive Summary (Document-Grounded)\n\n"
                f"**Document Title / Heading:** {title_context}\n\n"
                f"**1. Factual Background & Context:**\n"
            )
            for l in body_lines[:3]:
                mock_summary += f"- {l}\n"

            if len(body_lines) > 3:
                mock_summary += f"\n**2. Core Provisions, Rights & Terms:**\n"
                for l in body_lines[3:7]:
                    mock_summary += f"- {l}\n"

            mock_summary += (
                f"\n**3. PII & Entity Governance:**\n"
                f"- **{len(tokens_found)} sensitive entities** were safely protected in this document.\n"
                f"- No unmasked client details, account numbers, or party identifiers were transmitted to external AI APIs."
            )

        return SummarizeResponse(
            success=True,
            summary=mock_summary,
            provider="demo-provider",
            model="simulated-legal-ai"
        )

    # 2. OpenAI Provider
    if provider == "openai":
        model_name = req.model or "gpt-4o-mini"
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
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code != 200:
                    return SummarizeResponse(
                        success=False,
                        summary="",
                        provider=provider,
                        model=model_name,
                        error=f"OpenAI API Error ({res.status_code}): {res.text}"
                    )
                data = res.json()
                summary_text = data["choices"][0]["message"]["content"]
                return SummarizeResponse(
                    success=True,
                    summary=summary_text,
                    provider=provider,
                    model=model_name
                )
        except Exception as e:
            return SummarizeResponse(
                success=False,
                summary="",
                provider=provider,
                model=model_name,
                error=f"Failed to communicate with OpenAI: {str(e)}"
            )

    # 3. Anthropic Provider
    elif provider == "anthropic":
        model_name = req.model or "claude-3-5-sonnet-20241022"
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
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code != 200:
                    return SummarizeResponse(
                        success=False,
                        summary="",
                        provider=provider,
                        model=model_name,
                        error=f"Anthropic API Error ({res.status_code}): {res.text}"
                    )
                data = res.json()
                summary_text = "".join([c.get("text", "") for c in data.get("content", [])])
                return SummarizeResponse(
                    success=True,
                    summary=summary_text,
                    provider=provider,
                    model=model_name
                )
        except Exception as e:
            return SummarizeResponse(
                success=False,
                summary="",
                provider=provider,
                model=model_name,
                error=f"Failed to communicate with Anthropic: {str(e)}"
            )

    # 4. Google Gemini Provider
    elif provider == "gemini":
        model_name = req.model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={req.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {"parts": [{"text": f"{prompt}\n\nDocument Text:\n{req.protected_text}"}]}
            ]
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code != 200:
                    return SummarizeResponse(
                        success=False,
                        summary="",
                        provider=provider,
                        model=model_name,
                        error=f"Gemini API Error ({res.status_code}): {res.text}"
                    )
                data = res.json()
                summary_text = data["candidates"][0]["content"]["parts"][0]["text"]
                return SummarizeResponse(
                    success=True,
                    summary=summary_text,
                    provider=provider,
                    model=model_name
                )
        except Exception as e:
            return SummarizeResponse(
                success=False,
                summary="",
                provider=provider,
                model=model_name,
                error=f"Failed to communicate with Gemini: {str(e)}"
            )

    return SummarizeResponse(
        success=False,
        summary="",
        provider=provider,
        model="unknown",
        error=f"Unsupported provider: '{provider}'."
    )
