"""What a bid model must contain to be accepted, checked at upload against the same labels the agents use.

The app is template-free in layout: sheets, rows and names can be anything. What it cannot do
without is a tariff input it can move and an equity IRR it can read. A workbook missing either
is refused at upload, in plain words, with the sample model offered as the template to copy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from openpyxl import load_workbook

from .workbook_reader import key_cells


@dataclass(frozen=True)
class Requirement:
    key: str
    title: str
    how: str  # how the app recognises it
    required: bool


REQUIREMENTS: list[Requirement] = [
    Requirement(
        "tariff",
        "A tariff input",
        "a number with a label containing the word 'tariff' (INR/kWh), or a defined name called Tariff",
        True,
    ),
    Requirement(
        "equity_irr",
        "An equity IRR result",
        "a formula with a label like 'Equity IRR' or 'IRR to equity', as a fraction (0.14 for 14%)",
        True,
    ),
    Requirement(
        "min_dscr",
        "A minimum DSCR result",
        "a formula with a label like 'Min DSCR'. Optional: without it the walk-away rests on the IRR floor alone",
        False,
    ),
    Requirement(
        "hurdle",
        "The board's hurdle rate",
        "a number with a label like 'Hurdle' or 'Target IRR'. Optional: 14% is assumed when absent (A-01)",
        False,
    ),
]


@dataclass(frozen=True)
class TemplateCheck:
    ok: bool
    found: dict[str, str | None]  # requirement key -> the cell the app will use
    missing: list[str]  # titles of required items not found
    sheets: list[str]
    formulas: int
    message: str


def _formulas(path: str) -> tuple[list[str], int]:
    wb = load_workbook(path, read_only=True)
    sheets = list(wb.sheetnames)
    count = sum(
        1
        for ws in wb.worksheets
        for row in ws.iter_rows(values_only=True)
        for cell in row
        if isinstance(cell, str) and cell.startswith("=")
    )
    wb.close()
    return sheets, count


def check_bid_model(path: str) -> TemplateCheck:
    """Does this workbook have what the agents need? Same label rules as the Auditor and the Engine."""
    sheets, formulas = _formulas(path)
    names = {name: dn.attr_text for name, dn in load_workbook(path, read_only=True).defined_names.items()}
    found = key_cells(path, names)
    missing = [r.title for r in REQUIREMENTS if r.required and not found.get(r.key)]
    if not missing:
        message = "Accepted: " + ", ".join(
            f"{r.title.lower()} at {found[r.key]}" for r in REQUIREMENTS if found.get(r.key)
        )
    else:
        what = " and ".join(m.lower() for m in missing)
        message = (
            f"This workbook has {len(sheets)} sheet(s) and {formulas} formula(s), but the app could not find {what}. "
            "It looks for the labels listed under 'What a bid model needs'. Download the template to see a model "
            "that fits, or add those labels next to the cells in yours."
        )
    return TemplateCheck(not missing, found, missing, sheets, formulas, message)


def requirements() -> list[dict]:
    return [asdict(r) for r in REQUIREMENTS]
