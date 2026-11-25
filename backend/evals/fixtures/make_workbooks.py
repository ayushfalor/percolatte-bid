"""Generate workbooks the app has never seen, with ground truth computed in Python.

The point: their eval suite will use a workbook we have not seen. So ours must
too. Each generator writes an .xlsx with live formulas (no cached values, the
hardest case) and returns the answers computed independently in Python.

Add more generators here as you harden ingestion: merged multi-row headers,
paise tariffs, INDEX/MATCH scenario tables, a Solar+ESS augmentation spike,
an injected hardcode, a #REF! on a hidden sheet.
"""
from __future__ import annotations

from openpyxl import Workbook

WIND = {
    "capacity_mw": 150, "cuf": 0.34, "tariff": 3.55, "capex_cr_per_mw": 6.8, "om_lakh_per_mw": 9.0,
    "om_escalation": 0.04, "debt_share": 0.75, "interest": 0.095, "tenor": 15, "tax": 0.2517,
    "dep_life": 25, "availability_loss": 0.01, "years": 25,
}


def _irr(cfs: list[float]) -> float:
    lo, hi = -0.99, 1.0
    f = lambda r: sum(cf / (1 + r) ** i for i, cf in enumerate(cfs))  # noqa: E731
    flo = f(lo)
    for _ in range(300):
        mid = (lo + hi) / 2
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def wind_equity_irr(p: dict) -> float:
    capex = p["capacity_mw"] * p["capex_cr_per_mw"]
    debt = capex * p["debt_share"]
    cfs, opening = [-(capex - debt)], debt
    for y in range(1, p["years"] + 1):
        gen = p["capacity_mw"] * p["cuf"] * 8766 / 1000 * (1 - p["availability_loss"])
        ebitda = gen * p["tariff"] / 10 - p["capacity_mw"] * p["om_lakh_per_mw"] * (1 + p["om_escalation"]) ** (y - 1) / 100
        interest = -opening * p["interest"]
        principal = -(debt / p["tenor"]) if y <= p["tenor"] else 0.0
        opening = opening + principal
        dep = -capex / p["dep_life"]
        pbt = ebitda + interest + dep
        tax = -max(0.0, pbt * p["tax"])
        cfs.append(ebitda + interest + principal + tax)
    return _irr(cfs)


def wind_breakeven(target_irr: float, p: dict = WIND) -> float:
    lo, hi = 1.0, 8.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if wind_equity_irr({**p, "tariff": mid}) < target_irr:
            lo = mid
        else:
            hi = mid
    return hi


def make_wind_vertical(path: str) -> dict:
    """Wind model: years run down the rows, no named ranges, decimal percents, a hidden old tab."""
    p = WIND
    wb = Workbook()
    a = wb.active
    a.title = "Assumptions"
    a["A1"] = "WIND PROJECT ASSUMPTIONS"
    a.merge_cells("A1:C1")
    a.append(["Item", "Value", "Unit"])
    rows = [
        ("Capacity", p["capacity_mw"], "MW"), ("CUF", p["cuf"], "fraction"), ("Tariff", p["tariff"], "INR/kWh"),
        ("Capex", p["capex_cr_per_mw"], "INR Cr/MW"), ("O&M", p["om_lakh_per_mw"], "INR lakh/MW/yr"),
        ("O&M escalation", p["om_escalation"], "fraction"), ("Debt share", p["debt_share"], "fraction"),
        ("Interest", p["interest"], "fraction"), ("Loan tenor", p["tenor"], "yrs"), ("Tax rate", p["tax"], "fraction"),
        ("Depreciation life", p["dep_life"], "yrs"), ("Availability loss", p["availability_loss"], "fraction"),
    ]
    for r in rows:
        a.append(list(r))  # rows 3..14 -> B3 capacity ... B14 availability loss

    s = wb.create_sheet("Annual")
    s.append(["Year", "Generation (MU)", "Revenue", "O&M", "EBITDA", "Opening debt", "Interest", "Principal",
              "Closing debt", "Depreciation", "PBT", "Tax", "", "Equity CF"])  # column M left blank on purpose
    A = "Assumptions!"
    s.append([0, 0, 0, 0, 0, 0, 0, 0, f"={A}$B$3*{A}$B$6*{A}$B$9", 0, 0, 0, None, f"=-({A}$B$3*{A}$B$6*(1-{A}$B$9))"])
    for r in range(3, 3 + p["years"]):
        s.append([
            f"=A{r-1}+1",
            f"={A}$B$3*{A}$B$4*8766/1000*(1-{A}$B$14)",
            f"=B{r}*{A}$B$5/10",
            f"=-{A}$B$3*{A}$B$7*(1+{A}$B$8)^(A{r}-1)/100",
            f"=C{r}+D{r}",
            f"=I{r-1}",
            f"=-F{r}*{A}$B$10",
            f"=-IF(A{r}<={A}$B$11,$I$2/{A}$B$11,0)",
            f"=F{r}+H{r}",
            f"=-{A}$B$3*{A}$B$6/{A}$B$13",
            f"=E{r}+G{r}+J{r}",
            f"=-MAX(0,K{r}*{A}$B$12)",
            None,
            f"=E{r}+G{r}+H{r}+L{r}",
        ])
    last = 2 + p["years"]
    m = wb.create_sheet("Summary")
    m.append(["Metric", "Value"])
    m.append(["Equity IRR", f"=IRR(Annual!N2:N{last})"])
    m.append(["Project cost (INR Cr)", f"={A}B3*{A}B6"])
    m.append(["Year-1 revenue (INR Cr)", "=Annual!C3"])

    old = wb.create_sheet("OLD_assumptions")
    old.append(["Tariff", 3.9])
    old.append(["CUF", 0.31])
    old.sheet_state = "hidden"
    wb.save(path)
    return {
        "equity_irr_cell": "Summary!B2",
        "tariff_cell": "Assumptions!B5",
        "equity_irr": wind_equity_irr(p),
        "breakeven_12pct": wind_breakeven(0.12),
        "project_cost": p["capacity_mw"] * p["capex_cr_per_mw"],
        "legacy_sheet": "OLD_assumptions",
    }
