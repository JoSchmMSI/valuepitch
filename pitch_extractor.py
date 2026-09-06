"""
ValuePitch — Pitch Extractor
==============================
Uses Claude Sonnet (primary) or Groq Llama (fallback) to dissect a
free-text pitch or idea description into structured PitchParameters.

This is the cornerstone of the product — every downstream calculation
depends on the accuracy of this extraction. Claude Sonnet is used
deliberately here for its superior structured-extraction capability.

Input:  raw pitch text (any length, any format)
Output: PitchParameters dict ready to feed into pitch_engine.py
"""

import json
import os
import requests
from pitch_engine import PitchParameters

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GROQ_KEY      = os.environ.get("GROQ_API_KEY", "")

EXTRACTION_SYSTEM = """You are a professional startup analyst and investment analyst.
Your ONLY job is to extract structured information from a pitch or business idea description.

You MUST respond with ONLY a valid JSON object — no markdown, no explanation, no preamble.

Extract the following fields. If a value is not mentioned, use the defaults provided.

{
  "company_name": "Name of the company or project (string, default: 'Unnamed Venture')",
  "sector": "Primary industry sector — one of: technology, fintech, healthtech, edtech, sustainability, logistics, manufacturing, retail, media, professional_services, other (string)",
  "business_model": "Revenue/business model — one of: saas_b2b, saas_b2c, marketplace, fintech, healthtech, edtech, proptech, ai_ml, ecommerce, logistics, manufacturing, sustainability, media_content, professional_svcs, general (string)",
  "geography": "Primary target geography/market (string, default: 'Europe')",
  "stage": "Development stage — one of: pre_revenue, seed, series_a, series_b_plus (string, default: 'seed')",
  "current_revenue": "Current annual revenue in EUR (number, default: 0)",
  "projected_revenue_yr1": "Projected annual revenue year 1 in EUR (number, default: 100000)",
  "projected_revenue_yr3": "Projected annual revenue year 3 in EUR (number, default: 500000)",
  "projected_revenue_yr5": "Projected annual revenue year 5 in EUR (number, default: 2000000)",
  "funding_ask": "Amount of funding sought in EUR (number, default: 250000)",
  "gross_margin_pct": "Expected gross margin as percentage 0-100 (number, default: 70)",
  "arpu": "Average revenue per user/customer per year in EUR (number, default: 500)",
  "tam_eur": "Total Addressable Market in EUR (number, default: 50000000)",
  "required_return_multiple": "Target investment return multiple for investor (number, default: 10)",
  "exit_year": "Target exit year from now (number, default: 5)",
  "team_score": "Team quality score 0-10 based on description (number)",
  "market_score": "Market opportunity score 0-10 (number)",
  "product_score": "Product/solution quality score 0-10 (number)",
  "traction_score": "Traction/validation score 0-10 (number)",
  "competition_score": "Competitive positioning score 0-10 (number)",
  "pitch_summary": "One paragraph summary of the business in plain language (string)",
  "key_risks": "Top 3 risks identified from the pitch as a list (array of strings)",
  "key_strengths": "Top 3 strengths identified from the pitch as a list (array of strings)"
}

Rules:
- Extract numbers from text (e.g. '€500K' → 500000, '2M users' → use to estimate revenue)
- Stage detection rules (apply in order):
  1. If current revenue = 0 OR pitch mentions "free pilots", "no revenue", "pre-revenue", "zero revenue", "pilot customers" with no payment → use pre_revenue
  2. If revenue exists but < EUR 500K ARR and raising first round → use seed
  3. If revenue EUR 500K–3M ARR → use series_a
  4. If revenue > EUR 3M ARR → use series_b_plus
  5. If truly unclear → use seed
- Scores should be based on what is actually described — do NOT inflate
- business_model must exactly match one of the enum values listed
- stage must exactly match one of the enum values listed
- ONLY return the JSON object, nothing else"""


