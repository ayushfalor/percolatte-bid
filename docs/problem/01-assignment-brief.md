# Assignment brief (verbatim)

Source: Percollate take-home brief, as received. Kept verbatim so every decision can point back to it. Keep this repository private and give reviewers access.

## Percollate: Take-Home Assignment

#### **Agentic bid workbench for renewable energy tenders**

### **Context**

Government agencies in India (SECI, NTPC, NHPC) award renewable energy projects through tenders. Developers read a long tender document, build their bid in Excel financial models, and then compete in a live reverse auction on tariff (₹/kWh). Today that's done by hand: long documents, fragile spreadsheets, and a war room on auction day.

You'll build an early slice of an agentic product for a developer's bid team. It's open-ended on purpose: we want to see your product thinking as much as your engineering.

### **What we're giving you**

- **A real tender:** SECI's 700 MW ISTS-connected solar RfS (C&I-1), linked above.

- **Market history:** results from recent SECI auctions (bidders, capacity, tariffs). They're published as PDFs; we'll also share a compiled Excel version.

- **A mock bid model:** bid_model.xlsx, a developer's financial model with capex, CUF, degradation, O&M, debt terms, tariff and equity IRR across several sheets. It's messy the way real workbooks are.

### **What to build, and what we're measuring**

**1. Excel ingestion**
Make sense of the workbooks without assuming a fixed template: sheets, tables, formulas, named ranges, merged headers, hardcoded values, units.
 → *We're measuring how reliable and robust your ingestion pipeline is.* We'll run it on a workbook you haven't seen.

**2. The Excel agent**
The agent should build an understanding of the model: which inputs drive which outputs, which assumptions matter, and what looks wrong. Then it should be able to act on that understanding by running scenarios, finding a breakeven, or explaining a number. Chat can be one way in, but **it shouldn't be the main output.** Show us what the agent understands about the model.
 → *We're measuring the depth of understanding and the knowledge base your agent builds.* We also care about speed and whether the numbers are correct.

**3. Tender context and bid simulation**
Pull out what matters from the RfS (capacity limits, eligibility, auction rules, timelines, penalties, guarantees), combine it with the market history and the bid model, and simulate the auction to recommend a bid range. Show the trade-off between the chance of winning and the return.
 → *We're measuring how much useful context you can extract from a specific tender* and how well you carry it through to the recommendation.

**4. The UI**
 The user is a bid manager: not technical, short on time, and responsible for a large amount of money.
 → *We're measuring how intuitive it is.* Can they trust it and act on it without you there?

### **Constraints**

- **Time:** about 4–6 hours of work. You have 24 hours from when you start, and you can start any time this week.

- **Stack:** Whatever you wish! Bonus points for python backend and typescript frontend

- **AI tools:** use any and however many

- **LLM:** any provider. Tell us what it costs to run.

### **Deliverables**

- A Git repo with setup instructions

- A README covering what you built and why, what you left out, where it breaks, and **one page on how this becomes a product a renewable developer would pay for**

- After you submit, we'll do a 45-minute call to walk through it together and extend it live.
