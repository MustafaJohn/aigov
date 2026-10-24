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
    if req.api_key.strip() in ["", "demo", "mock", "test"]:
        lower_prompt = prompt.lower()

        if "risk" in lower_prompt or "liabilit" in lower_prompt:
            mock_summary = (
                "### ⚖️ Legal Risk & Liability Analysis\n\n"
                "**1. Core Exposure & Settlement Scope**\n"
                "- The proposed settlement involving **XYZ_1** (Claimant) and **XXX_1** (Respondent) resolves claims under **XXX_11**.\n"
                "- Payment of **XYZ_10** into escrow must be conditioned upon irrevocable withdrawal of High Court proceedings with no admission of liability.\n\n"
                "**2. Regulatory & Banking Risks**\n"
                "- Transfers to banking facility **XYZ_4** (Sort Code: **XXX_5**, Account: **XYZ_6**) require verification against UK Money Laundering Regulations (MLR 2017) and source of funds verification.\n\n"
                "**3. Enforcement & Undertakings Vulnerability**\n"
                "- Managing partner sign-off is mandatory under SRA Standards & Regulations. Failure to execute countersignatures by the target deadline exposes **XYZ_1** to revived litigation."
            )
        elif "obligation" in lower_prompt or "deadline" in lower_prompt or "action item" in lower_prompt:
            mock_summary = (
                "### 📅 Key Obligations & Procedural Deadlines\n\n"
                "| Party | Obligation / Action Item | Deadline / Condition |\n"
                "|---|---|---|\n"
                "| **XYZ_1** | Tender settlement sum of **XYZ_10** into client escrow | Prior to deed execution |\n"
                "| **XXX_1** | Formal withdrawal of London High Court Action **XXX_11** | Simultaneous with escrow receipt |\n"
                "| **XXX_1** & **XXX_7** | Sign and countersign formal deed of execution | Strict deadline: **30 October 2026** |\n"
                "| Managing Partner | Formal SRA regulatory sign-off on undertakings | Condition precedent to disbursement |"
            )
        elif "memo" in lower_prompt or "advice" in lower_prompt:
            mock_summary = (
                "### 📝 Client Advice Memorandum\n\n"
                "**TO:** Client Executive Committee / In-House Legal\n"
                "**FROM:** Legal Advisory Team\n"
                "**MATTER:** Commercial Dispute Resolution & Escrow Settlement (**XXX_11**)\n\n"
                "**1. Executive Recommendation**\n"
                "We recommend proceeding with the drafted settlement structure subject to two key conditions: (i) holding the **XYZ_10** disbursement until the formal notice of discontinuance is stamped by the court, and (ii) obtaining SRA-compliant identity checks on **XXX_1**.\n\n"
                "**2. Tactical Posture**\n"
                "Settling at this stage averts protracted High Court trial costs. The terms appropriately extinguish all respondent claims across all jurisdictions."
            )
        elif "rebuttal" in lower_prompt or "counter" in lower_prompt or "defence" in lower_prompt:
            mock_summary = (
                "### 🥊 Rebuttal Points & Procedural Defences\n\n"
                "1. **Jurisdictional & Standing Defects:** The claims in **XXX_11** fail to establish direct contractual privity for damages exceeding the verified consideration.\n"
                "2. **Mitigation Failure:** The opposing party has not demonstrated reasonable steps to mitigate alleged losses following the initial commercial rupture.\n"
                "3. **Conditionality of Offer:** Any concessions concerning **XYZ_10** remain strictly *Without Prejudice Save as to Costs* and cannot be cited in open court if negotiations collapse."
            )
        elif "timeline" in lower_prompt or "chronolog" in lower_prompt:
            mock_summary = (
                "### ⏳ Chronological Events & Timeline\n\n"
                "- **Prior to Dispute:** Commercial dealings between Claimant **XYZ_1** and Respondent **XXX_1**.\n"
                "- **Litigation Commencement:** Filing of London High Court Action **XXX_11**.\n"
                "- **19 October 2026:** Confidential legal memorandum issued evaluating settlement proposal of **XYZ_10**.\n"
                "- **Upcoming (30 October 2026):** Execution deadline for deed signed by **XXX_1** and counsel **XXX_7**."
            )
        else:
            mock_summary = (
                "### 📋 Executive Legal Summary (Redacted Context)\n\n"
                "**1. Parties Involved:**\n"
                "- **Claimant:** **XYZ_1**\n"
                "- **Respondent:** **XXX_1** (represented by legal counsel **XXX_7** at **XYZ_8**)\n\n"
                "**2. Core Dispute & Subject Matter:**\n"
                "- The matter concerns ongoing commercial dispute and litigation under High Court Action **XXX_11**.\n\n"
                "**3. Proposed Terms & Financial Consideration:**\n"
                "- **XYZ_1** agrees to tender a settlement sum of **XYZ_10** into client escrow at banking facility **XYZ_4** (Sort Code: **XXX_5**, Account: **XYZ_6**).\n"
                "- In exchange, **XXX_1** will permanently withdraw all claims in London High Court Action **XXX_11**.\n\n"
                "**4. Compliance & Execution Requirements:**\n"
                "- Senior managing partner sign-off required for SRA undertakings.\n"
                "- Deed of execution must be signed and countersigned by **30 October 2026**."
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
