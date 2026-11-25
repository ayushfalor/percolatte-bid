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
    }
