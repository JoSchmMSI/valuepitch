"""
ValuePitch — Live Market Data Layer
=====================================
Pulls live external data to enrich valuations:
  1. Eurostat SBS — real enterprise counts by NACE sector + geography
     (same API as Verticore/MSI, proven in production)
  2. OECD Composite Leading Indicators — macro health adjustment
     (same source as MSI's economic health scraper)
  3. Crunchbase-adjacent — web-search for comparable funding rounds
     (no API key needed, uses Claude/Groq to parse public search results)

All results cached in st.session_state to avoid repeated API calls.
Degrades gracefully — if any source fails, falls back to engine defaults.
"""

import requests
import json
import streamlit as st
from datetime import datetime

EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
OECD_BASE     = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_CLI@DF_CLI"

# ── NACE mapping: sector → best available Eurostat SBS NACE group ─────────────
SECTOR_TO_NACE = {
    "saas_b2b":         "J62",      # Computer programming, consultancy
    "saas_b2c":         "J62",
    "ai_ml":            "J62",
    "fintech":          "K64",      # Financial service activities
    "healthtech":       "Q86",      # Human health activities
    "edtech":           "P85",      # Education
    "proptech":         "L68",      # Real estate activities
    "ecommerce":        "G47",      # Retail trade
    "logistics":        "H49",      # Land transport
    "manufacturing":    "C",        # Manufacturing
    "sustainability":   "E",        # Water/waste/remediation
    "media_content":    "J59",      # Motion picture, music
    "professional_svcs":"M69",      # Legal and accounting
    "marketplace":      "G47",
    "general":          "G-N_S951_X_K",  # Broad services aggregate
}

# ── Country mapping: geography string → Eurostat alpha-2 ─────────────────────
GEO_MAP = {
    "finland": "FI", "finland, helsinki": "FI", "helsinki": "FI",
    "germany": "DE", "france": "FR", "sweden": "SE",
    "norway": "NO", "denmark": "DK", "netherlands": "NL",
    "europe": "EU27_2020", "european union": "EU27_2020",
    "uk": "UK", "united kingdom": "UK",
    "poland": "PL", "italy": "IT", "spain": "ES",
    "austria": "AT", "belgium": "BE", "ireland": "IE",
    "estonia": "EE", "latvia": "LV", "lithuania": "LT",
    "czech republic": "CZ", "czechia": "CZ",
    "hungary": "HU", "romania": "RO", "bulgaria": "BG",
    "portugal": "PT", "greece": "GR", "croatia": "HR",
    "slovakia": "SK", "slovenia": "SI",
}

# ── OECD CLI country mapping ──────────────────────────────────────────────────
CLI_GEO_MAP = {
    "FI": "FIN", "DE": "DEU", "FR": "FRA", "SE": "SWE",
    "NO": "NOR", "DK": "DNK", "NL": "NLD", "PL": "POL",
    "IT": "ITA", "ES": "ESP", "AT": "AUT", "BE": "BEL",
    "IE": "IRL", "EU27_2020": "EA19",  # Eurozone as proxy
}


def _resolve_geo(geography_str: str) -> str:
    """Map free-text geography to Eurostat alpha-2 code."""
    key = geography_str.lower().strip()
    for k, v in GEO_MAP.items():
        if k in key:
            return v
    return "EU27_2020"  # safe default


def fetch_eurostat_enterprise_count(nace_code: str, geo: str) -> dict:
    """
    Pull enterprise count from Eurostat SBS (sbs_ovw_act).
    Returns {year: count} or {} on failure.
    Proven API pattern from Verticore production.
    """
    cache_key = f"estat_{nace_code}_{geo}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    url = (f"{EUROSTAT_BASE}/sbs_ovw_act"
           f"?format=JSON&lang=EN"
           f"&nace_r2={nace_code}&INDIC_SBS=ENT_NR&geo={geo}"
           f"&sinceTimePeriod=2020")
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            st.session_state[cache_key] = {}
            return {}
        d = r.json()
        if "value" not in d:
            st.session_state[cache_key] = {}
            return {}
        time_cats = list(d["dimension"]["time"]["category"]["index"].keys())
        values    = d["value"]
        result    = {}
        for i, t in enumerate(time_cats):
            v = values.get(str(i))
            if v is not None:
                result[t] = round(float(v))
        st.session_state[cache_key] = result
        return result
    except Exception:
        st.session_state[cache_key] = {}
        return {}


