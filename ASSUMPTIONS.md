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

