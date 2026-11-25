#!/usr/bin/env python3
"""The native face of the toast: a pinned Tk window in the Popit pinned-app register.

The reference is the CUA machine's pinned Popit application: near-black ground, one warm
gold hairline, uppercase mono section ink, compact stat row, and a square pin/close pair.
The window reads `ToastState` on a timer and redraws only when the revision changes.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

GROUND = "#0C0E0C"
PANEL = "#11140F"
RAISED = "#171B14"
EDGE = "#5A4720"
HAIRLINE = "#2C2A20"
INK = "#F0E4C8"
BODY = "#C9C4B4"
GOLD = "#D8B45A"
DIM = "#7E796A"
GREEN = "#93C99B"
ROSE = "#D8786C"
TONE_COLOR = {"idle": DIM, "working": GOLD, "ok": GREEN, "refused": ROSE}
WIDTH = 404


def _spaced(text: str) -> str:
    return " ".join(text.upper())


class ToastWindow:
    def __init__(self, manager, *, start_hidden: bool = False) -> None:
        self.manager = manager
        self.revision = -1
        self.moved = False
        self.hidden = start_hidden
        self.root = tk.Tk()
        self.root.title("Agent toast")
        self.root.overrideredirect(True)
        try:
            self.root.attributes("-topmost", True)
            self.root.attributes("-alpha", 0.98)
        except tk.TclError:
            pass
        self.root.configure(bg=EDGE)
        self._build()
        self.root.bind("<Control-q>", lambda _e: self.root.destroy())
        self.root.after(120, self.poll)
        if start_hidden:
            self.root.withdraw()

    # -- construction ---------------------------------------------------------
    def _build(self) -> None:
        self.mono = tkfont.Font(family="Consolas", size=9)
        self.mono_bold = tkfont.Font(family="Consolas", size=9, weight="bold")
        self.mono_small = tkfont.Font(family="Consolas", size=8)
        self.head_font = tkfont.Font(family="Consolas", size=12, weight="bold")

        self.frame = tk.Frame(self.root, bg=GROUND, highlightbackground=EDGE,
                              highlightthickness=1, bd=0)
        self.frame.pack(fill="both", expand=True)

        # Title bar: the pinned frame's own header, not an OS chrome.
        self.bar = tk.Frame(self.frame, bg=GROUND, padx=10, pady=0, height=28)
        self.bar.pack(fill="x")
        self.bar.pack_propagate(False)
        self.mark = tk.Label(self.bar, text="◆", bg=GROUND, fg=GOLD,
                             font=self.mono_small)
        self.mark.pack(side="left", padx=(0, 6))
        self.app_name = tk.Label(self.bar, text="A G E N T", bg=GROUND, fg=GOLD,
                                 font=self.head_font)
        self.app_name.pack(side="left")
        self.close_btn = tk.Label(self.bar, text="×", bg=GROUND, fg=DIM,
                                  font=self.mono_bold, cursor="hand2", padx=5)
        self.close_btn.pack(side="right")
        self.pin_btn = tk.Label(self.bar, text="⌖", bg=GROUND, fg=GOLD,
                                font=self.mono_bold, cursor="hand2", padx=5)
        self.pin_btn.pack(side="right")
        self.rule = tk.Frame(self.frame, bg=EDGE, height=1)
        self.rule.pack(fill="x")

        # Stat strip, the pinned app's compact reading row.
        self.stats = tk.Frame(self.frame, bg=PANEL, padx=10, pady=6)
        self.stats.pack(fill="x")
        self.kicker = tk.Label(self.stats, text="CUA PROBE", bg=PANEL, fg=GOLD,
                               font=self.mono_bold, anchor="w")
        self.kicker.pack(side="left")
        self.dot = tk.Label(self.stats, text="●", bg=PANEL, fg=DIM, font=self.mono_small)
        self.dot.pack(side="right")
        self.status = tk.Label(self.stats, text="idle", bg=PANEL, fg=DIM,
                               font=self.mono_small, anchor="e")
        self.status.pack(side="right", padx=(0, 4))
        self.count = tk.Label(self.stats, text="0 probes", bg=PANEL, fg=DIM,
                              font=self.mono_small, anchor="e")
        self.count.pack(side="right", padx=(0, 12))

        self.body = tk.Frame(self.frame, bg=GROUND, padx=10, pady=8)
        self.body.pack(fill="both", expand=True)
        self.title = tk.Label(self.body, text="Agent chat", bg=GROUND, fg=INK,
                              font=self.mono_bold, anchor="w", justify="left",
                              wraplength=WIDTH - 28)
        self.title.pack(fill="x")
        self.subrule = tk.Frame(self.body, bg=HAIRLINE, height=1)
        self.subrule.pack(fill="x", pady=(6, 6))

        self.lines = tk.Frame(self.body, bg=GROUND)
        self.lines.pack(fill="both", expand=True)
        self.footer = tk.Label(self.body, text="", bg=GROUND, fg=DIM,
                               font=self.mono_small, anchor="w")
        self.footer.pack(fill="x", pady=(7, 0))

        for widget in (self.bar, self.app_name, self.mark, self.title):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
        self.close_btn.bind("<Button-1>", lambda _e: self.hide())
        self.pin_btn.bind("<Button-1>", lambda _e: self.toggle_pin())
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

    # -- window behaviour -----------------------------------------------------
    def _drag_start(self, event) -> None:
        self._drag = (event.x_root - self.root.winfo_x(),
                      event.y_root - self.root.winfo_y())

    def _drag_move(self, event) -> None:
        if not hasattr(self, "_drag"):
            return
        self.moved = True
        x = event.x_root - self._drag[0]
        y = event.y_root - self._drag[1]
        self.root.geometry(f"+{x}+{y}")

    def toggle_pin(self) -> None:
        pinned = not bool(self.root.attributes("-topmost"))
        self.root.attributes("-topmost", pinned)
        self.pin_btn.configure(fg=GOLD if pinned else DIM)
        self.manager.update({"pinned": pinned})

    def hide(self) -> None:
        self.hidden = True
        self.root.withdraw()

    def show(self) -> None:
        self.hidden = False
        self.root.deiconify()
        self.root.attributes("-topmost", True)

    def place_default(self) -> None:
        self.root.update_idletasks()
        width = max(WIDTH, self.root.winfo_reqwidth())
        height = self.root.winfo_reqheight()
        x = max(0, self.root.winfo_screenwidth() - width - 24)
        y = 24
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    # -- render ---------------------------------------------------------------
    def poll(self) -> None:
        try:
            state = self.manager.current()
            if int(state.get("revision", 0)) != self.revision:
                self.render(state)
        finally:
            self.root.after(700, self.poll)

    def render(self, state: dict) -> None:
        self.revision = int(state.get("revision", 0))
        tone = state.get("tone") if state.get("tone") in TONE_COLOR else "idle"
        color = TONE_COLOR[tone]
        entries = state.get("lines") or []
        self.kicker.configure(text=_spaced(state.get("kicker") or "CUA PROBE"))
        self.title.configure(text=state.get("title") or "Agent chat")
        self.status.configure(text=(state.get("status") or tone).upper(), fg=color)
        self.dot.configure(fg=color)
        self.count.configure(text=f"{len(entries)} probe{'s' if len(entries) != 1 else ''}")
        self.pin_btn.configure(fg=GOLD if state.get("pinned", True) else DIM)
        self.root.attributes("-topmost", bool(state.get("pinned", True)))
        for child in self.lines.winfo_children():
            child.destroy()
        if not entries:
            empty = tk.Label(self.lines, text="no probe has reported yet", bg=GROUND,
                             fg=DIM, font=self.mono_small, anchor="w")
            empty.pack(fill="x", pady=2)
        for entry in entries[-6:]:
            row = tk.Frame(self.lines, bg=GROUND)
            row.pack(fill="x", pady=2)
            line_tone = entry.get("tone") if entry.get("tone") in TONE_COLOR else "idle"
            mark = tk.Label(row, text="›", bg=GROUND, fg=TONE_COLOR[line_tone],
                            font=self.mono_bold)
            mark.pack(side="left", anchor="n")
            text = tk.Label(row, text=entry.get("text") or "", bg=GROUND, fg=BODY,
                            font=self.mono_small, anchor="w", justify="left",
                            wraplength=WIDTH - 62)
            text.pack(side="left", fill="x", expand=True, padx=(4, 0))
            if entry.get("at"):
                clock = tk.Label(row, text=entry["at"], bg=GROUND, fg=DIM,
                                 font=self.mono_small)
                clock.pack(side="right", padx=(6, 0))
        source = state.get("source") or ""
        updated = (state.get("updated") or "").replace("T", " ")[:19]
        self.footer.configure(text=(source + "  ·  " + updated).strip(" ·"))
        if not self.moved:
            self.place_default()
        else:
            self.root.update_idletasks()

    def rendered(self) -> dict:
        self.root.update_idletasks()
        line_texts = []
        for row in self.lines.winfo_children():
            labels = [child for child in row.winfo_children()
                      if isinstance(child, tk.Label) and child.cget("text") != "›"]
            if labels:
                line_texts.append(" ".join(str(label.cget("text")) for label in labels))
        return {
            "title": str(self.title.cget("text")),
            "kicker": str(self.kicker.cget("text")),
            "status": str(self.status.cget("text")),
            "lines": line_texts,
            "geometry": self.root.geometry(),
            "topmost": bool(self.root.attributes("-topmost")),
            "visible": bool(self.root.winfo_viewable()),
        }

    def pump(self) -> None:
        self.root.update()

    def run(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass
