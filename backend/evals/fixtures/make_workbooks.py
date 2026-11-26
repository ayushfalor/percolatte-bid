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
    "capacity_mw": 150,
    "cuf": 0.34,
    "tariff": 3.55,
    "capex_cr_per_mw": 6.8,
    "om_lakh_per_mw": 9.0,
    "om_escalation": 0.04,
    "debt_share": 0.75,
    "interest": 0.095,
    "tenor": 15,
    "tax": 0.2517,
    "dep_life": 25,
    "availability_loss": 0.01,
    "years": 25,
}

# Bugs planted in make_wind_with_planted_bugs, the solar sample's two traps on a different layout.
INSURANCE_RATE = 0.0025  # of total capex a year, never referenced by any formula
TYPED_OVER_YEAR = 8  # someone pasted a number over the O&M formula for this year
TYPED_OVER_VALUE = -15.0  # INR Cr; the formula for year 8 gives about -17.77


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


def wind_equity_irr(p: dict, *, om_typed_over: dict[int, float] | None = None, insurance: bool = False) -> float:
    """Equity IRR in plain Python. `om_typed_over` maps a year to the O&M value someone typed
    over the formula (INR Cr, negative); `insurance` charges INSURANCE_RATE of total capex a year."""
    capex = p["capacity_mw"] * p["capex_cr_per_mw"]
    debt = capex * p["debt_share"]
    cfs, opening = [-(capex - debt)], debt
    for y in range(1, p["years"] + 1):
        gen = p["capacity_mw"] * p["cuf"] * 8766 / 1000 * (1 - p["availability_loss"])
        om = -p["capacity_mw"] * p["om_lakh_per_mw"] * (1 + p["om_escalation"]) ** (y - 1) / 100
        if om_typed_over and y in om_typed_over:
            om = om_typed_over[y]
        if insurance:
            om -= capex * INSURANCE_RATE
        ebitda = gen * p["tariff"] / 10 + om
        interest = -opening * p["interest"]
        principal = -(debt / p["tenor"]) if y <= p["tenor"] else 0.0
        opening = opening + principal
        dep = -capex / p["dep_life"]
        pbt = ebitda + interest + dep
        tax = -max(0.0, pbt * p["tax"])
        cfs.append(ebitda + interest + principal + tax)
    return _irr(cfs)


def wind_breakeven(target_irr: float, p: dict = WIND, **planted) -> float:
    lo, hi = 1.0, 8.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if wind_equity_irr({**p, "tariff": mid}, **planted) < target_irr:
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
        ("Capacity", p["capacity_mw"], "MW"),
        ("CUF", p["cuf"], "fraction"),
        ("Tariff", p["tariff"], "INR/kWh"),
        ("Capex", p["capex_cr_per_mw"], "INR Cr/MW"),
        ("O&M", p["om_lakh_per_mw"], "INR lakh/MW/yr"),
        ("O&M escalation", p["om_escalation"], "fraction"),
        ("Debt share", p["debt_share"], "fraction"),
        ("Interest", p["interest"], "fraction"),
        ("Loan tenor", p["tenor"], "yrs"),
        ("Tax rate", p["tax"], "fraction"),
        ("Depreciation life", p["dep_life"], "yrs"),
        ("Availability loss", p["availability_loss"], "fraction"),
    ]
    for r in rows:
        a.append(list(r))  # rows 3..14 -> B3 capacity ... B14 availability loss

    s = wb.create_sheet("Annual")
    s.append(
        [
            "Year",
            "Generation (MU)",
            "Revenue",
            "O&M",
            "EBITDA",
            "Opening debt",
            "Interest",
            "Principal",
            "Closing debt",
            "Depreciation",
            "PBT",
            "Tax",
            "",
            "Equity CF",
        ]
    )  # column M left blank on purpose
    A = "Assumptions!"
    s.append([0, 0, 0, 0, 0, 0, 0, 0, f"={A}$B$3*{A}$B$6*{A}$B$9", 0, 0, 0, None, f"=-({A}$B$3*{A}$B$6*(1-{A}$B$9))"])
    for r in range(3, 3 + p["years"]):
        s.append(
            [
                f"=A{r - 1}+1",
                f"={A}$B$3*{A}$B$4*8766/1000*(1-{A}$B$14)",
                f"=B{r}*{A}$B$5/10",
                f"=-{A}$B$3*{A}$B$7*(1+{A}$B$8)^(A{r}-1)/100",
                f"=C{r}+D{r}",
                f"=I{r - 1}",
                f"=-F{r}*{A}$B$10",
                f"=-IF(A{r}<={A}$B$11,$I$2/{A}$B$11,0)",
                f"=F{r}+H{r}",
                f"=-{A}$B$3*{A}$B$6/{A}$B$13",
                f"=E{r}+G{r}+J{r}",
                f"=-MAX(0,K{r}*{A}$B$12)",
                None,
                f"=E{r}+G{r}+H{r}+L{r}",
            ]
        )
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


