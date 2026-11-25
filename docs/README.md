# Docs

| Folder | What is in it | Read it when |
|---|---|---|
| `problem/` | Requirements and where each is met, domain primer, tender facts, sample data | You need to know what was asked or what a term means |
| `solution/` | The design (`SOLUTION.md`), decision log, data extraction diagram | You are building or explaining how it works |
| `phases/` | The current phase (`status.json`), which gates the evals | You want to know which phase's tests are mandatory |
| `product/` | Why a developer would pay, pricing (draft) | Writing the README product page, the call |
| `EXPLAINED.md` | The solution and the evals in simple English | First read, or before the call |
| `RUNBOOK.md` | Running, checking and fixing the app | Something does not start |

Reading order for a reviewer: `../README.md`, `EXPLAINED.md`, `solution/SOLUTION.md`, `solution/decisions.md`.

Raw notes (call notes, chat exports) go in `/notes`, which git ignores, as do the phase plan and
the per-phase docs. Only distilled, checked content belongs here.
