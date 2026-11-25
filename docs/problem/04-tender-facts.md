# Tender facts (golden set)

The facts below come from RfS No. SECI/C&P/IPP/15/0009/26-27 (C&I-1). Every quote is checked by the eval suite to appear on the cited page. Printed page = PDF page minus 1.

Source of truth: `backend/evals/expected/tender_facts.json`. Edit that file, not this table, then regenerate.

| Field | Value | Unit | Clause | PDF page | Printed page |
|---|---|---|---|---|---|
| emd_per_mw | 800000 | INR/MW | 16.1 | 21 | 20 |
| pbg_per_mw | 2000000 | INR/MW | 17.1 | 23 | 22 |
| success_charge_per_mw | 100000 | INR/MW plus taxes | 18.1 | 25 | 24 |
| min_bid_mw | 50 | MW | 5.1 | 9 | 8 |
| max_bid_mw | 700 | MW | 5.1 | 9 | 8 |
| capacity_step_mw | 10 | MW | 5.1 | 9 | 8 |
| min_declared_cuf | 0.25 | fraction | 8.1 | 13 | 12 |
| cuf_band | +10% / -15% | of declared CUF | 8.1 | 13 | 12 |
| cuf_hours_per_year | 8766 | hours | 43.9 | 56 | 55 |
| scsd_months_from_ppa | 24 | months | 9.2 | 17 | 16 |
| financial_closure_before_scsd_months | 6 | months | 21.1 | 29 | 28 |
| ppa_term_years | 25 | years from SCSD | 20.2 | 27 | 26 |
| band_over_l1 | 0.02 | fraction of L1 | 41.2 | 52 | 51 |
| se_cap_mw | 700 | MW | 40.2 | 50 | 49 |
| min_decrement | 0.01 | INR/kWh | 40.4 | 51 | 50 |
| era_initial_minutes | 30 | minutes | 40.4 | 52 | 51 |
| era_extension_minutes | 8 | minutes | 40.4 | 52 | 51 |
| partial_refusal_threshold | 0.5 | of quoted capacity | 41.4 | 53 | 52 |
| almm_exempt | True | flag | 3.3 | 9 | 8 |
| sez_status_loss_not_force_majeure | True | flag | 20.11 | 29 | 28 |
| trading_margin | 0.07 | INR/kWh | 43.64 | 61 | 60 |
| net_worth_per_mw | 8000000 | INR/MW | 36.1 | 45 | 44 |
| drawl_point | Paradeep ISTS Substation | text | 7.5 | 12 | 11 |
| gib_retrofit_rule | True | flag | 15.d | 20 | 19 |

## Quirks that change the bid

- **ALMM exemption (3.3, 35.2).** Projects sit in an SEZ or EOU and supply a green hydrogen buyer, so imported modules are allowed. The sample bid model still prices ALMM List-II modules.
- **SEZ/EOU status is your risk (20.11).** Losing it is not Force Majeure or Change in Law.
- **Connectivity first (7.6).** A final grant of connectivity with a start date on or before 31 Dec 2028 must be submitted with the bid.
- **PPA runs 25 years from the scheduled supply date (20.2).** Delays eat into the 25 years.
- **Bird-diverter rules in Rajasthan and Gujarat (15.d).** Extra cost if the site is there.
- **SECI trading margin INR 0.07/kWh (43.64).** Charged to the buyer, on top of our tariff.

## Inconsistencies inside the RfS

- Auto-extension: Annexure-A says any bid in the last 8 minutes extends the auction; clause 40.4 says only a zone change does. We follow 40.4 (ASSUMPTIONS A-10).
- Annexure-B mentions 10 MW units for part commissioning; clause 9.1 sets a 50 MW minimum.
- Clause 36.10 refers to clauses 38.1 and 38.2; it means 36.1 and 36.2. Clause 34.4 refers to 33.4.