def make_wind_with_planted_bugs(path: str) -> dict:
    """The wind model with the sample's two traps on a different layout.

    Same vertical wind model, plus an insurance rate nothing references and a number pasted over
    the O&M formula for one year. The labels mirror the solar sample's wording ("% of capex p.a.",
    a total capex cell in INR Cr) so the Auditor has to find the wiring target through labels and
    the reference graph rather than from a remembered cell address.
    """
    p = WIND
    wb = Workbook()
    a = wb.active
    a.title = "Assumptions"
    a["A1"] = "WIND PROJECT ASSUMPTIONS"
    a.merge_cells("A1:C1")
    a.append(["Item", "Value", "Unit"])
    rows = [
        ("Capacity", p["capacity_mw"], "MW"),
        ("CUF", p["cuf"], "fraction"),
        ("Tariff", p["tariff"], "INR/kWh"),
        ("Capex", p["capex_cr_per_mw"], "INR Cr/MW"),
        ("O&M", p["om_lakh_per_mw"], "INR lakh/MW/yr"),
        ("O&M escalation", p["om_escalation"], "fraction"),
        ("Debt share", p["debt_share"], "fraction"),
        ("Interest", p["interest"], "fraction"),
        ("Loan tenor", p["tenor"], "yrs"),
        ("Tax rate", p["tax"], "fraction"),
        ("Depreciation life", p["dep_life"], "yrs"),
        ("Availability loss", p["availability_loss"], "fraction"),
    ]
    for r in rows:
        a.append(list(r))  # rows 3..14 -> B3 capacity ... B14 availability loss
    # Appended last on purpose: the Annual formulas use absolute $B$3..$B$14, so inserting would shift them.
    a.append(["Insurance", INSURANCE_RATE, "% of capex p.a."])  # row 15, referenced by nothing

    s = wb.create_sheet("Annual")
    s.append(
        [
            "Year",
            "Generation (MU)",
            "Revenue",
            "O&M",
            "EBITDA",
            "Opening debt",
            "Interest",
            "Principal",
            "Closing debt",
            "Depreciation",
            "PBT",
            "Tax",
            "",
            "Equity CF",
        ]
    )  # column M left blank on purpose
    A = "Assumptions!"
    s.append([0, 0, 0, 0, 0, 0, 0, 0, f"={A}$B$3*{A}$B$6*{A}$B$9", 0, 0, 0, None, f"=-({A}$B$3*{A}$B$6*(1-{A}$B$9))"])
    for r in range(3, 3 + p["years"]):
        s.append(
            [
                f"=A{r - 1}+1",
                f"={A}$B$3*{A}$B$4*8766/1000*(1-{A}$B$14)",
                f"=B{r}*{A}$B$5/10",
                f"=-{A}$B$3*{A}$B$7*(1+{A}$B$8)^(A{r}-1)/100",
                f"=C{r}+D{r}",
                f"=I{r - 1}",
                f"=-F{r}*{A}$B$10",
                f"=-IF(A{r}<={A}$B$11,$I$2/{A}$B$11,0)",
                f"=F{r}+H{r}",
                f"=-{A}$B$3*{A}$B$6/{A}$B$13",
                f"=E{r}+G{r}+J{r}",
                f"=-MAX(0,K{r}*{A}$B$12)",
                None,
                f"=E{r}+G{r}+H{r}+L{r}",
            ]
        )
    typed_over_row = TYPED_OVER_YEAR + 2  # row 3 is year 1
    s[f"D{typed_over_row}"] = TYPED_OVER_VALUE  # a number pasted over the O&M formula

    last = 2 + p["years"]
    m = wb.create_sheet("Summary")
    m.append(["Metric", "Value"])
    m.append(["Equity IRR", f"=IRR(Annual!N2:N{last})"])
    m.append(["Total capex (INR Cr)", f"={A}B3*{A}B6"])
    m.append(["Year-1 revenue (INR Cr)", "=Annual!C3"])

    old = wb.create_sheet("OLD_assumptions")
    old.append(["Tariff", 3.9])
    old.append(["CUF", 0.31])
    old.sheet_state = "hidden"
    wb.save(path)

    typed_over = {TYPED_OVER_YEAR: TYPED_OVER_VALUE}
    as_is = wind_breakeven(0.12, p, om_typed_over=typed_over)
    fixed_hardcode = wind_breakeven(0.12, p)
    with_insurance = wind_breakeven(0.12, p, om_typed_over=typed_over, insurance=True)
    both = wind_breakeven(0.12, p, insurance=True)
    return {
        "equity_irr_cell": "Summary!B2",
        "tariff_cell": "Assumptions!B5",
        "total_capex_cell": "Summary!B3",
        "legacy_sheet": "OLD_assumptions",
        "target_irr": 0.12,
        "typed_over_cell": f"Annual!D{typed_over_row}",
        "typed_over_value": TYPED_OVER_VALUE,
        "orphan_input_cell": "Assumptions!B15",
        "om_row_cells": [f"Annual!D{r}" for r in range(3, 3 + p["years"])],
        "equity_irr": wind_equity_irr(p, om_typed_over=typed_over),
        "breakeven": as_is,
        "breakeven_typed_over_fixed": fixed_hardcode,
        "breakeven_insurance_wired": with_insurance,
        "breakeven_both_fixed": both,
        "impact_typed_over": fixed_hardcode - as_is,
        "impact_insurance": with_insurance - as_is,
    }


