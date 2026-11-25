# Domain primer (plain English)

Everything here is checked against the RfS; clause numbers in brackets. Use these words the same
way everywhere in code, docs and UI.

## The deal

- **SECI**: a government company that runs the auction, buys the power from the winner and sells it on to the buyer.
- **RfS (Request for Selection)**: the tender document, our rulebook. 128 PDF pages.
- **PPA / PSA**: the 25-year contract between the developer and SECI (PPA), and SECI's matching contract with the buyer (PSA).
- **Buyer**: an export unit in Odisha making green hydrogen or ammonia; power is drawn at Paradeep (7.5).
- **ISTS**: the national transmission grid. The plant can be anywhere in India; the buyer is in Odisha.
- **SEZ / EOU**: special export zones and units. This is why imported panels are allowed here (3.3, 35.2).
- **ALMM**: the government's approved list of (mostly Indian) panel makers, normally mandatory. Exempt in this tender.

## The plant and the money

- **MW vs MWp**: grid capacity (AC) vs panel capacity (DC). The model uses 1.4 MWp per MW.
- **CUF**: how much the plant produces vs running flat out all year. Measured on 8,766 hours (43.9). Must declare at least 25% and stay within +10% / -15% of it (8.1).
- **MU**: million units = million kWh. Revenue (INR crore) = MU x tariff / 10.
- **Equity IRR**: the annual return on the developer's own money. The board's hurdle in the model is 14%.
- **DSCR**: cash available to pay the bank divided by what is due that year. Banks want it above about 1.2x (assumed).
- **Breakeven tariff**: the tariff that gives exactly 14% equity IRR. The sample model as received: INR 2.6039/kWh.

## The money you put up

- **EMD**: bid security, INR 8 lakh per MW (16.1). Lost if you withdraw or refuse an award you had to take.
- **PBG**: performance security, INR 20 lakh per MW (17.1). Lost (pro rata) if supply starts late.
- **Success charges**: INR 1 lakh per MW + GST, paid to SECI if you win (18.1).

## The auction

- **Two envelopes**: first eligibility, then a sealed tariff (the "entry bid").
- **e-RA**: the live reverse auction. Prices only go down, at least 1 paisa a step. 30 minutes, extended by 8 minutes whenever someone's zone changes (40.4).
- **L1**: the lowest tariff. **The 2% band**: only bids within L1 + 2% can win, cut to two decimals (41.2). If L1 is INR 2.36, nobody above INR 2.40 wins.
- **SE (eligible capacity)**: min(700 MW, 0.8 x total MW bid) (40.2). Below 875 MW of total bids, less than 700 MW is awarded.
- **H1 knockout**: if 0.8 x total bids is above 700 MW, the single highest sealed bid is dropped before the live auction, unless that would leave fewer than 3 bidders or drop capacity below 700 (40.2). The 80% cut and the knockout never happen together.
- **Zones**: green (full award if it ended now), orange (partial), red (nothing).
- **Partial awards**: last winner gets what is left, in 10 MW steps, minimum 50 MW. Under half your bid you may refuse; half or more you must accept or lose the EMD (41.4, 41.5).

## Corrections to earlier notes

- The band for an L1 of INR 2.36 is INR 2.40, not 2.41 (tariffs are cut, not rounded).
- The 80% rule applies whenever total bids are under 875 MW, not only when "undersubscribed".
- History cannot be replayed as is: past solar auctions priced ALMM-bound panels; this one allows imports.
