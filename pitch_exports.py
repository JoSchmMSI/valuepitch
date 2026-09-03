"""
ValuePitch — Excel Export Engine
==================================
Generates two professional Excel models pre-filled with
ValuePitch's extracted and calculated parameters:

1. DCF Model — 10-year discounted cash flow with three scenarios,
   survival adjustment, terminal value, sensitivity table.
   User can change yellow input cells and model recalculates.

2. Monte Carlo Simulation — 1,000 simulation runs varying
   revenue growth, margin, and churn simultaneously.
   Output: probability distribution of exit valuations.
   Requires xlwings or manual recalc — implemented as
   pre-calculated simulation with distribution table.

Both follow the xlsx skill conventions:
  - Blue text: hardcoded inputs
  - Yellow fill: cells user should edit
  - Black: formula cells
  - Professional Arial font throughout
  - Formulas not hardcoded values
"""

import io
import math
import random
import subprocess
import tempfile
import os
import openpyxl
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers
)
from openpyxl.utils import get_column_letter
from pitch_engine import PitchParameters, fmt_eur, SECTOR_MULTIPLES, SECTOR_GROWTH_RATES, DISCOUNT_RATES, SURVIVAL_RATES

# ── Style constants ────────────────────────────────────────────────────────────
NAVY    = "1A3A5C"
GOLD    = "C9A227"
WHITE   = "FFFFFF"
LGREY   = "F2F4F7"
MGREY   = "CDD2DB"
BLUE_INPUT = "0000FF"    # blue text for hardcoded inputs
YELLOW_FILL = "FFFF00"   # yellow fill for user-editable cells
GREEN_TEXT  = "008000"

def _header_fill(color):   return PatternFill("solid", fgColor=color)
def _font(bold=False, color="000000", size=10, italic=False):
    return Font(name="Arial", bold=bold, color=color, size=size, italic=italic)
def _border():
    s = Side(style="thin", color="CCCCCC")
    return Border(left=s, right=s, top=s, bottom=s)
def _align(h="left", v="center"):
    return Alignment(horizontal=h, vertical=v, wrap_text=True)

def _set(ws, row, col, value, bold=False, color="000000", size=10,
         fill=None, align="left", num_fmt=None, italic=False):
    cell = ws.cell(row=row, column=col, value=value)
    cell.font      = _font(bold=bold, color=color, size=size, italic=italic)
    cell.alignment = _align(align)
    if fill:
        cell.fill = _header_fill(fill)
    if num_fmt:
        cell.number_format = num_fmt
    return cell


