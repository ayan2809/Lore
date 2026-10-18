"""Logs, timing and cost (plan section 12).

- `log_event(**fields)`: one JSON object per line on stdout (and in a file if LORE_LOG_FILE is set).
- `estimate_cost(model, tokens_in, tokens_out)`: dollars, from the PRICES table below.
- `Timer`: `with Timer() as t: ...; t.ms`.
- `RunMetrics`: counts steps, model calls and tokens during one investigation -> `RunSummary`.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

from lore.models import RunSummary

PRICES: dict[str, tuple[float, float]] = {
    # USD per 1M tokens (input, output incl. thinking), Gemini API paid tier, checked Oct 18 2026
    # at ai.google.dev/gemini-api/docs/pricing. Argon doubles Dec 1 2026, 3.8 Flash Jan 1 2027.
    "gemini-4-argon": (2.00, 10.00),
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-embedding-2": (0.20, 0.0),
}
DEFAULT_PRICE = (2.00, 12.00)  # unknown model: assume the Pro price so cost is never understated


def log_event(**fields: Any) -> None:
    """Write one structured log line. Never raises: logging must not break a request."""
    line = json.dumps({"ts": round(time.time(), 3), **fields}, default=str)
    print(line, file=sys.stdout, flush=True)
    path = os.environ.get("LORE_LOG_FILE")  # e.g. logs/lore.jsonl
    if path:
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = PRICES.get(model, DEFAULT_PRICE)
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


class Timer:
    """Context manager measuring wall-clock milliseconds."""

    def __enter__(self) -> Timer:
        self._start = time.perf_counter()
        self.ms = 0.0
        return self

    def __exit__(self, *exc: object) -> None:
        self.ms = (time.perf_counter() - self._start) * 1000


class RunMetrics:
    """Accumulates the numbers shown in the UI's run summary."""

    def __init__(self, investigation_id: str, replay: bool = False):
        self.investigation_id = investigation_id
        self.replay = replay
        self.steps = 0
        self.model_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost_usd = 0.0
        self.time_to_root_cause_ms: float | None = None
        self._start = time.perf_counter()

    def step(self) -> None:
        """Count one tool call."""
        self.steps += 1

    def model_call(self, model: str, tokens_in: int, tokens_out: int) -> None:
        self.model_calls += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.cost_usd += estimate_cost(model, tokens_in, tokens_out)

    def root_cause_found(self) -> None:
        """Call once, when the Investigator names the root cause (the business metric)."""
        if self.time_to_root_cause_ms is None:
            self.time_to_root_cause_ms = self.elapsed_ms()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000

    def summary(self) -> RunSummary:
        return RunSummary(
            investigation_id=self.investigation_id,
            steps=self.steps,
            model_calls=self.model_calls,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            cost_usd=round(self.cost_usd, 6),
            total_ms=round(self.elapsed_ms(), 1),
            time_to_root_cause_ms=self.time_to_root_cause_ms,
            replay=self.replay,
        )
