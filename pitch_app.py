"""
ValuePitch — Pitch & Idea Valuation Intelligence
==================================================
AI-powered valuation engine for startups, incubators,
investors, and corporate evaluators.

Input:  free-text pitch or idea description
Output: three-scenario valuation (Conservative / Base / Optimistic)
        across 3 / 5 / 10-year horizons with PESTEL + comparables.

Built on the same data infrastructure as MSI Engine and Verticore.
(c) 2026 J. Schmidt. Proprietary & Confidential.
"""

import streamlit as st
import os
import json
import requests
from datetime import datetime

import pitch_engine as pe
import pitch_extractor as px
import pitch_live_data as pld
import pitch_exports as pex

# ── Config ────────────────────────────────────────────────────────────────────
def _secret(key, default=""):
    try:
        return st.secrets.get(key, os.environ.get(key, default))
    except Exception:
        return os.environ.get(key, default)

ANTHROPIC_KEY = _secret("ANTHROPIC_API_KEY")
GROQ_KEY      = _secret("GROQ_API_KEY")
CLR           = "#1A3A5C"   # ValuePitch deep navy
CLR2          = "#C9A227"   # gold accent

st.set_page_config(
    page_title="ValuePitch · Pitch Valuation Intelligence",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
:root{{
  --bg:#F0F2F5; --white:#FFFFFF; --border:#CDD2DB; --text:#0D1117;
  --muted:#52596B; --navy:{CLR}; --gold:{CLR2};
}}
html,body,[data-testid="stAppViewContainer"]{{
  background:var(--bg)!important; font-family:'Inter',sans-serif!important;
}}
[data-testid="stSidebar"]{{display:none!important;}}
#MainMenu,footer,header{{visibility:hidden;}}
.block-container{{padding-top:0.5rem!important;padding-bottom:2rem!important;}}

.vp-hdr{{background:#FFFFFF;border-radius:8px;padding:16px 24px;
  margin-bottom:20px;display:flex;align-items:center;
  justify-content:space-between;border:1px solid #CDD2DB;
  box-shadow:0 1px 4px rgba(0,0,0,0.06);}}
.vp-title{{font-size:1.3rem;font-weight:800;color:#14181F;letter-spacing:-0.02em;}}
.vp-sub{{font-size:0.64rem;font-weight:700;letter-spacing:0.2em;
  text-transform:uppercase;color:#7A8499;margin-top:4px;}}
.vp-copy{{font-size:0.62rem;color:#52596B;margin-top:4px;
  letter-spacing:0.03em;font-weight:500;}}

.sec{{font-size:0.72rem;font-weight:700;letter-spacing:0.18em;
  text-transform:uppercase;color:var(--muted);border-bottom:1px solid #C4CAD6;
  padding-bottom:7px;margin:26px 0 15px 0;}}

[data-testid="stSelectbox"] label,
[data-testid="stNumberInput"] label,
[data-testid="stTextArea"] label,
[data-testid="stSlider"] label{{
  font-size:0.68rem!important;font-weight:600!important;
  letter-spacing:0.08em!important;text-transform:uppercase!important;
  color:var(--muted)!important;}}

.val-card{{border-radius:10px;padding:22px 24px;
  box-shadow:0 2px 12px rgba(0,0,0,0.12);margin-bottom:8px;}}
.val-label{{font-size:0.6rem;font-weight:700;letter-spacing:0.2em;
  text-transform:uppercase;color:rgba(255,255,255,0.65);margin-bottom:4px;}}
.val-num{{font-size:2.4rem;font-weight:800;color:#FFFFFF;line-height:1;}}
.val-sub{{font-size:0.72rem;color:rgba(255,255,255,0.7);margin-top:8px;}}

.score-bar-bg{{background:#E5E7EB;border-radius:4px;height:8px;
  width:100%;margin:6px 0;}}
.note{{background:#FBF7EC;border-left:3px solid {CLR2};
  border-radius:0 6px 6px 0;padding:11px 15px;font-size:0.78rem;
  color:#5A4A15;margin:10px 0;}}
.prov{{font-size:0.68rem;color:#7A8499;margin-top:6px;line-height:1.5;}}
.strength{{background:#EDF7EE;border-left:3px solid #2E7D32;
  border-radius:0 6px 6px 0;padding:8px 14px;font-size:0.8rem;
  color:#1A3A1C;margin:4px 0;}}
.risk{{background:#FEF2F2;border-left:3px solid #C62828;
  border-radius:0 6px 6px 0;padding:8px 14px;font-size:0.8rem;
  color:#3A0A0A;margin:4px 0;}}
.pestel-card{{background:#FFFFFF;border:1px solid #CDD2DB;
  border-radius:8px;padding:14px 18px;margin-bottom:8px;}}
.pestel-letter{{font-size:1.4rem;font-weight:800;color:{CLR};}}
.pestel-title{{font-size:0.85rem;font-weight:700;color:#0D1117;}}
.pestel-body{{font-size:0.8rem;color:#52596B;margin-top:4px;line-height:1.5;}}
</style>
""", unsafe_allow_html=True)

# ── AI layer helpers ──────────────────────────────────────────────────────────
def ai_call(system: str, user: str, max_tokens: int = 600) -> str:
    """Call Claude primary, Groq fallback."""
    if ANTHROPIC_KEY:
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY,
                         "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-sonnet-4-6",
                      "max_tokens": max_tokens,
                      "system": system,
                      "messages": [{"role": "user", "content": user}]},
                timeout=30,
            )
            if r.status_code == 200:
                blocks = r.json().get("content", [])
                return "".join(b.get("text","") for b in blocks
                               if b.get("type") == "text")
        except Exception:
            pass
    if GROQ_KEY:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}",
                         "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile",
                      "max_tokens": max_tokens, "temperature": 0.3,
                      "messages": [{"role": "system","content": system},
                                   {"role": "user","content": user}]},
                timeout=30,
            )
            if r.status_code == 200:
                choices = r.json().get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
        except Exception:
            pass
    return ""


def _extract_json(text: str) -> dict:
    """Extract JSON from AI response — handles fences, truncation, partial output."""
    if not text:
        return {}
    text = text.strip()
    # Find opening brace
    try:
        start = text.index("{")
    except ValueError:
        return {}
    # Try full parse first
    try:
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except Exception:
        pass
    # JSON truncated — try to repair by appending closing braces
    partial = text[start:]
    for suffix in ['"}', '"}}', '"}}}']:
        try:
            return json.loads(partial + suffix)
        except Exception:
            pass
    return {}


def _flatten_values(data: dict) -> dict:
    """
    Convert any nested dict/list values to plain strings.
    Claude sometimes returns {"political": {"summary": "...", "factors": [...]}}
    This flattens those into {"political": "summary. factor1. factor2."}
    """
    result = {}
    for k, v in data.items():
        if k.startswith("_"):
            result[k] = v
            continue
        if isinstance(v, str):
            result[k] = v
        elif isinstance(v, dict):
            # Extract summary or first string value, then append factors if any
            parts = []
            if "summary" in v:
                parts.append(str(v["summary"]))
            if "factors" in v and isinstance(v["factors"], list):
                for f in v["factors"][:3]:
                    if isinstance(f, dict):
                        parts.append(str(f.get("factor", f.get("description", ""))))
                    elif isinstance(f, str):
                        parts.append(f)
            if not parts:
                parts = [str(vv) for vv in v.values() if isinstance(vv, str)][:2]
            result[k] = " ".join(parts) if parts else str(v)
        elif isinstance(v, list):
            result[k] = " ".join(str(i) for i in v[:3])
        else:
            result[k] = str(v)
    return result


def _call_claude_only(system: str, prompt: str, max_tokens: int = 700) -> str:
    """
    Call Claude API directly — no Groq fallback for PESTEL/Porter.
    Groq's api.groq.com is blocked by Streamlit Cloud's egress policy.
    Claude-only with 20-second timeout to avoid long waits on failure.
    """
    if not ANTHROPIC_KEY:
        return ""
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
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45,
        )
        if r.status_code == 200:
            blocks = r.json().get("content", [])
            return "".join(b.get("text", "") for b in blocks
                           if b.get("type") == "text")
        return ""
    except Exception:
        return ""


def generate_pestel(sector: str, geography: str, business_model: str) -> dict:
    """
    Generate PESTEL specific to sector + geography via Claude.
    Uses proven flat-string prompt format.
    Never caches failures.
    """
    cache_key = f"pestel_{sector}_{geography}_{business_model}"
    # Only return cache if it has real content — never return failure messages
    if cache_key in st.session_state:
        cached = st.session_state[cache_key]
        REQUIRED = {"political","economic","social","technological","environmental","legal"}
        if REQUIRED.issubset(cached.keys()) and not any(
            "Unable to generate" in str(v) or "Please retry" in str(v)
            for v in cached.values()
        ):
            return cached
        del st.session_state[cache_key]

    REQUIRED = {"political","economic","social","technological","environmental","legal"}

    system = (
        "You are a strategy analyst. Respond ONLY with a flat JSON object "
        "where each value is a plain string of exactly 2 sentences maximum. "
        "Be concise. No nested objects. No arrays. No markdown. No explanation."
    )
    prompt = (
        f"Write a PESTEL analysis for: Sector={sector}, Geography={geography}, "
        f"Business model={business_model}.\n"
        f"Be specific to {geography} and {sector} — name real regulations, market dynamics, "
        f"named players, actual trends.\n"
        f"Return this exact structure with string values only:\n"
        + '{"political":"...","economic":"...","social":"...","technological":"...","environmental":"...","legal":"..."}'
    )

    result = _call_claude_only(system, prompt, max_tokens=900)
    data   = _flatten_values(_extract_json(result))

    if data and REQUIRED.issubset(data.keys()):
        st.session_state[cache_key] = data
        return data

    # Return honest failure — never cache it
    return {k: f"Unable to generate analysis for {sector} / {geography}. "
               f"Please retry — Claude API required."
            for k in REQUIRED} | {"_is_fallback": True}


def generate_porter(sector: str, business_model: str) -> dict:
    """
    Generate Porter's Five Forces specific to sector via Claude.
    Uses proven flat-dict prompt format. Never caches failures.
    """
    cache_key = f"porter_{sector}_{business_model}"
    if cache_key in st.session_state:
        cached = st.session_state[cache_key]
        REQUIRED_P = {"rivalry","new_entrants","suppliers","buyers","substitutes"}
        if REQUIRED_P.issubset(cached.keys()) and not any(
            "Unable to generate" in str(v) or "Please retry" in str(v)
            for v in cached.values()
        ):
            return cached
        del st.session_state[cache_key]

    REQUIRED = {"rivalry","new_entrants","suppliers","buyers","substitutes"}

    system = (
        "You are a strategy analyst. Respond ONLY with a flat JSON object. "
        "No markdown. No explanation. No nested arrays."
    )
    _company_ctx = f" Company: {company_description}." if company_description else ""
    prompt = (
        f"Write Porter's Five Forces for: Sector={sector}, Model={business_model}.{_company_ctx}\n"
        f"Name the ACTUAL direct competitors for THIS specific business (not generic sector giants).\n"
        f"Name real companies, real regulations, real dynamics relevant to this exact market.\n"
        f"Return this exact structure:\n"
        + '{"rivalry":{"level":"High/Medium/Low","note":"2-3 specific sentences"},'
        + '"new_entrants":{"level":"High/Medium/Low","note":"2-3 specific sentences"},'
        + '"suppliers":{"level":"High/Medium/Low","note":"2-3 specific sentences"},'
        + '"buyers":{"level":"High/Medium/Low","note":"2-3 specific sentences"},'
        + '"substitutes":{"level":"High/Medium/Low","note":"2-3 specific sentences"}}'
    )

    result = _call_claude_only(system, prompt, max_tokens=1200)
    data   = _extract_json(result)

    # Validate structure — each value needs level + note
    if data and REQUIRED.issubset(data.keys()):
        valid = all(
            isinstance(v, dict) and "level" in v and "note" in v
            for k, v in data.items() if k in REQUIRED
        )
        if valid:
            st.session_state[cache_key] = data
            return data

    return {k: {"level": "Medium",
                "note": f"Unable to generate analysis for {sector}. Please retry."}
            for k in REQUIRED} | {"_is_fallback": True}


# ── User type options ─────────────────────────────────────────────────────────
USER_TYPES = {
    "Founder / Entrepreneur":     ("founder",    "You are evaluating your own idea or venture."),
    "Investor / VC":              ("investor",   "You are assessing an investment opportunity."),
    "Incubator / Accelerator":    ("assessor",   "You are evaluating a pitch for programme selection."),
    "Corporate / Strategic Buyer":("corporate",  "You are assessing for acquisition or partnership."),
}

# ── Formatters ────────────────────────────────────────────────────────────────
def fmt(v): return pe.fmt_eur(v)

def score_color(s):
    if s >= 70: return "#2E7D32"
    if s >= 50: return "#C9A227"
    return "#C62828"

def level_color(l):
    return {"High":"#C62828","Medium":"#C9A227","Low":"#2E7D32"}.get(l,"#52596B")


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="vp-hdr">
  <div>
    <div class="vp-title">◆ Value<span style="color:{CLR};">Pitch</span></div>
    <div class="vp-sub">Pitch & Idea Valuation Intelligence</div>
    <div class="vp-copy">&copy; 2026 J. Schmidt &nbsp;&middot;&nbsp;
      Proprietary &amp; Confidential &nbsp;&middot;&nbsp; All rights reserved</div>
  </div>
  <div style="font-size:0.72rem;color:#52596B;text-align:right;line-height:1.6;">
    Live analysis &nbsp;&middot;&nbsp;
    <strong style="color:#0D1117;">{datetime.now().strftime('%d %b %Y, %H:%M')}</strong>
    <br><span style="font-size:0.64rem;color:#9BAEC8;">
    AI analysis engine &nbsp;&middot;&nbsp; Financial model engine &nbsp;&middot;&nbsp;
    Live market benchmarks</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Step 1: User type ─────────────────────────────────────────────────────────
st.markdown('<div class="sec">Step 1 &mdash; Who are you?</div>',
            unsafe_allow_html=True)

ut_col1, ut_col2 = st.columns([2, 3])
with ut_col1:
    user_type_label = st.selectbox(
        "I am using ValuePitch as a",
        list(USER_TYPES.keys()),
        key="user_type_sel",
    )
user_type_code, user_type_desc = USER_TYPES[user_type_label]
with ut_col2:
    st.markdown(f"""<div style="background:#FFFFFF;border:1px solid #CDD2DB;
      border-radius:6px;padding:12px 16px;margin-top:22px;
      font-size:0.85rem;color:#52596B;">{user_type_desc}</div>""",
      unsafe_allow_html=True)

# ── Step 2: Pitch input ───────────────────────────────────────────────────────
st.markdown('<div class="sec">Step 2 &mdash; Describe the pitch or idea</div>',
            unsafe_allow_html=True)

pitch_text = st.text_area(
    "Paste your pitch, idea description, or executive summary",
    height=180,
    placeholder=(
        "Example: We are building a B2B SaaS platform for industrial companies "
        "to monitor supply chain risk in real time. Current ARR: EUR 120K. "
        "Targeting EUR 2M ARR in 3 years. Seeking EUR 500K seed funding. "
        "Operating in Germany and Nordics. Team of 4, 2 years product traction."
    ),
    key="pitch_input",
)

analyse_btn = st.button(
    "Analyse & Value",
    type="primary",
    disabled=not pitch_text.strip(),
    key="analyse_btn",
)

# ── Run extraction + valuation ─────────────────────────────────────────────────
if analyse_btn and pitch_text.strip():
    with st.spinner("Extracting parameters and analyzing the pitch..."):
        extracted = px.extract_from_pitch(pitch_text, user_type_code)
        params    = px.dict_to_params(extracted, user_type_code)
        meta      = px.get_pitch_meta(extracted)
        st.session_state["extracted"]    = extracted
        st.session_state["params"]       = params
        st.session_state["meta"]         = meta
        st.session_state["valuation"]    = pe.compute_valuation(params)
        # Clear ALL analysis caches on every new pitch submission
        for k in list(st.session_state.keys()):
            if any(k.startswith(p) for p in ["pestel_","porter_","enrich_","dcf_","mc_"]):
                del st.session_state[k]
        if "adj_geo" in st.session_state:
            del st.session_state["adj_geo"]

if analyse_btn and pitch_text.strip():
    with st.spinner("Pulling live market data (Eurostat + OECD)..."):
        _params     = st.session_state.get("params")
        if _params:
            _ekey = f"enrich_{_params.business_model}_{_params.geography}"
            if _ekey not in st.session_state:
                _enr = pld.enrich_with_live_data(
                    _params.business_model, _params.geography)
                st.session_state[_ekey] = _enr
                if _enr.get("live_tam_eur"):
                    _params.tam_eur = _enr["live_tam_eur"]
                    st.session_state["params"]    = _params
                    st.session_state["valuation"] = pe.compute_valuation(_params)

# ── Show results if we have them ───────────────────────────────────────────────
if "valuation" in st.session_state:
    result = st.session_state["valuation"]
    params = st.session_state["params"]
    meta   = st.session_state["meta"]
    extr   = st.session_state["extracted"]

    # ── Extracted parameters confirmation ─────────────────────────────────────
    st.markdown('<div class="sec">Extracted parameters — verify and adjust</div>',
                unsafe_allow_html=True)

    if meta.get("summary"):
        st.markdown(f"""<div style="background:#FFFFFF;border:1px solid #CDD2DB;
          border-radius:8px;padding:14px 18px;margin-bottom:16px;
          font-size:0.85rem;color:#0D1117;line-height:1.6;">
          <strong>AI Summary:</strong> {meta['summary']}</div>""",
          unsafe_allow_html=True)

    e1, e2, e3, e4 = st.columns(4)
    with e1:
        new_stage = st.selectbox(
            "Stage", ["pre_revenue","seed","series_a","series_b_plus"],
            index=["pre_revenue","seed","series_a","series_b_plus"].index(params.stage),
            key="adj_stage")
    with e2:
        new_bm = st.selectbox(
            "Business model",
            list(pe.SECTOR_MULTIPLES.keys()),
            index=list(pe.SECTOR_MULTIPLES.keys()).index(params.business_model)
            if params.business_model in pe.SECTOR_MULTIPLES else 0,
            key="adj_bm")
    with e3:
        new_geo = st.text_input("Geography", value=params.geography, key="adj_geo")
    with e4:
        new_ret = st.number_input(
            "Required return (x)",
            min_value=1.0, max_value=100.0,
            value=float(params.required_return_multiple),
            step=1.0, key="adj_ret")

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        new_r1 = st.number_input("Revenue Yr1 (EUR)",
            min_value=0.0, value=float(params.projected_revenue_yr1),
            step=10_000.0, key="adj_r1")
    with f2:
        new_r3 = st.number_input("Revenue Yr3 (EUR)",
            min_value=0.0, value=float(params.projected_revenue_yr3),
            step=50_000.0, key="adj_r3")
    with f3:
        new_r5 = st.number_input("Revenue Yr5 (EUR)",
            min_value=0.0, value=float(params.projected_revenue_yr5),
            step=100_000.0, key="adj_r5")
    with f4:
        new_ask = st.number_input("Funding ask (EUR)",
            min_value=0.0, value=float(params.funding_ask),
            step=25_000.0, key="adj_ask")

    g1, g2 = st.columns(2)
    with g1:
        new_margin = st.slider("Gross margin %", 0, 100,
            int(params.gross_margin_pct), key="adj_margin")
    with g2:
        new_exit = st.slider("Target exit year", 3, 10,
            int(params.exit_year), key="adj_exit")

    # Recalculate button
    if st.button("Recalculate with adjusted inputs", key="recalc_btn"):
        params.stage                   = new_stage
        params.business_model          = new_bm
        params.geography               = new_geo
        params.required_return_multiple= new_ret
        params.projected_revenue_yr1   = new_r1
        params.projected_revenue_yr3   = new_r3
        params.projected_revenue_yr5   = new_r5
        params.funding_ask             = new_ask
        params.gross_margin_pct        = float(new_margin)
        params.exit_year               = new_exit
        st.session_state["params"]     = params
        st.session_state["valuation"]  = pe.compute_valuation(params)
        result = st.session_state["valuation"]

    # ── Strengths & Risks ──────────────────────────────────────────────────────
    if meta.get("strengths") or meta.get("risks"):
        sr1, sr2 = st.columns(2)
        with sr1:
            if meta.get("strengths"):
                st.markdown("**Key strengths identified**")
                for s in meta["strengths"]:
                    if s:
                        st.markdown(
                            f'<div class="strength">&#10003; {s}</div>',
                            unsafe_allow_html=True)
        with sr2:
            if meta.get("risks"):
                st.markdown("**Key risks identified**")
                for r in meta["risks"]:
                    if r:
                        st.markdown(
                            f'<div class="risk">&#9651; {r}</div>',
                            unsafe_allow_html=True)

    # ── Scorecard ──────────────────────────────────────────────────────────────
    sc = result.scorecard_score
    sc_color = score_color(sc)
    st.markdown(
        '<div style="background:#FFFFFF;border:1px solid #CDD2DB;border-radius:8px;'
        'padding:16px 20px;margin:16px 0;">'
        '<div style="font-size:0.62rem;font-weight:700;letter-spacing:0.14em;'
        f'text-transform:uppercase;color:{CLR};margin-bottom:8px;">'
        'Scorecard Rating (Bill Payne Method)</div>'
        '<div style="display:flex;align-items:center;gap:16px;">'
        f'<div style="font-size:2.4rem;font-weight:800;color:{sc_color};">{sc}/100</div>'
        '<div>'
        f'<div style="font-size:0.95rem;font-weight:600;color:#0D1117;">'
        f'{result.scorecard_label}</div>'
        '<div style="background:#E5E7EB;border-radius:4px;height:8px;width:100%;margin:6px 0;">'
        f'<div style="background:{sc_color};height:8px;border-radius:4px;width:{sc}%;"></div>'
        '</div>'
        f'<div style="font-size:0.72rem;color:#7A8499;">'
        f'Team {params.team_score:.0f}/10 &nbsp;&middot;&nbsp;'
        f'Market {params.market_score:.0f}/10 &nbsp;&middot;&nbsp;'
        f'Product {params.product_score:.0f}/10 &nbsp;&middot;&nbsp;'
        f'Traction {params.traction_score:.0f}/10 &nbsp;&middot;&nbsp;'
        f'Competition {params.competition_score:.0f}/10</div>'
        '</div></div></div>',
        unsafe_allow_html=True)

    # ── Three-scenario valuation cards ─────────────────────────────────────────
    st.markdown(
        '<div class="sec">Valuation &mdash; Three Scenarios</div>',
        unsafe_allow_html=True)

    CARD_COLORS = {
        "Conservative": "#1A2B3C",
        "Base":          CLR,
        "Optimistic":    "#1A4A2E",
    }

    vc1, vc2, vc3 = st.columns(3)
    for col, scenario in zip([vc1, vc2, vc3],
                              [result.conservative, result.base, result.optimistic]):
        bg = CARD_COLORS[scenario.scenario]
        with col:
            st.markdown(f"""<div class="val-card" style="background:{bg};">
              <div class="val-label">{scenario.scenario}</div>
              <div class="val-num">{fmt(scenario.valuation_blended)}</div>
              <div class="val-sub">
                Blended pre-money valuation<br>
                DCF: {fmt(scenario.valuation_dcf)} &nbsp;&middot;&nbsp;
                VC: {fmt(scenario.valuation_vc)}<br>
                Multiple: {fmt(scenario.valuation_multiple)}
              </div>
            </div>""", unsafe_allow_html=True)

    st.markdown(
        '<div class="prov">Blended: DCF 35% / VC Method 45% / Revenue Multiple 20% '
        f'(stage: {params.stage}). '
        f'Discount rate: {int(pe.DISCOUNT_RATES.get(params.stage, 0.45)*100)}%. '
        'Survival-adjusted. Methodology in footer.</div>',
        unsafe_allow_html=True)

    # ── Projection table ───────────────────────────────────────────────────────
    st.markdown(
        '<div class="sec">Revenue & Valuation Projection &mdash; 3 / 5 / 10 Year</div>',
        unsafe_allow_html=True)

    import pandas as pd
    rows = []
    for s in [result.conservative, result.base, result.optimistic]:
        rows.append({
            "Scenario":    s.scenario,
            "Revenue Yr3": fmt(s.revenue_yr3),
            "Revenue Yr5": fmt(s.revenue_yr5),
            "Revenue Yr10":fmt(s.revenue_yr10),
            "EBITDA Yr5":  fmt(s.ebitda_yr5),
            "Valuation":   fmt(s.valuation_blended),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown(
        f'<div class="prov">Revenue projections use sector CAGR benchmark: '
        f'{int(pe.SECTOR_GROWTH_RATES.get(params.business_model, 0.15)*100)}% '
        f'({params.business_model}). Conservative applies 60% revenue multiplier + '
        f'0.7x growth discount. Base applies 80% multiplier. '
        f'Optimistic applies full plan + 1.3x growth. '
        f'EBITDA estimated at gross margin ({params.gross_margin_pct:.0f}%) x 50% '
        f'FCF conversion.</div>',
        unsafe_allow_html=True)

    # ── Comparable benchmarks ──────────────────────────────────────────────────
    st.markdown(
        '<div class="sec">Market Benchmarks &amp; Comparables</div>',
        unsafe_allow_html=True)

    sector = params.business_model
    mults  = pe.SECTOR_MULTIPLES.get(sector, pe.SECTOR_MULTIPLES["general"])
    st.markdown(f"""<div style="background:#FFFFFF;border:1px solid #CDD2DB;
      border-radius:8px;padding:16px 20px;">
      <div style="font-size:0.62rem;font-weight:700;letter-spacing:0.14em;
        text-transform:uppercase;color:{CLR};margin-bottom:10px;">
        Sector: {sector.replace('_',' ').title()}</div>
      <div style="display:flex;gap:24px;flex-wrap:wrap;">
        <div><div style="font-size:1.6rem;font-weight:800;color:#0D1117;">
          {mults['low']}x&ndash;{mults['high']}x</div>
          <div style="font-size:0.72rem;color:#7A8499;">Revenue multiple range</div>
        </div>
        <div><div style="font-size:1.6rem;font-weight:800;color:{CLR};">
          {mults['mid']}x</div>
          <div style="font-size:0.72rem;color:#7A8499;">Median multiple</div>
        </div>
        <div><div style="font-size:1.6rem;font-weight:800;color:#0D1117;">
          &euro;3.3M</div>
          <div style="font-size:0.72rem;color:#7A8499;">Median pre-seed Europe (Equidam H1 2026)</div>
        </div>
        <div><div style="font-size:1.6rem;font-weight:800;color:#0D1117;">
          {int(pe.SECTOR_GROWTH_RATES.get(sector,0.15)*100)}%</div>
          <div style="font-size:0.72rem;color:#7A8499;">Sector CAGR benchmark</div>
        </div>
      </div>
      <div class="prov" style="margin-top:10px;">{result.comparable_notes}</div>
    </div>""", unsafe_allow_html=True)

    # ── Live data enrichment display ─────────────────────────────────────────
    enrich_key  = f"enrich_{params.business_model}_{params.geography}"
    enrichment  = st.session_state.get(enrich_key, {})
    if enrichment and enrichment.get("data_sources"):
        st.markdown('<div class="sec">Live Market Data &mdash; Eurostat + OECD</div>',
                    unsafe_allow_html=True)
        note       = pld.format_enrichment_note(enrichment)
        macro_adj  = enrichment.get("macro_adjustment", 1.0)
        adj_color  = "#2E7D32" if macro_adj >= 1.0 else "#C62828"
        adj_label  = (f"+{int((macro_adj-1)*100)}% growth uplift"
                      if macro_adj > 1.0
                      else f"{int((macro_adj-1)*100)}% growth headwind")
        st.markdown(
            '<div style="background:#FFFFFF;border:1px solid #CDD2DB;'
            'border-radius:8px;padding:16px 20px;margin-bottom:8px;">'
            '<div style="font-size:0.62rem;font-weight:700;letter-spacing:0.14em;'
            f'text-transform:uppercase;color:{CLR};margin-bottom:8px;">'
            'Live data enrichment active</div>'
            + note +
            f'<div style="margin-top:8px;font-size:0.78rem;font-weight:600;'
            f'color:{adj_color};">Macro adjustment: {adj_label} '
            f'(OECD CLI {enrichment.get("cli",100.0)}, '
            f'{enrichment.get("cli_trend","neutral")})</div>'
            '<div class="prov">Sources: '
            + ' / '.join(enrichment.get("data_sources", ["sector benchmarks"]))
            + '</div></div>',
            unsafe_allow_html=True)

    # ── Download exports ───────────────────────────────────────────────────────
    st.markdown('<div class="sec">Download Financial Models</div>',
                unsafe_allow_html=True)
    # Build Excel files once and cache — avoids rebuilding on every render
    _dcf_key = f"dcf_{params.company_name}_{params.stage}_{params.projected_revenue_yr5}"
    _mc_key  = f"mc_{params.company_name}_{params.stage}_{params.projected_revenue_yr5}"
    if _dcf_key not in st.session_state:
        _enr2 = st.session_state.get(f"enrich_{params.business_model}_{params.geography}", {})
        st.session_state[_dcf_key] = pex.build_dcf_model(params, _enr2).getvalue()
    if _mc_key not in st.session_state:
        st.session_state[_mc_key] = pex.build_monte_carlo(params, n_simulations=1000).getvalue()

    dl1, dl2, dl3 = st.columns(3)
    with dl1:
        st.download_button(
            label="Download DCF Model (.xlsx)",
            data=st.session_state[_dcf_key],
            file_name=f"ValuePitch_DCF_{params.company_name.replace(' ','_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="10-year DCF with three scenarios, sensitivity table. Yellow cells are editable.",
        )
    with dl2:
        st.download_button(
            label="Download Monte Carlo (.xlsx)",
            data=st.session_state[_mc_key],
            file_name=f"ValuePitch_MonteCarlo_{params.company_name.replace(' ','_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="1,000 simulations varying growth, margin, exit multiple + survival probability.",
        )
    with dl3:
        st.markdown(
            '<div style="background:#F8F9FA;border:1px dashed #CDD2DB;'
            'border-radius:8px;padding:14px 16px;text-align:center;'
            'font-size:0.8rem;color:#7A8499;">'
            'Executive Summary PDF<br>'
            '<span style="font-size:0.7rem;">Coming soon</span></div>',
            unsafe_allow_html=True)

    # ── PESTEL ─────────────────────────────────────────────────────────────────
    ph1, ph2 = st.columns([8,1])
    with ph1:
        st.markdown(
            '<div class="sec">PESTEL Analysis &mdash; AI-Generated, Live Context</div>',
            unsafe_allow_html=True)
    with ph2:
        if st.button("↻ Retry", key="pestel_retry"):
            for k in list(st.session_state.keys()):
                if k.startswith("pestel_"):
                    del st.session_state[k]

    with st.spinner("Generating PESTEL..."):
        pestel = generate_pestel(params.sector, params.geography, params.business_model)

    PESTEL_MAP = [
        ("P", "Political",     "political"),
        ("E", "Economic",      "economic"),
        ("S", "Social",        "social"),
        ("T", "Technological", "technological"),
        ("E", "Environmental", "environmental"),
        ("L", "Legal",         "legal"),
    ]
    p1, p2 = st.columns(2)
    for i, (letter, title, key) in enumerate(PESTEL_MAP):
        col = p1 if i % 2 == 0 else p2
        with col:
            st.markdown(f"""<div class="pestel-card">
              <span class="pestel-letter">{letter}</span>
              <span class="pestel-title" style="margin-left:8px;">{title}</span>
              <div class="pestel-body">{pestel.get(key,'')}</div>
            </div>""", unsafe_allow_html=True)

    # ── Porter's Five Forces ───────────────────────────────────────────────────
    st.markdown(
        "<div class=\"sec\">Porter's Five Forces</div>",
        unsafe_allow_html=True)

    with st.spinner("Generating Porter's Five Forces..."):
        _pitch_ctx = st.session_state.get('meta', {}).get('summary', '')
        porter = generate_porter(params.sector, params.business_model, _pitch_ctx)

    PORTER_MAP = [
        ("Competitive Rivalry",     "rivalry"),
        ("Threat of New Entrants",  "new_entrants"),
        ("Supplier Power",          "suppliers"),
        ("Buyer Power",             "buyers"),
        ("Threat of Substitutes",   "substitutes"),
    ]
    pot1, pot2, pot3 = st.columns(3)
    cols = [pot1, pot2, pot3, pot1, pot2]
    for col, (title, key) in zip(cols, PORTER_MAP):
        force  = porter.get(key, {"level":"Medium","note":"—"})
        level  = force.get("level","Medium")
        lcolor = level_color(level)
        with col:
            st.markdown(f"""<div style="background:#FFFFFF;border:1px solid #CDD2DB;
              border-radius:8px;padding:12px 16px;margin-bottom:8px;">
              <div style="font-size:0.78rem;font-weight:700;color:#0D1117;">{title}</div>
              <div style="font-size:1.1rem;font-weight:800;color:{lcolor};
                margin:4px 0;">{level}</div>
              <div style="font-size:0.75rem;color:#52596B;line-height:1.5;">
                {force.get('note','')}</div>
            </div>""", unsafe_allow_html=True)

    # ── Footer ─────────────────────────────────────────────────────────────────
    st.markdown(f"""<div style="border-top:2px solid #CDD2DB;margin-top:40px;
      padding:14px 0 6px 0;">
      <div style="display:flex;justify-content:space-between;
        font-size:0.65rem;color:#9CA3AF;margin-bottom:6px;">
        <span>Valuation = weighted blend of DCF (survival-adjusted) / VC Method /
          Revenue Multiple &nbsp;&middot;&nbsp;
          Scorecard: Bill Payne method &nbsp;&middot;&nbsp;
          PESTEL + Porter: AI-generated from sector + geography</span>
        <span style="text-align:right;white-space:nowrap;margin-left:24px;">
          <strong style="color:#52596B;">&#9670; ValuePitch</strong>
          &nbsp;&middot;&nbsp; &copy; 2026 J. Schmidt
          &nbsp;&middot;&nbsp; Proprietary &amp; Confidential
        </span>
      </div>
      <div style="font-size:0.60rem;color:#B0B8C4;line-height:1.5;">
        This platform and all underlying methodology, scoring formulae, financial models,
        and AI-assisted analysis are the exclusive intellectual property of J. Schmidt.
        Valuations are indicative estimates based on sector benchmarks and AI-extracted
        parameters. Not financial advice. Verify with a qualified advisor before
        investment decisions.
      </div>
    </div>""", unsafe_allow_html=True)

else:
    # ── Empty state ────────────────────────────────────────────────────────────
    st.markdown(f"""<div style="background:#FFFFFF;border:1px solid #CDD2DB;
      border-radius:12px;padding:48px 32px;text-align:center;margin-top:24px;">
      <div style="font-size:2.5rem;margin-bottom:16px;">&#9670;</div>
      <div style="font-size:1.1rem;font-weight:700;color:#0D1117;margin-bottom:8px;">
        Paste a pitch above to get started</div>
      <div style="font-size:0.85rem;color:#52596B;max-width:500px;
        margin:0 auto;line-height:1.6;">
        ValuePitch reads any pitch or idea description and returns a
        three-scenario valuation across 3, 5, and 10 year horizons
        &mdash; backed by live market benchmarks, PESTEL, and
        Porter's Five Forces. No forms to fill. Just paste and analyse.
      </div>
      <div style="margin-top:24px;font-size:0.72rem;color:#9CA3AF;">
        AI analysis engine &nbsp;&middot;&nbsp;
        Financial engine: DCF + VC Method + Revenue Multiple &nbsp;&middot;&nbsp;
        Benchmarks: Equidam H1 2026 + sector data
      </div>
    </div>""", unsafe_allow_html=True)