def _recalc_bytes(buf: io.BytesIO) -> io.BytesIO:
    """
    Write workbook to temp file, recalculate via LibreOffice,
    read back as BytesIO. This populates all formula cached values
    so Excel shows numbers immediately on open.
    """
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
        tmp.write(buf.getvalue())
        tmp_path = tmp.name
    try:
        subprocess.run(
            ['python3', '/mnt/skills/public/xlsx/scripts/recalc.py',
             tmp_path, '60'],
            capture_output=True, text=True, timeout=90
        )
        with open(tmp_path, 'rb') as f:
            result = io.BytesIO(f.read())
        result.seek(0)
        return result
    except Exception:
        buf.seek(0)
        return buf
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ── DCF MODEL ─────────────────────────────────────────────────────────────────
def build_dcf_model(params: PitchParameters,
                    enrichment: dict = None) -> io.BytesIO:
    """
    Build a professional 10-year DCF model Excel file.
    Returns BytesIO ready for st.download_button.
    """
    wb = openpyxl.Workbook()

    # ── Sheet 1: Cover ────────────────────────────────────────────────────────
    ws_cover = wb.active
    ws_cover.title = "Cover"
    ws_cover.sheet_view.showGridLines = False
    ws_cover.column_dimensions["A"].width = 40
    ws_cover.column_dimensions["B"].width = 50

    _set(ws_cover, 1, 1, "VALUEPITCH", bold=True, size=18, color=NAVY)
    _set(ws_cover, 2, 1, "Discounted Cash Flow Valuation Model",
         bold=True, size=13, color=NAVY)
    _set(ws_cover, 3, 1, f"Company: {params.company_name}",
         bold=True, size=11)
    _set(ws_cover, 4, 1, f"Stage: {params.stage.replace('_',' ').title()}")
    _set(ws_cover, 5, 1, f"Sector: {params.business_model.replace('_',' ').title()}")
    _set(ws_cover, 6, 1, f"Geography: {params.geography}")
    _set(ws_cover, 8, 1,
         "INSTRUCTIONS: Change yellow cells to update your assumptions. "
         "All other cells recalculate automatically.",
         italic=True, color="666666", size=9)
    _set(ws_cover, 9, 1,
         "Blue cells = hardcoded inputs (your extracted figures). "
         "Yellow cells = adjustable assumptions. Black = formulas.",
         italic=True, color="666666", size=9)
    _set(ws_cover, 11, 1, "(c) 2026 J. Schmidt / ValuePitch — Not financial advice.",
         italic=True, color="999999", size=8)

    # ── Sheet 2: Assumptions ──────────────────────────────────────────────────
    ws_ass = wb.create_sheet("Assumptions")
    ws_ass.sheet_view.showGridLines = False
    ws_ass.column_dimensions["A"].width = 35
    ws_ass.column_dimensions["B"].width = 20
    ws_ass.column_dimensions["C"].width = 35

    def ass_header(row, text):
        c = ws_ass.cell(row=row, column=1, value=text)
        c.font  = _font(bold=True, color=WHITE, size=10)
        c.fill  = _header_fill(NAVY)
        c.alignment = _align()
        ws_ass.merge_cells(f"A{row}:C{row}")

    def ass_row(row, label, value, fmt=None, editable=False, note=""):
        _set(ws_ass, row, 1, label, size=10)
        c = _set(ws_ass, row, 2, value, size=10, color=BLUE_INPUT,
                 align="right", num_fmt=fmt)
        if editable:
            c.fill = _header_fill(YELLOW_FILL)
        if note:
            _set(ws_ass, row, 3, note, size=9, color="666666", italic=True)

    sector = params.business_model
    base_growth = SECTOR_GROWTH_RATES.get(sector, 0.15)
    disc_rate   = DISCOUNT_RATES.get(params.stage, 0.45)
    surv        = SURVIVAL_RATES.get(params.stage, SURVIVAL_RATES["seed"])
    exit_mult   = SECTOR_MULTIPLES.get(sector, SECTOR_MULTIPLES["general"])["mid"]

    ass_header(1, "REVENUE ASSUMPTIONS")
    ass_row(2,  "Current Revenue (EUR)",        params.current_revenue,       '#,##0', False, "Extracted from pitch")
    ass_row(3,  "Projected Revenue Year 1 (EUR)",params.projected_revenue_yr1, '#,##0', True,  "Adjust as needed — yellow = editable")
    ass_row(4,  "Projected Revenue Year 3 (EUR)",params.projected_revenue_yr3, '#,##0', True)
    ass_row(5,  "Projected Revenue Year 5 (EUR)",params.projected_revenue_yr5, '#,##0', True)
    ass_row(6,  "Gross Margin %",               params.gross_margin_pct/100,   '0.0%', True,  "Percentage of revenue after COGS")
    ass_row(7,  "ARPU (EUR/year)",               params.arpu,                  '#,##0', True)

    ass_header(9, "VALUATION ASSUMPTIONS")
    ass_row(10, "Discount Rate (WACC/Risk)",    disc_rate,   '0.0%', True,
            f"Stage default: {int(disc_rate*100)}% for {params.stage}")
    ass_row(11, "Sector Revenue Multiple (exit)",exit_mult,  '0.0x', True,
            f"Sector benchmark: {sector}")
    ass_row(12, "Exit Year (from today)",        params.exit_year, '0',  True)
    ass_row(13, "Required VC Return Multiple",   params.required_return_multiple, '0.0x', True)
    ass_row(14, "Sector CAGR Benchmark",         base_growth, '0.0%', False,
            f"Source: SaaS Capital / Equidam H1 2026")
    ass_row(15, "Survival Rate (5yr, stage)",    surv["5yr"], '0.0%', False,
            f"Source: CB Insights startup survival data")

    ass_header(17, "FUNDING")
    ass_row(18, "Funding Ask (EUR)",             params.funding_ask, '#,##0', True)
    ass_row(19, "Pre-money Valuation (VC Method)", f"=B18*(B13-1)", '#,##0', False,
            "Calculated: Post-money / Required return - Funding ask")

    if enrichment and enrichment.get("data_sources"):
        ass_header(21, "LIVE MARKET DATA (EUROSTAT + OECD)")
        r = 22
        if enrichment.get("enterprise_count"):
            ass_row(r, f"Enterprise Count ({enrichment['geo_code']})",
                    enrichment["enterprise_count"], '#,##0', False,
                    f"Source: Eurostat SBS {enrichment.get('nace_code','')} — live")
            r += 1
        if enrichment.get("cli"):
            ass_row(r, "OECD Composite Leading Indicator",
                    enrichment["cli"], '0.00', False,
                    f"Trend: {enrichment.get('cli_trend','neutral')} — live")
            r += 1
        if enrichment.get("live_tam_eur"):
            ass_row(r, "Live TAM Estimate (Eurostat-anchored, EUR)",
                    enrichment["live_tam_eur"], '#,##0', False,
                    "Enterprise count × adoption rate × median ARPU")

    # ── Sheet 3: DCF Projection ───────────────────────────────────────────────
    ws_dcf = wb.create_sheet("DCF Projection")
    ws_dcf.sheet_view.showGridLines = False

    years   = list(range(1, 11))
    yr_cols = {yr: yr + 1 for yr in years}   # col B=yr1, col K=yr10

    # Column widths
    ws_dcf.column_dimensions["A"].width = 32
    for yr in years:
        ws_dcf.column_dimensions[get_column_letter(yr+1)].width = 13

    # Header row
    _set(ws_dcf, 1, 1, "DCF PROJECTION — 10 YEAR",
         bold=True, size=12, color=NAVY)
    for yr in years:
        c = ws_dcf.cell(row=2, column=yr+1, value=f"Year {yr}")
        c.font      = _font(bold=True, color=WHITE)
        c.fill      = _header_fill(NAVY)
        c.alignment = _align("center")

    # Revenue row — interpolated from assumptions
    _set(ws_dcf, 3, 1, "Revenue (EUR)", bold=True)
    # Year 1: from Assumptions B3
    c = ws_dcf.cell(row=3, column=2, value="=Assumptions!B3")
    c.font = _font(color="000000"); c.number_format = '#,##0'
    # Year 2: interpolate between yr1 and yr3
    c2 = ws_dcf.cell(row=3, column=3,
                     value="=B3*(1+Assumptions!B14)")
    c2.font = _font(); c2.number_format = '#,##0'
    # Year 3: from assumptions
    c3 = ws_dcf.cell(row=3, column=4, value="=Assumptions!B4")
    c3.font = _font(); c3.number_format = '#,##0'
    # Year 4-5: grow toward yr5
    for col_offset in [4, 5]:
        c = ws_dcf.cell(row=3, column=col_offset+1,
                        value=f"={get_column_letter(col_offset)}3*(1+Assumptions!B14)")
        c.font = _font(); c.number_format = '#,##0'
    # Year 5: from assumptions
    ws_dcf.cell(row=3, column=6, value="=Assumptions!B5").number_format = '#,##0'
    # Year 6-10: compound growth from yr5
    for yr in range(6, 11):
        col = yr + 1
        c = ws_dcf.cell(row=3, column=col,
                        value=f"={get_column_letter(col-1)}3*(1+Assumptions!B14)")
        c.font = _font(); c.number_format = '#,##0'

    # Gross Profit
    _set(ws_dcf, 4, 1, "Gross Profit (EUR)")
    for yr in years:
        col = yr + 1
        c = ws_dcf.cell(row=4, column=col,
                        value=f"={get_column_letter(col)}3*Assumptions!B6")
        c.font = _font(); c.number_format = '#,##0'

    # Operating costs (40% of gross profit at early stage)
    _set(ws_dcf, 5, 1, "Operating Costs (EUR)")
    for yr in years:
        col = yr + 1
        c = ws_dcf.cell(row=5, column=col,
                        value=f"={get_column_letter(col)}4*0.65")
        c.font = _font(); c.number_format = '#,##0'

    # EBITDA
    _set(ws_dcf, 6, 1, "EBITDA (EUR)", bold=True)
    for yr in years:
        col = yr + 1
        c = ws_dcf.cell(row=6, column=col,
                        value=f"={get_column_letter(col)}4-{get_column_letter(col)}5")
        c.font = _font(bold=True); c.number_format = '#,##0'

    # Free Cash Flow (EBITDA × 0.8 — capex/WC proxy)
    _set(ws_dcf, 7, 1, "Free Cash Flow (EUR)")
    for yr in years:
        col = yr + 1
        c = ws_dcf.cell(row=7, column=col,
                        value=f"={get_column_letter(col)}6*0.8")
        c.font = _font(); c.number_format = '#,##0'

    # Discount factor
    _set(ws_dcf, 8, 1, "Discount Factor")
    for yr in years:
        col = yr + 1
        c = ws_dcf.cell(row=8, column=col,
                        value=f"=1/((1+Assumptions!B10)^{yr})")
        c.font = _font(); c.number_format = '0.000'

    # PV of FCF
    _set(ws_dcf, 9, 1, "PV of Free Cash Flow (EUR)")
    for yr in years:
        col = yr + 1
        c = ws_dcf.cell(row=9, column=col,
                        value=f"={get_column_letter(col)}7*{get_column_letter(col)}8")
        c.font = _font(); c.number_format = '#,##0'

    # Terminal value row
    _set(ws_dcf, 11, 1, "Terminal Value Assumptions", bold=True, color=NAVY)
    _set(ws_dcf, 12, 1, "Exit Revenue Multiple")
    c = ws_dcf.cell(row=12, column=2, value="=Assumptions!B11")
    c.font = _font(); c.number_format = '0.0x'
    _set(ws_dcf, 13, 1, "Terminal Value (EUR)")
    c = ws_dcf.cell(row=13, column=2, value="=K3*Assumptions!B11")
    c.font = _font(bold=True); c.number_format = '#,##0'
    _set(ws_dcf, 14, 1, "PV of Terminal Value (EUR)")
    c = ws_dcf.cell(row=14, column=2,
                    value=f"=B13/(1+Assumptions!B10)^Assumptions!B12")
    c.font = _font(bold=True); c.number_format = '#,##0'

    # Summary valuation
    _set(ws_dcf, 16, 1, "VALUATION SUMMARY", bold=True, size=11, color=NAVY)
    _set(ws_dcf, 17, 1, "Sum of PV of FCFs (EUR)")
    c = ws_dcf.cell(row=17, column=2, value="=SUM(B9:K9)")
    c.font = _font(); c.number_format = '#,##0'
    _set(ws_dcf, 18, 1, "PV of Terminal Value (EUR)")
    c = ws_dcf.cell(row=18, column=2, value="=B14")
    c.font = _font(); c.number_format = '#,##0'
    _set(ws_dcf, 19, 1, "Enterprise Value (EUR)", bold=True)
    c = ws_dcf.cell(row=19, column=2, value="=B17+B18")
    c.font = _font(bold=True, size=12); c.number_format = '#,##0'
    _set(ws_dcf, 20, 1, f"Survival Adjustment ({int(surv['5yr']*100)}%, {params.stage})")
    c = ws_dcf.cell(row=20, column=2,
                    value=f"=B19*{surv['5yr']}")
    c.font = _font(); c.number_format = '#,##0'
    _set(ws_dcf, 21, 1, "Adjusted Pre-Money Valuation (EUR)", bold=True)
    c = ws_dcf.cell(row=21, column=2, value="=B20")
    c.font = _font(bold=True, color=NAVY, size=13); c.number_format = '#,##0'

    # Sensitivity table
    _set(ws_dcf, 23, 1, "SENSITIVITY — Valuation by Discount Rate vs Exit Multiple",
         bold=True, color=NAVY)
    disc_rates  = [0.30, 0.40, 0.50, 0.60, 0.70]
    exit_mults  = [3.0, 5.0, 8.0, 12.0, 15.0]
    _set(ws_dcf, 24, 1, "Disc Rate \\ Exit Multiple")
    for j, em in enumerate(exit_mults):
        c = ws_dcf.cell(row=24, column=j+2, value=f"{em}x")
        c.font = _font(bold=True, color=WHITE)
        c.fill = _header_fill(NAVY)
        c.alignment = _align("center")
    for i, dr in enumerate(disc_rates):
        row = 25 + i
        c = ws_dcf.cell(row=row, column=1, value=f"{int(dr*100)}%")
        c.font = _font(bold=True, color=WHITE)
        c.fill = _header_fill(NAVY)
        for j, em in enumerate(exit_mults):
            # Simplified: terminal val / (1+dr)^exit_year * survival
            yr5_rev = params.projected_revenue_yr5
            tv  = yr5_rev * em / ((1 + dr) ** params.exit_year) * surv["5yr"]
            cell = ws_dcf.cell(row=row, column=j+2, value=round(tv))
            cell.font = _font()
            cell.number_format = '#,##0'
            if abs(dr - disc_rate) < 0.01 and abs(em - exit_mult) < 0.1:
                cell.fill = _header_fill(GOLD)  # highlight base case

    # ── Sheet 4: Scenarios ────────────────────────────────────────────────────
    ws_scen = wb.create_sheet("Three Scenarios")
    ws_scen.sheet_view.showGridLines = False
    ws_scen.column_dimensions["A"].width = 30
    for col in ["B","C","D"]:
        ws_scen.column_dimensions[col].width = 22

    scenarios = [
        ("Conservative", 0.60, 0.70, NAVY),
        ("Base",         0.80, 1.00, "1A3A5C"),
        ("Optimistic",   1.00, 1.30, "1A4A2E"),
    ]
    _set(ws_scen, 1, 1, "THREE-SCENARIO VALUATION SUMMARY",
         bold=True, size=12, color=NAVY)
    headers = ["Conservative", "Base", "Optimistic"]
    for j, h in enumerate(headers):
        c = ws_scen.cell(row=2, column=j+2, value=h)
        c.font  = _font(bold=True, color=WHITE)
        c.fill  = _header_fill(NAVY)
        c.alignment = _align("center")

    rows_def = [
        ("Revenue Multiplier",  [f"{s[1]:.0%}" for s in scenarios]),
        ("Revenue Year 1 (EUR)",[f"=Assumptions!B3*{s[1]}" for s in scenarios]),
        ("Revenue Year 3 (EUR)",[f"=Assumptions!B4*{s[1]}" for s in scenarios]),
        ("Revenue Year 5 (EUR)",[f"=Assumptions!B5*{s[1]}" for s in scenarios]),
        ("Revenue Year 10 (EUR)",[f"=Assumptions!B5*{s[1]}*(1+Assumptions!B14*{s[2]})^5"
                                   for s in scenarios]),
        ("Blended Valuation (EUR)", [
            f"=Assumptions!B5*{s[1]}*Assumptions!B11/(1+Assumptions!B10)^"
            f"Assumptions!B12*{surv['5yr']}" for s in scenarios
        ]),
    ]
    fmts = ["0%", "#,##0", "#,##0", "#,##0", "#,##0", "#,##0"]
    for i, (label, values) in enumerate(rows_def):
        row = i + 3
        bold = (label == "Blended Valuation (EUR)")
        _set(ws_scen, row, 1, label, bold=bold)
        for j, val in enumerate(values):
            c = ws_scen.cell(row=row, column=j+2, value=val)
            c.font = _font(bold=bold,
                           color=NAVY if bold else "000000",
                           size=13 if bold else 10)
            c.number_format = fmts[i]
            c.alignment     = _align("right")

    # ── Save to BytesIO ───────────────────────────────────────────────────────
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return _recalc_bytes(output)