WHOLE_COLUMN_CUF = 0.36  # the scenario the lookup selects, different from WIND's own CUF


def _wind_body(wb, p: dict, cuf_formula: str, extra_assumptions: list[list] | None = None) -> None:
    """The shared wind model body: assumptions, the annual series and a summary."""
    a = wb.active
    a.title = "Assumptions"
    a["A1"] = "WIND PROJECT ASSUMPTIONS"
    a.merge_cells("A1:C1")
    a.append(["Item", "Value", "Unit"])
    rows = [
        ("Capacity", p["capacity_mw"], "MW"),
        ("CUF", cuf_formula, "fraction"),
        ("Tariff", p["tariff"], "INR/kWh"),
        ("Capex", p["capex_cr_per_mw"], "INR Cr/MW"),
        ("O&M", p["om_lakh_per_mw"], "INR lakh/MW/yr"),
        ("O&M escalation", p["om_escalation"], "fraction"),
        ("Debt share", p["debt_share"], "fraction"),
        ("Interest", p["interest"], "fraction"),
        ("Loan tenor", p["tenor"], "yrs"),
        ("Tax rate", p["tax"], "fraction"),
        ("Depreciation life", p["dep_life"], "yrs"),
        ("Availability loss", p["availability_loss"], "fraction"),
    ]
    for r in rows:
        a.append(list(r))  # rows 3..14 -> B3 capacity ... B14 availability loss
    for extra in extra_assumptions or []:
        a.append(extra)  # appended last: the Annual formulas use absolute $B$3..$B$14

    s = wb.create_sheet("Annual")
    s.append(
        [
            "Year",
            "Generation (MU)",
            "Revenue",
            "O&M",
            "EBITDA",
            "Opening debt",
            "Interest",
            "Principal",
            "Closing debt",
            "Depreciation",
            "PBT",
            "Tax",
            "",
            "Equity CF",
        ]
    )
    A = "Assumptions!"
    s.append([0, 0, 0, 0, 0, 0, 0, 0, f"={A}$B$3*{A}$B$6*{A}$B$9", 0, 0, 0, None, f"=-({A}$B$3*{A}$B$6*(1-{A}$B$9))"])
    for r in range(3, 3 + p["years"]):
        s.append(
            [
                f"=A{r - 1}+1",
                f"={A}$B$3*{A}$B$4*8766/1000*(1-{A}$B$14)",
                f"=B{r}*{A}$B$5/10",
                f"=-{A}$B$3*{A}$B$7*(1+{A}$B$8)^(A{r}-1)/100",
                f"=C{r}+D{r}",
                f"=I{r - 1}",
                f"=-F{r}*{A}$B$10",
                f"=-IF(A{r}<={A}$B$11,$I$2/{A}$B$11,0)",
                f"=F{r}+H{r}",
                f"=-{A}$B$3*{A}$B$6/{A}$B$13",
                f"=E{r}+G{r}+J{r}",
                f"=-MAX(0,K{r}*{A}$B$12)",
                None,
                f"=E{r}+G{r}+H{r}+L{r}",
            ]
        )
    last = 2 + p["years"]
    m = wb.create_sheet("Summary")
    m.append(["Metric", "Value"])
    m.append(["Equity IRR", f"=IRR(Annual!N2:N{last})"])
    m.append(["Total capex (INR Cr)", f"={A}B3*{A}B6"])
    m.append(["Year-1 revenue (INR Cr)", "=Annual!C3"])


