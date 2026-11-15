"""Refuse an input that was picked by hand instead of derived and recorded.

Three times in one session a pipeline input was chosen by an invented heuristic
inside a command line: "the largest body dmx", "item_stand_idle as the fallback",
"the best-moving tengu clip".  Each one was a guess about a set nobody had
measured, and the first two were guesses about a set that was **incomplete** (28
of Tengu's 188 clips had been decompiled to DMX).

A choice is admissible when it is (a) made over the complete candidate set, (b)
by a named rule, (c) written to a receipt that lists every candidate and the
metric, and (d) the consumer names that receipt.  `--clips` without `--selection`
is the refusal.

Refusal codes:

    hand-picked-input        a consumer was given a chosen input with no selection receipt
    selection-incomplete     the receipt's candidate set is smaller than the shipped set
    selection-rule-missing   the receipt names no rule or no metric
"""
from __future__ import annotations

import json
from pathlib import Path


class Refused(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def write_selection(path: Path, *, role: str, rule: str, metric: str, candidates: list[dict], chosen, extra: dict | None = None) -> dict:
    payload = {
        "role": role,
        "rule": rule,
        "metric": metric,
        "candidates": len(candidates),
        "chosen": chosen if isinstance(chosen, list) else [chosen],
        "all_candidates": candidates,
    }
    if extra:
        payload.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def load_selection(path: Path, *, shipped: int | None = None) -> dict:
    """Read a selection receipt, refusing one that cannot justify its choice."""
    if not path.is_file():
        raise Refused("hand-picked-input", f"no selection receipt at {path}; a chosen input must be derived and recorded")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("rule") or not payload.get("metric"):
        raise Refused("selection-rule-missing", f"{path.name} names no rule or no metric")
    if shipped is not None and int(payload.get("candidates") or 0) < shipped:
        raise Refused(
            "selection-incomplete",
            f"{path.name} scored {payload.get('candidates')} candidates against {shipped} shipped clips; "
            "a choice made over a partial set is a guess",
        )
    return payload


def require(path_arg: str | None, *, shipped: int | None = None) -> dict:
    if not path_arg:
        raise Refused(
            "hand-picked-input",
            "this input was passed without --selection; an invented pick is not a measurement",
        )
    return load_selection(Path(path_arg), shipped=shipped)