def extract_from_pitch(raw_text: str,
                       user_type: str = "founder",
                       max_tokens: int = 1000) -> dict:
    """
    Extract structured parameters from raw pitch text.
    Returns a dict ready to unpack into PitchParameters.
    """
    prompt = f"""User type: {user_type}

Pitch / idea description:
{raw_text}

Extract all parameters from this pitch into the JSON format specified."""

    # Layer 1: Claude Sonnet (primary — superior extraction accuracy)
    if ANTHROPIC_KEY:
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": max_tokens,
                    "system": EXTRACTION_SYSTEM,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            if r.status_code == 200:
                blocks = r.json().get("content", [])
                text   = "".join(b.get("text", "") for b in blocks
                                 if b.get("type") == "text")
                result = _parse_json(text)
                if result:
                    return result
        except Exception as e:
            print(f"Claude extraction error: {e}")

    # Layer 2: Groq Llama (fallback)
    if GROQ_KEY:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "max_tokens": max_tokens,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": EXTRACTION_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                },
                timeout=30,
            )
            if r.status_code == 200:
                choices = r.json().get("choices", [])
                if choices:
                    text   = choices[0].get("message", {}).get("content", "")
                    result = _parse_json(text)
                    if result:
                        return result
        except Exception as e:
            print(f"Groq extraction error: {e}")

    # Layer 3: Structured defaults (if both fail)
    return _defaults()


def _parse_json(text: str) -> dict:
    """Parse JSON from model output robustly."""
    try:
        text = text.strip()
        # Strip markdown fences if present
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                try:
                    return json.loads(part)
                except Exception:
                    continue
        return json.loads(text)
    except Exception:
        return {}


def _defaults() -> dict:
    """Safe defaults when extraction fails entirely."""
    return {
        "company_name": "Unnamed Venture",
        "sector": "technology",
        "business_model": "saas_b2b",
        "geography": "Europe",
        "stage": "seed",
        "current_revenue": 0,
        "projected_revenue_yr1": 100_000,
        "projected_revenue_yr3": 500_000,
        "projected_revenue_yr5": 2_000_000,
        "funding_ask": 250_000,
        "gross_margin_pct": 70,
        "arpu": 500,
        "tam_eur": 50_000_000,
        "required_return_multiple": 10.0,
        "exit_year": 5,
        "team_score": 5,
        "market_score": 5,
        "product_score": 5,
        "traction_score": 3,
        "competition_score": 5,
        "pitch_summary": "No summary available — please check your API key configuration.",
        "key_risks": ["Data extraction unavailable", "Manual input required", "Verify API key"],
        "key_strengths": ["Analysis pending", "Input required", ""],
    }


def dict_to_params(d: dict, user_type: str = "founder") -> PitchParameters:
    """Convert extracted dict to PitchParameters dataclass."""
    valid_models  = list(__import__('pitch_engine').SECTOR_MULTIPLES.keys())
    valid_stages  = list(__import__('pitch_engine').SURVIVAL_RATES.keys())
    bm = d.get("business_model", "general")
    st = d.get("stage", "seed")
    return PitchParameters(
        company_name              = str(d.get("company_name", "Unnamed Venture")),
        sector                    = str(d.get("sector", "technology")),
        business_model            = bm if bm in valid_models else "general",
        geography                 = str(d.get("geography", "Europe")),
        stage                     = st if st in valid_stages else "seed",
        user_type                 = user_type,
        current_revenue           = float(d.get("current_revenue", 0)),
        projected_revenue_yr1     = float(d.get("projected_revenue_yr1", 100_000)),
        projected_revenue_yr3     = float(d.get("projected_revenue_yr3", 500_000)),
        projected_revenue_yr5     = float(d.get("projected_revenue_yr5", 2_000_000)),
        funding_ask               = float(d.get("funding_ask", 250_000)),
        gross_margin_pct          = float(d.get("gross_margin_pct", 70)),
        arpu                      = float(d.get("arpu", 500)),
        tam_eur                   = float(d.get("tam_eur", 50_000_000)),
        required_return_multiple  = float(d.get("required_return_multiple", 10.0)),
        exit_year                 = int(d.get("exit_year", 5)),
        team_score                = float(d.get("team_score", 5)),
        market_score              = float(d.get("market_score", 5)),
        product_score             = float(d.get("product_score", 5)),
        traction_score            = float(d.get("traction_score", 3)),
        competition_score         = float(d.get("competition_score", 5)),
    )


def get_pitch_meta(extracted: dict) -> dict:
    """Pull the non-financial metadata from extracted dict for display."""
    return {
        "summary":   extracted.get("pitch_summary", ""),
        "risks":     extracted.get("key_risks", []),
        "strengths": extracted.get("key_strengths", []),
    }