def make_wind_whole_column(path: str) -> dict:
    """A scenario tab that is read only through a whole-column lookup.

    VLOOKUP(selector, Scenarios!A:C, 3, FALSE) gives the right CUF, but a reference graph that
    skips whole-column references sees no edge into Scenarios at all, so the sheet looks like an
    abandoned copy and its numbers look like inputs nobody reads.
    """
    p = {**WIND, "cuf": WHOLE_COLUMN_CUF}
    wb = Workbook()
    _wind_body(wb, p, "=VLOOKUP($B$15,Scenarios!A:C,3,FALSE)", [["Scenario", 2, "#"]])

    sc = wb.create_sheet("Scenarios")
    sc.append(["#", "Scenario", "CUF"])
    sc.append([1, "Base", 0.34])
    sc.append([2, "High", WHOLE_COLUMN_CUF])
    sc.append([3, "Low", 0.31])
    wb.save(path)
    return {
        "equity_irr_cell": "Summary!B2",
        "tariff_cell": "Assumptions!B5",
        "cuf_cell": "Assumptions!B4",
        "lookup_sheet": "Scenarios",
        "selected_cuf": WHOLE_COLUMN_CUF,
        "target_irr": 0.12,
        "equity_irr": wind_equity_irr(p),
        "breakeven": wind_breakeven(0.12, p),
    }


# Interest during construction: the classic circular reference in a project finance model.
# IDC is a share of total capex, and total capex includes IDC.
IDC = {
    "capacity_mw": 150,
    "cuf": 0.34,
    "tariff": 3.55,
    "base_capex_cr": 800.0,
    "om_lakh_per_mw": 9.0,
    "om_escalation": 0.04,
    "debt_share": 0.7,
    "interest": 0.0925,
    "tenor": 15,
    "tax": 0.2517,
    "dep_life": 25,
    "availability_loss": 0.01,
    "years": 25,
}


def idc_total_capex(p: dict = IDC) -> float:
    """Solved in closed form: total = base + debt_share * interest * total."""
    return p["base_capex_cr"] / (1 - p["debt_share"] * p["interest"])


def idc_equity_irr(p: dict = IDC) -> float:
    capex = idc_total_capex(p)
    debt = capex * p["debt_share"]
    cfs, opening = [-(capex - debt)], debt
    for y in range(1, p["years"] + 1):
        gen = p["capacity_mw"] * p["cuf"] * 8766 / 1000 * (1 - p["availability_loss"])
        om = -p["capacity_mw"] * p["om_lakh_per_mw"] * (1 + p["om_escalation"]) ** (y - 1) / 100
        ebitda = gen * p["tariff"] / 10 + om
        interest = -opening * p["interest"]
        principal = -(debt / p["tenor"]) if y <= p["tenor"] else 0.0
        opening = opening + principal
        dep = -capex / p["dep_life"]
        tax = -max(0.0, (ebitda + interest + dep) * p["tax"])
        cfs.append(ebitda + interest + principal + tax)
    return _irr(cfs)


