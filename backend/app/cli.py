"""Command line access to the deterministic tools, no database needed.

python -m app.cli structure path/to/model.xlsx
python -m app.cli evaluate  path/to/model.xlsx 'Returns!C8' --set Tariff=2.5
python -m app.cli goal-seek path/to/model.xlsx --variable Tariff --target 'Returns!C8' --value 0.14
python -m app.cli parity    path/to/model.xlsx
python -m app.cli tender    path/to/tender.pdf
python -m app.cli history   path/to/auction_history.xlsx
"""

from __future__ import annotations

import argparse
import json
import sys


def _out(obj) -> None:
    json.dump(obj, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bidbench")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("structure", "parity", "tender", "history"):
        sub.add_parser(name).add_argument("path")
    ev = sub.add_parser("evaluate")
    ev.add_argument("path")
    ev.add_argument("outputs", nargs="+")
    ev.add_argument("--set", action="append", default=[], help="CELL=VALUE, repeatable")
    gs = sub.add_parser("goal-seek")
    gs.add_argument("path")
    gs.add_argument("--variable", required=True)
    gs.add_argument("--target", required=True)
    gs.add_argument("--value", type=float, required=True)
    args = p.parse_args(argv)

    if args.cmd == "structure":
        from .core.workbook_reader import read_structure

        _out(read_structure(args.path))
    elif args.cmd == "tender":
        from .core.tender_reader import read_pages

        r = read_pages(args.path)
        r["page_texts"] = [{k: v for k, v in pg.items() if k != "text"} for pg in r["page_texts"]]
        _out(r)
    elif args.cmd == "history":
        from .core.history_reader import read_history

        _out(read_history(args.path))
    else:
        from .core.excel_engine import WorkbookEngine

        eng = WorkbookEngine(args.path)
        if args.cmd == "parity":
            _out(eng.parity().as_dict())
        elif args.cmd == "evaluate":
            overrides = {}
            for item in args.set:
                key, _, val = item.partition("=")
                try:
                    overrides[key] = float(val)
                except ValueError:
                    overrides[key] = val
            _out(eng.evaluate(overrides, args.outputs))
        elif args.cmd == "goal-seek":
            _out(eng.goal_seek(args.variable, args.target, args.value).__dict__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