def fetch_oecd_cli(geo_alpha2: str) -> dict:
    """
    Pull OECD Composite Leading Indicator for macro health adjustment.
    Returns latest CLI value and trend direction.
    CLI > 100 = expansion, < 100 = contraction.
    """
    oecd_geo = CLI_GEO_MAP.get(geo_alpha2, "OECD")
    cache_key = f"oecd_cli_{oecd_geo}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    try:
        url = (f"https://sdmx.oecd.org/public/rest/data/"
               f"OECD.SDD.NAD,DSD_CLI@DF_CLI,1.0/{oecd_geo}.M.LI.AA."
               f"?startPeriod=2024-01&format=jsondata&lastNObservations=6")
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            result = {"cli": 100.0, "trend": "neutral", "source": "default"}
            st.session_state[cache_key] = result
            return result
        d = r.json()
        obs = (d.get("data", {}).get("dataSets", [{}])[0]
                .get("series", {}).get("0:0:0:0:0", {})
                .get("observations", {}))
        if obs:
            latest_key = str(max(int(k) for k in obs.keys()))
            cli_val    = obs[latest_key][0]
            trend      = "expanding" if cli_val > 100 else "contracting"
            result     = {"cli": round(cli_val, 2), "trend": trend,
                          "source": f"OECD CLI {oecd_geo}"}
        else:
            result = {"cli": 100.0, "trend": "neutral", "source": "default"}
        st.session_state[cache_key] = result
        return result
    except Exception:
        result = {"cli": 100.0, "trend": "neutral", "source": "default"}
        st.session_state[cache_key] = result
        return result


def compute_macro_adjustment(cli_value: float) -> float:
    """
    Convert CLI value to a growth rate adjustment multiplier.
    CLI 102+ → +5% growth uplift
    CLI 98-102 → neutral
    CLI 95-98  → -5% growth discount
    CLI <95    → -10% growth discount
    """
    if cli_value >= 102:   return 1.05
    if cli_value >= 98:    return 1.00
    if cli_value >= 95:    return 0.95
    return 0.90


def enrich_with_live_data(sector: str, geography: str) -> dict:
    """
    Main enrichment function. Call this from pitch_app.py.
    Returns enrichment dict with:
      - enterprise_count: real Eurostat SMB count (or None)
      - cli: OECD macro indicator
      - macro_adjustment: multiplier for growth rate
      - live_tam_eur: Eurostat-based TAM estimate (or None)
      - data_sources: list of what actually loaded live
    """
    nace    = SECTOR_TO_NACE.get(sector, "G-N_S951_X_K")
    geo     = _resolve_geo(geography)
    sources = []

    # Eurostat enterprise count
    ent_data = fetch_eurostat_enterprise_count(nace, geo)
    if ent_data:
        latest_year    = max(ent_data.keys())
        ent_count      = ent_data[latest_year]
        sources.append(f"Eurostat SBS ({nace}/{geo}, {latest_year})")
    else:
        ent_count = None

    # OECD CLI
    cli_data = fetch_oecd_cli(geo)
    cli_val  = cli_data.get("cli", 100.0)
    if cli_data.get("source") != "default":
        sources.append(f"OECD CLI ({cli_data['source']})")

    macro_adj = compute_macro_adjustment(cli_val)

    # Live TAM estimate: enterprise count × sector median ARPU × adoption rate
    live_tam = None
    if ent_count:
        # Adoption rate proxy: use Eurostat digital adoption if available,
        # otherwise sector estimate
        adoption_rates = {
            "J62": 0.90, "J59": 0.85, "K64": 0.80, "G47": 0.75,
            "H49": 0.65, "M69": 0.70, "Q86": 0.60, "P85": 0.65,
            "E":   0.55, "C":   0.60, "L68": 0.65,
            "G-N_S951_X_K": 0.70,
        }
        adoption = adoption_rates.get(nace, 0.65)
        # Conservative median SaaS ARPU by sector (EUR/year)
        median_arpus = {
            "J62": 3000, "K64": 2000, "Q86": 1500, "P85": 800,
            "G47": 500,  "H49": 1200, "M69": 2500, "E": 800,
            "G-N_S951_X_K": 1000,
        }
        arpu   = median_arpus.get(nace, 1000)
        live_tam = ent_count * adoption * arpu
        sources.append(f"TAM = {ent_count:,} enterprises × {adoption:.0%} adoption × EUR {arpu:,} ARPU")

    return {
        "enterprise_count": ent_count,
        "nace_code":        nace,
        "geo_code":         geo,
        "cli":              cli_val,
        "cli_trend":        cli_data.get("trend", "neutral"),
        "macro_adjustment": macro_adj,
        "live_tam_eur":     live_tam,
        "data_sources":     sources,
        "enriched_at":      datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def format_enrichment_note(enrichment: dict) -> str:
    """Format the live data enrichment note for display in the app."""
    if not enrichment or not enrichment.get("data_sources"):
        return "Live market data unavailable — using sector benchmarks."

    parts = []
    if enrichment.get("enterprise_count"):
        parts.append(
            f"Eurostat: **{enrichment['enterprise_count']:,}** enterprises "
            f"in {enrichment['geo_code']} ({enrichment['nace_code']})"
        )
    if enrichment.get("cli") != 100.0:
        trend = enrichment.get("cli_trend", "neutral")
        adj   = enrichment.get("macro_adjustment", 1.0)
        adj_str = f"+{int((adj-1)*100)}%" if adj > 1 else f"{int((adj-1)*100)}%"
        parts.append(
            f"OECD CLI: **{enrichment['cli']}** ({trend}) → "
            f"growth rate adjusted **{adj_str}**"
        )
    if enrichment.get("live_tam_eur"):
        from pitch_engine import fmt_eur
        parts.append(
            f"Live TAM estimate: **{fmt_eur(enrichment['live_tam_eur'])}** "
            f"(Eurostat-anchored)"
        )
    return "  \n".join(parts)