def idc_breakeven(target_irr: float, p: dict = IDC) -> float:
    lo, hi = 1.0, 8.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if idc_equity_irr({**p, "tariff": mid}) < target_irr:
            lo = mid
        else:
            hi = mid
    return hi


def make_idc_loop(path: str) -> dict:
    """A model whose capex depends on itself through interest during construction.

    Excel solves this with iterative calculation turned on. Our formula library returns nothing
    for the cycle by default, and zero when told to tolerate circularity, so both the capex and
    every number built on it come out wrong unless the cycle is solved on purpose.
    """
    p = IDC
    wb = Workbook()
    a = wb.active
    a.title = "Assumptions"
    a["A1"] = "PROJECT ASSUMPTIONS"
    a.append(["Item", "Value", "Unit"])
    for row in [
        ("Capacity", p["capacity_mw"], "MW"),
        ("CUF", p["cuf"], "fraction"),
        ("Tariff", p["tariff"], "INR/kWh"),
        ("Base capex", p["base_capex_cr"], "INR Cr"),
        ("O&M", p["om_lakh_per_mw"], "INR lakh/MW/yr"),
        ("O&M escalation", p["om_escalation"], "fraction"),
        ("Debt share", p["debt_share"], "fraction"),
        ("Interest", p["interest"], "fraction"),
        ("Loan tenor", p["tenor"], "yrs"),
        ("Tax rate", p["tax"], "fraction"),
        ("Depreciation life", p["dep_life"], "yrs"),
        ("Availability loss", p["availability_loss"], "fraction"),
    ]:
        a.append(list(row))  # rows 3..14 -> B3 capacity ... B14 availability loss
    a.append(["IDC", "=$B$9*$B$10*$B$16", "INR Cr"])  # row 15, reads total capex
    a.append(["Total capex", "=$B$6+$B$15", "INR Cr"])  # row 16, reads IDC: the loop

    s = wb.create_sheet("Annual")
    s.append(
        [
            "Year",
            "Generation (MU)",
            "Revenue",
            "O&M",
            "EBITDA",
            "Opening debt",
            "Interest",
            "Principal",
            "Closing debt",
            "Depreciation",
            "PBT",
            "Tax",
            "",
            "Equity CF",
        ]
    )
    A = "Assumptions!"
    s.append([0, 0, 0, 0, 0, 0, 0, 0, f"={A}$B$16*{A}$B$9", 0, 0, 0, None, f"=-({A}$B$16*(1-{A}$B$9))"])
    for r in range(3, 3 + p["years"]):
        s.append(
            [
                f"=A{r - 1}+1",
                f"={A}$B$3*{A}$B$4*8766/1000*(1-{A}$B$14)",
                f"=B{r}*{A}$B$5/10",
                f"=-{A}$B$3*{A}$B$7*(1+{A}$B$8)^(A{r}-1)/100",
                f"=C{r}+D{r}",
                f"=I{r - 1}",
                f"=-F{r}*{A}$B$10",
                f"=-IF(A{r}<={A}$B$11,$I$2/{A}$B$11,0)",
                f"=F{r}+H{r}",
                f"=-{A}$B$16/{A}$B$13",
                f"=E{r}+G{r}+J{r}",
                f"=-MAX(0,K{r}*{A}$B$12)",
                None,
                f"=E{r}+G{r}+H{r}+L{r}",
            ]
        )
    last = 2 + p["years"]
    m = wb.create_sheet("Summary")
    m.append(["Metric", "Value"])
    m.append(["Equity IRR", f"=IRR(Annual!N2:N{last})"])
    m.append(["Total capex (INR Cr)", f"={A}B16"])
    wb.save(path)
    return {
        "equity_irr_cell": "Summary!B2",
        "tariff_cell": "Assumptions!B5",
        "idc_cell": "Assumptions!B15",
        "total_capex_cell": "Assumptions!B16",
        "cycle_cells": {"Assumptions!B15", "Assumptions!B16"},
        "target_irr": 0.12,
        "total_capex": idc_total_capex(p),
        "idc": idc_total_capex(p) - p["base_capex_cr"],
        "equity_irr": idc_equity_irr(p),
        "breakeven": idc_breakeven(0.12, p),
    }