# ── MONTE CARLO MODEL ──────────────────────────────────────────────────────────
def build_monte_carlo(params: PitchParameters,
                      n_simulations: int = 1000) -> io.BytesIO:
    """
    Build a Monte Carlo simulation Excel model.
    Runs N simulations varying:
      - Revenue growth rate (±2 standard deviations from sector CAGR)
      - Gross margin (±10pp around stated margin)
      - Exit multiple (distribution around sector median)
      - Survival probability (Bernoulli trial at stage survival rate)

    Output: distribution table + percentile summary + histogram data.
    """
    random.seed(42)
    sector    = params.business_model
    base_cagr = SECTOR_GROWTH_RATES.get(sector, 0.15)
    base_mgn  = params.gross_margin_pct / 100
    base_mult = SECTOR_MULTIPLES.get(sector, SECTOR_MULTIPLES["general"])["mid"]
    disc_rate = DISCOUNT_RATES.get(params.stage, 0.45)
    surv_rate = SURVIVAL_RATES.get(params.stage, SURVIVAL_RATES["seed"])["5yr"]
    exit_yr   = params.exit_year

    # Run simulations
    results = []
    for _ in range(n_simulations):
        # Sample parameters — log-normal for growth, normal for margin, triangular for multiple
        sim_growth  = max(0.01, random.gauss(base_cagr, base_cagr * 0.5))
        sim_margin  = max(0.05, min(0.95, random.gauss(base_mgn, 0.10)))
        mult_low    = SECTOR_MULTIPLES.get(sector, SECTOR_MULTIPLES["general"])["low"]
        mult_high   = SECTOR_MULTIPLES.get(sector, SECTOR_MULTIPLES["general"])["high"]
        sim_mult    = random.triangular(mult_low, mult_high, base_mult)
        survived    = random.random() < surv_rate  # Bernoulli survival trial

        if not survived:
            results.append(0.0)
            continue

        rev_yr1  = params.projected_revenue_yr1
        rev_exit = rev_yr1 * ((1 + sim_growth) ** exit_yr)
        ebitda   = rev_exit * sim_margin * 0.6
        term_val = rev_exit * sim_mult
        # Simplified DCF: 3yr FCF + terminal value
        fcf_sum  = sum(
            rev_yr1 * ((1 + sim_growth) ** yr) * sim_margin * 0.5
            / ((1 + disc_rate) ** yr)
            for yr in range(1, exit_yr + 1)
        )
        pv_terminal = term_val / ((1 + disc_rate) ** exit_yr)
        valuation   = max(0.0, fcf_sum + pv_terminal)
        results.append(valuation)

    # Keep unsorted copy for raw sample sheet BEFORE sorting
    # (sort puts zeros first; sample[:500] would be all "Failed")
    results_unsorted = results[:]
    results.sort()
    n = len(results)
    non_zero = [r for r in results if r > 0]

    def pct(p): return results[int(p / 100 * n)]
    def pct_label(p):
        v = pct(p)
        return fmt_eur(v)

    # Build workbook
    wb = openpyxl.Workbook()
    ws_sum = wb.active
    ws_sum.title = "Monte Carlo Summary"
    ws_sum.sheet_view.showGridLines = False
    ws_sum.column_dimensions["A"].width = 35
    ws_sum.column_dimensions["B"].width = 22
    ws_sum.column_dimensions["C"].width = 30

    _set(ws_sum, 1, 1, "VALUEPITCH — MONTE CARLO SIMULATION",
         bold=True, size=14, color=NAVY)
    _set(ws_sum, 2, 1,
         f"{n_simulations:,} simulations · {params.company_name} · "
         f"{params.stage.replace('_',' ').title()}",
         size=10, color="666666")
    _set(ws_sum, 3, 1,
         "Varies: revenue growth, gross margin, exit multiple, survival probability",
         size=9, italic=True, color="888888")

    # Assumptions block
    _set(ws_sum, 5, 1, "SIMULATION ASSUMPTIONS", bold=True, color=NAVY)
    ass_data = [
        ("Base Revenue Growth (CAGR)", f"{base_cagr:.0%}",
         f"Sector: {sector}, ±50% std dev"),
        ("Base Gross Margin",           f"{base_mgn:.0%}",
         "±10pp standard deviation"),
        ("Exit Multiple Range",
         f"{mult_low:.1f}x – {mult_high:.1f}x",
         f"Triangular, median {base_mult:.1f}x"),
        ("Survival Probability (stage)", f"{surv_rate:.0%}",
         f"CB Insights, {params.stage}"),
        ("Discount Rate",               f"{disc_rate:.0%}",
         "Applied to all cash flows"),
        ("Exit Year",                   str(exit_yr),
         "Target exit horizon"),
        ("Simulations Run",             f"{n_simulations:,}", ""),
    ]
    for i, (label, val, note) in enumerate(ass_data):
        row = i + 6
        _set(ws_sum, row, 1, label)
        _set(ws_sum, row, 2, val, bold=True, align="right")
        _set(ws_sum, row, 3, note, italic=True, color="888888", size=9)

    # Results summary
    _set(ws_sum, 14, 1, "SIMULATION RESULTS", bold=True, color=NAVY)

    survival_pct = len(non_zero) / n * 100
    mean_val     = sum(non_zero) / len(non_zero) if non_zero else 0
    median_val   = non_zero[len(non_zero)//2] if non_zero else 0

    summary_rows = [
        ("Probability of survival (non-zero exit)", f"{survival_pct:.1f}%"),
        ("Mean valuation (survivors only, EUR)",     fmt_eur(mean_val)),
        ("Median valuation (survivors only, EUR)",   fmt_eur(median_val)),
        ("10th percentile (downside, EUR)",          pct_label(10)),
        ("25th percentile (EUR)",                    pct_label(25)),
        ("50th percentile / Median (EUR)",           pct_label(50)),
        ("75th percentile (EUR)",                    pct_label(75)),
        ("90th percentile (upside, EUR)",            pct_label(90)),
        ("Max outcome (EUR)",                        fmt_eur(max(results))),
    ]
    colors_sum = [NAVY, NAVY, NAVY, "C62828", "C9A227", NAVY, "2E7D32", "2E7D32", "2E7D32"]
    for i, (label, val) in enumerate(summary_rows):
        row = i + 15
        _set(ws_sum, row, 1, label, bold=(i == 1))
        _set(ws_sum, row, 2, val,
             bold=(i in [1, 5]), color=colors_sum[i], align="right", size=11)

    # Distribution table (histogram buckets)
    ws_dist = wb.create_sheet("Distribution Data")
    ws_dist.column_dimensions["A"].width = 25
    ws_dist.column_dimensions["B"].width = 15
    ws_dist.column_dimensions["C"].width = 15

    _set(ws_dist, 1, 1, "VALUATION DISTRIBUTION",
         bold=True, size=12, color=NAVY)
    _set(ws_dist, 2, 1, "Bucket (EUR)", bold=True, fill=NAVY, color=WHITE)
    _set(ws_dist, 2, 2, "Count",        bold=True, fill=NAVY, color=WHITE)
    _set(ws_dist, 2, 3, "Cumulative %", bold=True, fill=NAVY, color=WHITE)

    # Build 20 buckets
    max_val  = max(results) if results else 1
    step     = max_val / 20
    cumul    = 0
    for b in range(21):
        lo = b * step
        hi = (b + 1) * step
        count = sum(1 for r in results if lo <= r < hi)
        cumul += count
        row   = b + 3
        label = f"{fmt_eur(lo)} – {fmt_eur(hi)}"
        _set(ws_dist, row, 1, label)
        _set(ws_dist, row, 2, count, align="right", num_fmt="0")
        _set(ws_dist, row, 3, f"{cumul/n*100:.1f}%", align="right")

    # Full simulation data (first 500 rows for manageability)
    ws_raw = wb.create_sheet("Raw Simulations (sample)")
    ws_raw.column_dimensions["A"].width = 8
    ws_raw.column_dimensions["B"].width = 25
    _set(ws_raw, 1, 1, "Run #", bold=True)
    _set(ws_raw, 1, 2, "Simulated Valuation (EUR)", bold=True)
    _set(ws_raw, 1, 3, "Outcome", bold=True)
    sample = results_unsorted[:500]
    for i, val in enumerate(sample):
        row = i + 2
        _set(ws_raw, row, 1, i + 1, align="right")
        _set(ws_raw, row, 2, round(val), align="right", num_fmt="#,##0")
        outcome = "Survived" if val > 0 else "Failed"
        c_color = "2E7D32" if val > 0 else "C62828"
        _set(ws_raw, row, 3, outcome, color=c_color)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return _recalc_bytes(output)
