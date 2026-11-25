# The three sample files

## bid_model.xlsx (the developer's model)

200 MW solar, 8 sheets, 558 formulas. Equity IRR 14.21% at INR 2.62/kWh; breakeven for 14% is INR 2.6039.

| What is planted | Where | Effect |
|---|---|---|
| Insurance typed in but never used (comment says "to be wired") | Inputs!C28 | INR 2.16 Cr a year missing; +4 paise on breakeven |
| Year-6 O&M typed over a formula | CashFlow!I10 | +INR 2.2 Cr EBITDA in year 6 |
| Project IRR range stops at year 24 | Returns!C9 | Shows 11.34% instead of 11.44% |
| "PPA term" input not used by any formula | Inputs!C13 | Changing it does nothing |
| Stale goal-seek note ("last run gave 2.57") | Returns!C16 | At 2.57 the IRR is 13.56%, not 14% |
| Interest stored as 9.25 and divided by 100 | Inputs!C21 | Easy to break with 0.0925 |
| Hidden old tab with different numbers | Inputs_old_v2 | 250 MW, INR 2.71, CUF 29% |
| Modules priced as ALMM-bound | Capex!D5, H5 | Tender exempts ALMM |
| 8,760 hours instead of 8,766 | Inputs!C11 | Tiny |

## tender.pdf (the RfS)

128 pages, text layer on every page (no scans). Binding content: bid information sheet, Sections 1
to 6, Annexure-B. The rest is blank forms and portal instructions. See `04-tender-facts.md`.

## auction_history.xlsx (mock results, 40 tenders, 316 bid rows)

| Data trap | Fix |
|---|---|
| One exact duplicate bid row (MOCK-2023-001) | Dropped |
| MOCK-2023-008 in paise/kWh (254 = INR 2.54) | Divided by 100 |
| Three date formats | Parsed |
| 37 bidder names for 20 groups (SPVs, spelling) | Grouped |
| Undersubscribed tenders awarded 100% of bids, unlike this RfS's 80% rule | Use this RfS's rules, not history's |

Solar ISTS: 13 tenders, L1 between INR 2.49 and 2.57 except one outlier at INR 2.36. Median cut from
sealed bid to final price: 8 paise.