def make_unsupported_function(path: str) -> dict:
    """A model with one cell our formula library cannot evaluate.

    OFFSET is not in the library's registry, so the cell comes back as #NAME?. The rest of the
    model is fine, so the right behaviour is to carry on, name the function and the cell, and
    refuse to price anything whose answer would depend on it.
    """
    p = WIND
    wb = Workbook()
    _wind_body(wb, p, p["cuf"])
    summary = wb["Summary"]
    summary.append(["Year-10 revenue (OFFSET)", "=OFFSET(Annual!C2,10,0)"])
    wb.save(path)
    return {
        "equity_irr_cell": "Summary!B2",
        "tariff_cell": "Assumptions!B5",
        "offset_cell": "Summary!B5",
        "unsupported": "OFFSET",
        "target_irr": 0.12,
        "equity_irr": wind_equity_irr(p),
        "breakeven": wind_breakeven(0.12, p),
    }


def make_wind_positive_costs(path: str) -> dict:
    """The same wind model with the other sign convention: costs are positive.

    EBITDA = revenue - O&M instead of revenue + O&M. A rule that looks for a positive series
    added to a negative one finds nothing here, and an insurance fix that subtracts would add
    cost where it should take it away.
    """
    p = WIND
    wb = Workbook()
    a = wb.active
    a.title = "Assumptions"
    a["A1"] = "WIND PROJECT ASSUMPTIONS"
    a.append(["Item", "Value", "Unit"])
    for row in [
        ("Capacity", p["capacity_mw"], "MW"),
        ("CUF", p["cuf"], "fraction"),
        ("Tariff", p["tariff"], "INR/kWh"),
        ("Capex", p["capex_cr_per_mw"], "INR Cr/MW"),
        ("O&M", p["om_lakh_per_mw"], "INR lakh/MW/yr"),
        ("O&M escalation", p["om_escalation"], "fraction"),
        ("Debt share", p["debt_share"], "fraction"),
        ("Interest", p["interest"], "fraction"),
        ("Loan tenor", p["tenor"], "yrs"),
        ("Tax rate", p["tax"], "fraction"),
        ("Depreciation life", p["dep_life"], "yrs"),
        ("Availability loss", p["availability_loss"], "fraction"),
    ]:
        a.append(list(row))  # rows 3..14
    a.append(["Insurance", INSURANCE_RATE, "% of capex p.a."])  # row 15, referenced by nothing

    s = wb.create_sheet("Annual")
    s.append(
        [
            "Year",
            "Generation (MU)",
            "Revenue",
            "O&M",
            "EBITDA",
            "Opening debt",
            "Interest",
            "Principal",
            "Closing debt",
            "Depreciation",
            "PBT",
            "Tax",
            "",
            "Equity CF",
        ]
    )
    A = "Assumptions!"
    s.append([0, 0, 0, 0, 0, 0, 0, 0, f"={A}$B$3*{A}$B$6*{A}$B$9", 0, 0, 0, None, f"=-({A}$B$3*{A}$B$6*(1-{A}$B$9))"])
    for r in range(3, 3 + p["years"]):
        s.append(
            [
                f"=A{r - 1}+1",
                f"={A}$B$3*{A}$B$4*8766/1000*(1-{A}$B$14)",
                f"=B{r}*{A}$B$5/10",
                f"={A}$B$3*{A}$B$7*(1+{A}$B$8)^(A{r}-1)/100",  # positive cost
                f"=C{r}-D{r}",  # revenue minus cost
                f"=I{r - 1}",
                f"={A}$B$3*{A}$B$6/{A}$B$13",  # positive depreciation
                f"=IF(A{r}<={A}$B$11,$I$2/{A}$B$11,0)",  # positive principal
                f"=F{r}-H{r}",
                f"=F{r}*{A}$B$10",  # positive interest
                f"=E{r}-G{r}-J{r}",  # PBT = EBITDA - interest - depreciation
                f"=MAX(0,K{r}*{A}$B$12)",  # positive tax
                None,
                f"=E{r}-J{r}-H{r}-L{r}",  # equity CF = EBITDA - interest - principal - tax
            ]
        )
    last = 2 + p["years"]
    m = wb.create_sheet("Summary")
    m.append(["Metric", "Value"])
    m.append(["Equity IRR", f"=IRR(Annual!N2:N{last})"])
    m.append(["Total capex (INR Cr)", f"={A}B3*{A}B6"])
    wb.save(path)

    as_is = wind_breakeven(0.12, p)
    with_insurance = wind_breakeven(0.12, p, insurance=True)
    return {
        "equity_irr_cell": "Summary!B2",
        "tariff_cell": "Assumptions!B5",
        "total_capex_cell": "Summary!B3",
        "orphan_input_cell": "Assumptions!B15",
        "om_row_cells": [f"Annual!D{r}" for r in range(3, 3 + p["years"])],
        "target_irr": 0.12,
        "equity_irr": wind_equity_irr(p),
        "breakeven": as_is,
        "breakeven_insurance_wired": with_insurance,
        "impact_insurance": with_insurance - as_is,
    }


