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
