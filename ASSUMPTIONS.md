# Assumptions

Every number the app uses that does not come straight from the tender or the bid model is listed
here. Source types: **Tender** (RfS clause), **Model** (bid_model.xlsx), **History**
(auction_history.xlsx), **Assumed** (our call, mock data allowed by the brief).

| ID | Assumption | Value | Source | Used by | Change it in |
|---|---|---|---|---|---|
| A-01 | Board hurdle for equity IRR | 14% | Model (Returns!C11) | Engine | run params `hurdle` |
| A-02 | Lender DSCR covenant | 1.20x minimum | Assumed | Engine (walk-away floor) | run params |
| A-03 | Imported (non-ALMM) module price | INR 10/Wp | Assumed mock quote; ALMM exemption is Tender §3.3, §35.2 | Auditor, Engine | scenario overrides |
| A-04 | GST on supplies to an SEZ unit is zero-rated | 0% on EPC | Assumed, needs tax advice | Auditor (lever, off by default) | scenario overrides |
| A-05 | Share of the import saving rivals pass into their bids | 40% to 100% | Assumed | Rival model | rival run params |
| A-06 | Rival behaviour types come from history groups; real company names are illustrative labels | n/a | History + Assumed | Rival model | rival run params |
| A-07 | Fewer bidders than vanilla ISTS tenders (SEZ/EOU status and a connectivity grant are required) | participation odds per rival | Assumed | Rival model | rival run params |
| A-08 | Each bidder is one block of capacity; a partial award is rounded down to 10 MW | n/a | Simplification of Tender §41.3 | Auction rules | `core/auction_rules.py` |
| A-09 | Draw of lots for exact ties is replaced by bidder name order, so runs are reproducible | n/a | Simplification of Tender §41.2.d | Auction rules | `core/auction_rules.py` |
| A-10 | Auto-extension follows §40.4 (zone change), not Annexure-A (any bid in the last 8 minutes) | n/a | Tender conflict, our reading | Replay | Engine |
| A-11 | Any tariff above 20 in history is paise/kWh | divide by 100 | History (MOCK-2023-008 remark) | Reader | `core/history_reader.py` |
| A-12 | Bidder names grouped by their distinctive word (SPVs and spelling variants) | 37 names to 20 groups | History | Reader, Rival model | `core/history_reader.py` |
| A-13 | Monte Carlo seed | 42 | Assumed | Engine | `SIM_SEED` |
| A-14 | Printed page number = PDF page minus 1 in this RfS | offset 1 | Tender | Reader (citations) | detected per file |
| A-15 | Rival beliefs come in three frozen regimes: like history, 40% pass-through, 100% pass-through | n/a | Assumed | Rival model, Engine | `core/rival_model.py` REGIMES |
| A-16 | Each INR 1/Wp of module price moves the breakeven by about INR 0.08/kWh | derived | Model (14.5 to 10/Wp moves it 37 paise) | Rival model | recomputed from the workbook |
| A-17 | Price ladder covers INR 2.00 to 2.80, every paisa | n/a | Assumed (D-007) | Engine | `core/simulate.py` defaults |
| A-18 | Entry bid must keep the chance of being knocked out as H1 at or below 5% | 5% | Assumed | Engine | `recommend(max_h1_risk=...)` |
| A-19 | Real company names on rivals are illustrative labels, not real bid data | n/a | Assumed | Rival model, UI | anonymize toggle |
| A-20 | The tornado moves each input by 10% of its own value, either way | ±10% | Assumed | Auditor (tornado) | `core/audit.py` SWING |
| A-21 | A tender mismatch is "high" when it is worth at least 1 paisa, otherwise "medium" | INR 0.01/kWh | Assumed | Auditor (severity) | `core/checks.py` BIG_IMPACT |
| A-22 | A note is stale when the number it records is within 20% of the live breakeven but more than half a paisa off it | 20% band, 0.005 tolerance | Assumed | Auditor (stale notes) | `core/checks.py` STALE_BAND, STALE_TOLERANCE |
| A-23 | The target range is every price within 90% of the best expected value above the walk-away | 90% | Assumed | Engine (recommend) | `core/simulate.py` TARGET_SHARE |
| A-24 | The typical cut from sealed bid to final price, used to place the entry bid above the floor | 8 paise | History (median across solar ISTS bids) | Engine (recommend) | `core/simulate.py` TYPICAL_CUT |
| A-25 | Live auction: a rival's last bid is the most it will end at, and a typed L1 means some rival ends at or under it; the rival draws are filtered to the auctions that agree, as long as at least 200 of 5,000 do | 200 of 5,000 | Assumed (D-013) | Live Auction | `core/live_auction.py` MIN_SURVIVORS |
| A-26 | Live auction, only when "assume paces hold" is ticked: a cutting rival keeps its paise-per-minute pace to the close, never more than 30 paise past its last bid | 30 paise cap | Assumed | Live Auction | `core/live_auction.py` MAX_PROJECTED_CUT |
| A-27 | A key pasted on the Setup screen is kept in the app's local database as is; the database publishes no port and the repo never sees it | n/a | Assumed (D-012) | Setup, Copilot, Reader | `app/keys.py` |
