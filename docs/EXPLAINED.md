# The solution and the evals, in simple English

## The solution as a story

A bid manager has three things: their Excel model, a 128-page tender, and a spreadsheet of past
auctions. They need one answer: what price should we bid?

1. **Reader** opens all three. It maps every formula in the model, reads every page of the tender,
   and cleans the auction history (fixes paise typed as rupees, removes a duplicate row, groups 37
   bidder names into 20 real companies).
2. **Auditor** checks the model against itself and against the tender. Example: the insurance
   cost is typed in but never used, so the model looks 4 paise cheaper than it really is.
3. **Scout** looks up real rivals on the web. **Rival model** turns history and those facts into
   beliefs about each rival: how likely they are to show up and how low they would go, with reasons.
   These beliefs are frozen so they cannot shift quietly.
4. **Engine** works out our profit at every price from their own model, then plays the auction
   thousands of times under the exact tender rules to get our chance of winning at every price.
   It recommends three numbers: the sealed entry bid, the target range, and the price we never go below.
5. **Copilot** answers "what if" questions by running the same tools, never by guessing numbers.

Everything shows its source: a cell in their file, a page and quote from the tender, or a line in
ASSUMPTIONS.md.

## The evals in simple English

An eval is an automatic check that the app gives the right answer. We run them on every change.

- **Known answers.** For the sample model we know the right numbers (equity IRR 14.21% at INR 2.62,
  breakeven INR 2.6039). The evals check we get exactly those.
- **The tender's own examples.** The RfS includes worked examples of who wins. Our auction rules must
  reproduce them exactly.
- **A workbook we have never seen.** We generate a wind model with a different layout, no named
  ranges and no saved values, and work out the right answers separately in plain Python. Reviewers
  will test an unseen workbook; we do it first.
- **Proof from the tender.** For 24 key facts we store the value, the page and an exact quote; the
  check confirms the quote really is on that page.
- **From the outside.** Some evals start the whole app in Docker and call it over HTTP, the way a
  reviewer or their eval suite would.
- **Phase gates.** Each phase has its own evals, written before the code. Until the phase is done
  they are allowed to fail; once we close the phase they must always pass.
- **Docs check.** A phase is not done until its doc explains what we built and answers at least six
  questions a reviewer might ask.

## How a phase works

1. Check that the phase's evals match its scope; fix the evals first.
2. Build in small steps, running the fast evals after each.
3. Run everything. Close the phase: its evals become mandatory and its doc gets filled in.
4. Look ahead at the next phase's evals.
5. Push. CI runs everything on a clean machine. Merge only when it is green.
