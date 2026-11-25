"""Phase 3: rival beliefs as frozen snapshots. Contract only; see evals/test_phase3_rivals.py.

Regimes (each one its own frozen snapshot, so a UI switch never edits beliefs):
  history   rivals bid like the last 13 solar auctions
  almm_40   rivals pass on 40% of the imported-panel saving
  almm_100  rivals pass on all of it
"""

from __future__ import annotations

from typing import Any

from .contracts import RivalSnapshot

REGIMES = {"history": 0.0, "almm_40": 0.4, "almm_100": 1.0}


def build_snapshot(
    history: dict[str, Any],
    regime: str,
    seed: int = 42,
    n_draws: int = 5000,
    dossiers: list[dict[str, Any]] | None = None,
) -> RivalSnapshot:
    raise NotImplementedError("Phase 3: rival model not built yet")


def draws(snapshot: RivalSnapshot) -> Any:
    """The joint draws (participation, MW, opening bid, floor per rival per draw). Read-only."""
    raise NotImplementedError("Phase 3: rival model not built yet")
