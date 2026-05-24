"""
Progress Reporter — streaming sub-step feedback for long operations.

Provides visibility into what's happening during multi-minute runs.
Callbacks fire at each meaningful step so CLI can display progress.
"""
from __future__ import annotations
import sys
import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ProgressEvent:
    phase: str          # e.g. "phenomenon_scan", "kill_first", "paper_write"
    step: str           # e.g. "querying Semantic Scholar", "writing method section"
    detail: str = ""    # optional extra info
    elapsed: float = 0.0


ProgressCallback = Callable[[ProgressEvent], None]


class ProgressReporter:
    """
    Collects progress events and dispatches to registered callbacks.
    Default callback prints to stderr with ANSI formatting.
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._callbacks: list[ProgressCallback] = []
        self._start = time.time()
        self._phase_start = time.time()
        self._current_phase = ""
        self._step_count = 0

        # Register default stderr callback
        self._callbacks.append(self._default_callback)

    def add_callback(self, cb: ProgressCallback):
        self._callbacks.append(cb)

    def phase(self, name: str, detail: str = ""):
        """Start a new pipeline phase."""
        self._current_phase = name
        self._phase_start = time.time()
        self._step_count = 0
        self._emit(name, name.replace("_", " ").title(), detail)

    def step(self, description: str, detail: str = ""):
        """Report a sub-step within the current phase."""
        self._step_count += 1
        self._emit(self._current_phase, description, detail)

    def done(self, summary: str = ""):
        """Mark current phase as complete."""
        elapsed = time.time() - self._phase_start
        self._emit(self._current_phase, f"✓ done ({elapsed:.1f}s)", summary)

    def _emit(self, phase: str, step: str, detail: str):
        event = ProgressEvent(
            phase=phase,
            step=step,
            detail=detail,
            elapsed=time.time() - self._start,
        )
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def _default_callback(self, event: ProgressEvent):
        DIM = "\033[2m"; CYAN = "\033[36m"; GREEN = "\033[32m"; R = "\033[0m"
        if event.step.startswith("✓"):
            line = f"\r  {GREEN}{event.step}{R}"
        else:
            line = f"\r  {CYAN}·{R} {DIM}{event.phase}{R} — {event.step}"
        if event.detail and self.verbose:
            line += f"  {DIM}{event.detail[:60]}{R}"
        sys.stderr.write(line + "  \n" if event.step.startswith("✓") else line + "  ")
        sys.stderr.flush()


# Global singleton — phases import and use this
_reporter: ProgressReporter | None = None


def get_reporter() -> ProgressReporter:
    global _reporter
    if _reporter is None:
        _reporter = ProgressReporter()
    return _reporter


def set_reporter(reporter: ProgressReporter):
    global _reporter
    _reporter = reporter
