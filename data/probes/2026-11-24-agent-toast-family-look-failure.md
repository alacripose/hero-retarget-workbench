# 2026-11-24 — the agent toast was built without the pinned Popit family look

## The failure

I built `popit_apps/agent_toast/` in `deadlock-model-forge` from a guessed copy of the
Openlock **game HUD toast** (`openlock_schemes.css`: ground `#2E2C27`, green accent
`#5FE69E`) and then restyled once from the Archive screenshot. I did not read the
popit-shell repository on `F:` first, even though its README states that it **is** the
pinned family look. The owner had to point me at it.

A screenshot is not the authority. The authority is in the repository:

- `F:\Documents\popit-shell\README.md` — "This repository is also the pinned **family
  look**: the visual example every family application is measured against."
- `F:\Documents\popit-shell\docs\family-look.md` — one corner for every surface, body
  clipped at 0.5 px, frame stroked at 1 px from 1.5 px, and a named refusal for every
  departure.
- `F:\Documents\popit-shell\tools\family_look.json` — corner 7.67 × 11.00 px on every
  surface, never scaled to the surface; `clip_pad` 0.5, `frame_pad` 1.5,
  `stroke_width` 1, `corner_units` 27.8, `bar_height` 48.
- `F:\Documents\popit-shell\docs\index.html` — the generated landing page, whose tokens
  are `--paper #d9c9a6`, `--brass #b08d57`, `--brass-lit #e2c188`, `--ink #0b0906`,
  `--panel #14100b`, `--line rgba(176,141,87,0.32)`, body `Georgia` 16px/1.6, eyebrows
  12px Segoe uppercase at 0.22em.

## What my version got wrong, by name

| Failure | What I did | What the pin says |
|---|---|---|
| Wrong reference | Read `openlock_schemes.css` `.Toast` (a game HUD scheme) and called it the Openlock toast look | The family look is the popit-shell contour and landing tokens, not the game's HUD toast |
| Wrong location | New `popit_apps/agent_toast/` in the forge | The shell, its frame and its gate live in `F:\Documents\popit-shell` |
| No contour | Tk `highlightthickness=1` square frame | One nine-slice contour, clip at 0.5 and frame at 1.5, 7.67 × 11.00 corner on every surface |
| Invented palette | `#0C0E0C`, `#D8B45A`, `#93C99B` | `#0b0906`, `#b08d57`, `#e2c188`, `#d9c9a6`, `#14100b` |
| Wrong register | Consolas 8/9 px throughout and a `◆`/`⌖` chrome | Georgia body, Segoe UI uppercase eyebrows at 0.22em, the contour's own chrome |
| No gate | No probe or gate run against `family_look.json` | `family-look-pinned`, `landing-generated`, `contour-authority`; the gate reports 21 checks, 0 refusals |
| Incomplete claim | `state.py` and `window.py` exist; `server.py`, `probe.py`, `start.cmd` and a receipt do not | A tool is not finished without a probe that reads its surface |

Measured just now, from the repository itself:

```text
$ python tools/gate.py
...
[ok] family-look-pinned the family look pin matches what the surfaces draw
[ok] landing-generated the landing page is generated from the pinned look
[ok] contour-authority the nine-slice is defined once
21 checks, 0 refusals
```

`docs/index.html` is 165 lines, `docs/family-look.md` 38, `tools/family_look.json` 64.
The landing page comments the rule directly: "A surface paints through the contour clip
and strokes its frame. No radius anywhere."

## The correction

The agent toast is not finished and must not be described as a Popit-shell application
until it is rebuilt in `F:\Documents\popit-shell` against:

1. `ui/contour.js` for the path (`contourPath` / `contourWindowPath`) and the nine-slice;
2. `tools/family_look.json` for the corner, clip pad, frame pad and stroke width;
3. the landing tokens for ground, panel, brass, paper and ink;
4. a probe that reads the pinned window and a gate run that includes `family-look-pinned`.

The guess-based Tk palette in `popit_apps/agent_toast/window.py` is evidence of this
failure, not a base to keep.

## What this probe does not claim

No pinned application was built or witnessed in this pass. No reskin of the existing
`window.py` is claimed to satisfy the contour, because Tk's square frame cannot draw the
nine-slice path without the contour's own geometry. The next pass starts from
`ui/contour.js`, not from the screenshot.