EDGE_TYPED_OVER = {1: -11.0, 13: -19.0, 25: -27.0}  # first year, a middle year, and the last year


def make_wind_typed_over_edges(path: str) -> dict:
    """Numbers pasted over the O&M formula at the first year, a middle year and the last year.

    A run detector that needs a formula on both sides of the gap, or that stops at the first
    number it meets, misses the ends of the row and finds only one of the three.
    """
    p = WIND
    wb = Workbook()
    _wind_body(wb, p, p["cuf"])
    annual = wb["Annual"]
    for year, value in EDGE_TYPED_OVER.items():
        annual[f"D{year + 2}"] = value  # row 3 is year 1

    wb.save(path)
    as_is = wind_breakeven(0.12, p, om_typed_over=EDGE_TYPED_OVER)
    fixed = wind_breakeven(0.12, p)
    return {
        "equity_irr_cell": "Summary!B2",
        "tariff_cell": "Assumptions!B5",
        "typed_over_cells": [f"Annual!D{year + 2}" for year in sorted(EDGE_TYPED_OVER)],
        "target_irr": 0.12,
        "equity_irr": wind_equity_irr(p, om_typed_over=EDGE_TYPED_OVER),
        "breakeven": as_is,
        "breakeven_all_fixed": fixed,
        "impact_all_fixed": fixed - as_is,
    }


def make_wind_dynamic_refs(path: str) -> dict:
    """A model that builds a reference at run time, so the static graph cannot be trusted.

    INDIRECT("Scenarios!B"&selector) reaches a sheet and a cell that no formula names in
    plain text. With that in the workbook, "nothing reads this" is a guess, not a fact, so
    unused-input and abandoned-sheet findings should drop to information with a warning.
    """
    p = WIND
    wb = Workbook()
    _wind_body(wb, p, p["cuf"], [["Insurance", INSURANCE_RATE, "% of capex p.a."], ["Scenario", 2, "#"]])
    wb["Summary"].append(["CUF from the scenario tab", '=INDIRECT("Scenarios!C"&(Assumptions!B16+1))'])
    sc = wb.create_sheet("Scenarios")
    sc.append(["#", "Scenario", "CUF"])
    sc.append([1, "Base", 0.34])
    sc.append([2, "High", 0.36])
    old = wb.create_sheet("OLD_assumptions")
    old.append(["Tariff", 3.9])
    old.sheet_state = "hidden"
    wb.save(path)
    return {
        "equity_irr_cell": "Summary!B2",
        "tariff_cell": "Assumptions!B5",
        "orphan_input_cell": "Assumptions!B15",
        "legacy_sheet": "OLD_assumptions",
        "dynamic_cell": "Summary!B5",
        "target_irr": 0.12,
    }


RENAMED_HURDLE = 0.11  # written into the workbook, so it must win over the A-01 default


