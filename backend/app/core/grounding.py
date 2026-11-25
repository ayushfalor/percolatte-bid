"""Phase 5: the Copilot may only state numbers that came from a tool. Contract only."""

from __future__ import annotations

from typing import Any


def ungrounded_numbers(answer: str, tool_outputs: list[Any], tolerance: float = 0.005) -> list[str]:
    """Numbers in the answer that no tool output supports (after rounding). Empty list = safe to show."""
    raise NotImplementedError("Phase 5: Copilot not built yet")
