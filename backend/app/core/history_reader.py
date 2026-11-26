"""Auction history cleaning (deterministic, every fix is logged)."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

GENERIC = (
    "AND|PRIVATE|PVT|LIMITED|LTD|INDIA|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|HOLDINGS|PROJECTS|VENTURES|"
    "ENERGY|POWER|RENEWABLES|RE|SOLAR|GREEN|CLEAN|URJA|PARKS|INFRA|DEVELOPERS|WIND|STORAGE|HYBRID|SUN"
)


def group_name(raw: str) -> str:
    """'Narmada Clean Energy Three Ltd' and 'NARMADA CLEAN ENERGY LTD.' -> 'NARMADA'."""
    s = raw.upper().replace("&", " AND ")
    s = re.sub(r"[.(),]", " ", s)
    s = re.sub(rf"\b({GENERIC})\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or raw.upper().strip()


def read_history(path: str) -> dict[str, Any]:
    fixes: list[str] = []
    tenders = pd.read_excel(path, sheet_name="Tenders")
    bids = pd.read_excel(path, sheet_name="Bids")

    dupes = bids[bids.duplicated(keep="first")]
    if len(dupes):
        fixes.append(f"Removed {len(dupes)} exact duplicate bid row(s)")
    bids = bids.drop_duplicates()

    tariff_cols = [c for c in bids.columns if "tariff" in c.lower()]
    paise_rows = bids[(bids[tariff_cols] > 20).any(axis=1)]
    paise_tenders = sorted(paise_rows["Tender ID"].unique().tolist())
    if paise_tenders:
        bids.loc[paise_rows.index, tariff_cols] = bids.loc[paise_rows.index, tariff_cols] / 100
        fixes.append(f"Converted paise/kWh to INR/kWh for {', '.join(paise_tenders)}")
    t_tariff_cols = [c for c in tenders.columns if "tariff" in c.lower()]
    t_mask = (tenders[t_tariff_cols] > 20).any(axis=1)
    if t_mask.any():
        tenders.loc[t_mask, t_tariff_cols] = tenders.loc[t_mask, t_tariff_cols] / 100

    date_formats: dict[str, int] = {}
    for col in [c for c in tenders.columns if "date" in c.lower()]:
        kinds = tenders[col].map(lambda v: type(v).__name__).value_counts().to_dict()
        date_formats[col] = len(kinds)
        tenders[col] = pd.to_datetime(tenders[col].astype(str), format="mixed", dayfirst=True, errors="coerce")
    if any(n > 1 for n in date_formats.values()):
        fixes.append("Parsed mixed date formats (Excel dates, '22-Apr-23', '28.07.2023')")

    name_col = next(c for c in bids.columns if "bidder" in c.lower())
    bids["group"] = bids[name_col].map(group_name)
    raw_names, groups = bids[name_col].nunique(), bids["group"].nunique()
    fixes.append(f"Resolved {raw_names} bidder names into {groups} groups (SPVs and spelling variants)")

    return {
        "kind": "history",
        "tenders": len(tenders),
        "bids": len(bids),
        "categories": tenders["Category"].value_counts().to_dict() if "Category" in tenders else {},
        "duplicates_removed": len(dupes),
        "paise_tenders": paise_tenders,
        "raw_bidder_names": int(raw_names),
        "bidder_groups": int(groups),
        "fixes": fixes,
        "solar_ists": _solar_ists(tenders, bids, name_col),
    }


SOLAR_ISTS = "Solar (ISTS)"
FINAL = "Final e-RA tariff (INR/kWh)"
OPENING = "Financial bid tariff (INR/kWh)"
L1 = "L1 tariff (INR/kWh)"


def _solar_ists(tenders: pd.DataFrame, bids: pd.DataFrame, name_col: str) -> dict[str, Any]:
    """What each bidder group did in the solar ISTS auctions: the rival model's raw material.

    Kept as plain numbers per group rather than the bid rows, so the Reader's result stays small
    and the rival model never has to reopen the workbook.
    """
    solar_tenders = tenders[tenders["Category"] == SOLAR_ISTS]
    solar = bids[bids["Category"] == SOLAR_ISTS]
    l1 = {tid: float(v) for tid, v in zip(solar_tenders["Tender ID"], solar_tenders[L1], strict=True) if pd.notna(v)}
    cuts = (solar[OPENING] - solar[FINAL]).dropna()
    groups: dict[str, Any] = {}
    for name, g in solar.groupby("group"):
        finals = [float(v) for v in g[FINAL].dropna()]
        at_l1 = sum(
            1
            for tid, f in zip(g["Tender ID"], g[FINAL], strict=True)
            if pd.notna(f) and abs(float(f) - l1.get(tid, -1)) < 1e-9
        )
        groups[str(name)] = {
            "tenders": sorted(g["Tender ID"].unique().tolist()),
            "wins": int((g["Successful?"].astype(str).str.lower() == "yes").sum()),
            "at_l1": int(at_l1),
            "quoted_mw": [float(v) for v in g["Quoted capacity (MW)"].dropna()],
            "final_tariffs": finals,
            "opening_tariffs": [float(v) for v in g[OPENING].dropna()],
            "names": sorted(g[name_col].unique().tolist()),
        }
    return {
        "tenders": len(solar_tenders),
        "l1_tariffs": l1,
        "median_cut": float(cuts.median()) if len(cuts) else 0.0,
        "groups": groups,
    }