def make_renamed_labels(path: str) -> dict:
    """The wind model with nothing called by the names we first looked for, and no named ranges.

    "Levellised tariff (Rs/kWh)" instead of Tariff, "IRR to equity" instead of Equity IRR, a
    "Hurdle" row the model itself carries, "Operating expenses" instead of O&M and "Total
    investment" instead of capex. The numbers are the same; only the words changed.
    """
    p = WIND
    wb = Workbook()
    a = wb.active
    a.title = "Inputs"
    a["A1"] = "PROJECT INPUTS"
    a.append(["Item", "Value", "Unit"])
    for row in [
        ("Installed capacity", p["capacity_mw"], "MW"),
        ("Plant load factor", p["cuf"], "fraction"),
        ("Levellised tariff (Rs/kWh)", p["tariff"], ""),
        ("Investment per MW", p["capex_cr_per_mw"], "Rs Cr/MW"),
        ("Operating expenses", p["om_lakh_per_mw"], "Rs lakh/MW/yr"),
        ("Opex escalation", p["om_escalation"], "fraction"),
        ("Gearing", p["debt_share"], "fraction"),
        ("Cost of debt", p["interest"], "fraction"),
        ("Repayment period", p["tenor"], "yrs"),
        ("Tax", p["tax"], "fraction"),
        ("Asset life", p["dep_life"], "yrs"),
        ("Availability loss", p["availability_loss"], "fraction"),
    ]:
        a.append(list(row))  # rows 3..14, same positions as the wind body
    a.append(["Insurance", INSURANCE_RATE, "% of total investment p.a."])  # row 15, unreferenced
    a.append(["Hurdle", RENAMED_HURDLE, "fraction"])  # row 16, unreferenced on purpose

    s = wb.create_sheet("Cashflow")
    s.append(
        [
            "Year",
            "Energy (MU)",
            "Sales",
            "Operating expenses",
            "Operating margin",
            "Debt b/f",
            "Finance cost",
            "Repayment",
            "Debt c/f",
            "Depreciation",
            "Profit before tax",
            "Tax",
            "",
            "Cash to equity",
        ]
    )
    A = "Inputs!"
    s.append([0, 0, 0, 0, 0, 0, 0, 0, f"={A}$B$3*{A}$B$6*{A}$B$9", 0, 0, 0, None, f"=-({A}$B$3*{A}$B$6*(1-{A}$B$9))"])
    for r in range(3, 3 + p["years"]):
        s.append(
            [
                f"=A{r - 1}+1",
                f"={A}$B$3*{A}$B$4*8766/1000*(1-{A}$B$14)",
                f"=B{r}*{A}$B$5/10",
                f"=-{A}$B$3*{A}$B$7*(1+{A}$B$8)^(A{r}-1)/100",
                f"=C{r}+D{r}",
                f"=I{r - 1}",
                f"=-F{r}*{A}$B$10",
                f"=-IF(A{r}<={A}$B$11,$I$2/{A}$B$11,0)",
                f"=F{r}+H{r}",
                f"=-{A}$B$3*{A}$B$6/{A}$B$13",
                f"=E{r}+G{r}+J{r}",
                f"=-MAX(0,K{r}*{A}$B$12)",
                None,
                f"=E{r}+G{r}+H{r}+L{r}",
            ]
        )
    last = 2 + p["years"]
    m = wb.create_sheet("Results")
    m.append(["Metric", "Value"])
    m.append(["IRR to equity", f"=IRR(Cashflow!N2:N{last})"])
    m.append(["Total investment (Rs Cr)", f"={A}B3*{A}B6"])
    wb.save(path)

    as_is = wind_breakeven(RENAMED_HURDLE, p)
    with_insurance = wind_breakeven(RENAMED_HURDLE, p, insurance=True)
    return {
        "equity_irr_cell": "Results!B2",
        "tariff_cell": "Inputs!B5",
        "hurdle_cell": "Inputs!B16",
        "hurdle": RENAMED_HURDLE,
        "orphan_input_cell": "Inputs!B15",
        "om_row_cells": [f"Cashflow!D{r}" for r in range(3, 3 + p["years"])],
        "equity_irr": wind_equity_irr(p),
        "breakeven": as_is,
        "impact_insurance": with_insurance - as_is,
    }
