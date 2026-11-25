#!/usr/bin/env python3
"""The toast's one truth: a small JSON document, written atomically.

A probe updates the file or POSTs to the loopback server; the native window polls this
manager. The window never invents a line: an empty state renders the idle copy, and a
refusal keeps its code and the path it searched.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import threading

SCHEMA = "popit.agent-toast/1"
MAX_LINES = 8
TONES = ("idle", "working", "ok", "refused")
STATUS_WORDS = {
    "idle": "idle",
    "working": "working",
    "ok": "ok",
    "refused": "refused",
}


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def stamp(moment: datetime.datetime | None = None) -> str:
    return (moment or now()).astimezone().strftime("%H:%M:%S")


def default_state() -> dict:
    return {
        "schema": SCHEMA,
        "revision": 0,
        "kicker": "CUA PROBE",
        "title": "Agent chat",
        "status": "idle",
        "tone": "idle",
        "lines": [],
        "source": "popit_apps/agent_toast",
        "updated": now().replace(microsecond=0).isoformat(),
        "pinned": True,
    }


class Refused(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _one_line(value: object, limit: int = 220) -> str:
    text = " ".join(str(value if value is not None else "").split())
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def normalize(raw: object) -> dict:
    """Accept a partial patch and return a complete, safe document."""
    if not isinstance(raw, dict):
        raise Refused("state-not-object", "the update must be a JSON object")
    state = default_state()
    if raw.get("schema") not in (None, SCHEMA):
        raise Refused("schema-mismatch", f"expected {SCHEMA}")
    state["revision"] = int(raw.get("revision") or 0)
    state["kicker"] = _one_line(raw.get("kicker", state["kicker"]), 32) or "CUA PROBE"
    state["title"] = _one_line(raw.get("title", state["title"]), 64) or "Agent chat"
    tone = str(raw.get("tone") or raw.get("status") or "idle").lower()
    if tone not in TONES:
        raise Refused("unknown-tone", f"{tone!r} is not one of {', '.join(TONES)}")
    state["tone"] = tone
    state["status"] = _one_line(raw.get("status") or STATUS_WORDS[tone], 32)
    state["source"] = _one_line(raw.get("source", state["source"]), 120)
    state["updated"] = _one_line(raw.get("updated") or state["updated"], 40)
    state["pinned"] = bool(raw.get("pinned", True))
    lines = raw.get("lines") or []
    if not isinstance(lines, list):
        raise Refused("lines-not-list", "lines must be an array")
    clean = []
    for item in lines[-MAX_LINES:]:
        if isinstance(item, str):
            clean.append({"at": "", "text": _one_line(item), "tone": "idle"})
            continue
        if not isinstance(item, dict):
            raise Refused("line-not-object", "each line is a string or an object")
        line_tone = str(item.get("tone") or "idle").lower()
        if line_tone not in TONES:
            line_tone = "idle"
        text = _one_line(item.get("text") or item.get("detail") or "")
        if not text:
            continue
        clean.append({
            "at": _one_line(item.get("at") or "", 12),
            "text": text,
            "tone": line_tone,
        })
    state["lines"] = clean
    return state


class ToastState:
    def __init__(self, path: pathlib.Path) -> None:
        self.path = pathlib.Path(path)
        self._lock = threading.RLock()
        self._state = default_state()
        self._mtime = 0.0
        if self.path.exists():
            try:
                self._state = normalize(json.loads(self.path.read_text(encoding="utf-8")))
                self._mtime = self.path.stat().st_mtime
            except Exception:
                self._state = default_state()
        self.write(self._state, bump=False)

    def write(self, state: dict, *, bump: bool = True) -> dict:
        with self._lock:
            document = normalize(state)
            if bump:
                document["revision"] = int(self._state.get("revision", 0)) + 1
            document["updated"] = now().replace(microsecond=0).isoformat()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
            os.replace(temp, self.path)
            self._state = document
            self._mtime = self.path.stat().st_mtime
            return dict(document)

    def current(self) -> dict:
        with self._lock:
            try:
                mtime = self.path.stat().st_mtime
            except OSError:
                mtime = 0.0
            if mtime > self._mtime:
                try:
                    self._state = normalize(json.loads(self.path.read_text(encoding="utf-8")))
                    self._mtime = mtime
                except Exception:
                    pass
            return dict(self._state)

    def update(self, patch: dict) -> dict:
        with self._lock:
            current = dict(self._state)
            merged = dict(current)
            for key in ("kicker", "title", "status", "tone", "source", "pinned"):
                if key in patch:
                    merged[key] = patch[key]
            lines = list(current.get("lines") or [])
            if "lines" in patch:
                lines = list(patch["lines"] or [])[-MAX_LINES:]
            if patch.get("line"):
                item = patch["line"]
                if isinstance(item, str):
                    item = {"text": item, "tone": patch.get("tone", "idle")}
                lines = (lines + [dict(item, at=item.get("at") or stamp())])[-MAX_LINES:]
            merged["lines"] = lines
            return self.write(merged)

    def probe(self, name: str, outcome: str, detail: str = "",
              tone: str = "working") -> dict:
        name = _one_line(name, 40) or "probe"
        outcome = _one_line(outcome, 40) or "running"
        text = name + " · " + outcome + ((" — " + _one_line(detail)) if detail else "")
        return self.update({
            "kicker": "CUA PROBE",
            "status": outcome,
            "tone": tone,
            "line": {"text": text, "tone": tone, "at": stamp()},
        })
