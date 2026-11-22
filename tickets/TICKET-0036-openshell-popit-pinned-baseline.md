# TICKET-0036 — the Popit shell is the pinned baseline; every other theme is an option

**Status:** theme order and the mutable-window baseline are implemented and measured; the in-game
mount is measured as a 0×0 tree and is not fixed yet.
**Owner:** ala
**Opened:** 2026-11-21

## Requirement

The owner's corrections, verbatim:

> get the openshell up to the popit shell pinned contour & visual baseline and landing page and
> popit application basline from the session archive mutatable windows instead of bitching about me
> being in the hideout and follow project convention outlined in the deadlock model forge agents
> file while upgrading the openshell package formats to the updated brass meridian and openlock
> designs

> the popit-shell is the pinned baseline every other shape and theme comes after it as an option

## Contract

1. **Popit is the default, not an option.** The theme picker's default is `popit`; every other
   scheme (brass meridian, family, deadlock, alpha, holo, material, ios, touchwiz) comes after it in
   the order. The pinned shape is `docs/family-look.json`, read from the Popit source.
2. **A window is mutable.** The Popit application baseline moves a window by its title bar and
   resizes it from four corners. The pinned stylesheet may retire debug chrome, never the grips.
3. **A theme is colour, the contour is shape.** Brass meridian carries the pinned inks only; it
   cannot change geometry, and the pinned stylesheet still loads last.
4. **The shell must draw in the game the owner is in.** Being in a match is not a reason to stop;
   the mount is measured rather than assumed.

## State (2026-11-21)

- `shell/alpha-shell/themes/default` is `popit`; `themes/order` is popit, brass, family, deadlock,
  alpha, holo, material, ios, touchwiz. The generated `openlock_shell_data.js` reads
  `themes.default = popit`, `themes.defaultForm = popit`, and `brass` is a scheme with its pinned
  ink roles.
- `openlock_pinned.css` keeps the four resize grips visible in the pinned brass and retires only the
  cost readout.
- `openlock_boot.js` no longer yields on a session-wide flag, so a HUD reload can mount again.

## Measured

- `python tools/gen_shell_data.py` → 349 windows, 9 refusals, 22 wishes; `themes.default` is
  `popit` and `order[0]` is `popit`.
- `node tools/tests/chrome-test.js` → 94 checks OK; `node tools/tests/contour-test.js` → 53 checks,
  0 failures; `python tools/contour_gate.py` → 9 checks, 0 refusals.
- Installed VPK `4EC5163C…` (22:54), client boot log:
  `[dl-openshell] mount: shell mounted from base_hud without a server`, then
  `[Openlock] bar chain: Taskbar:0x0 < OpenlockStandaloneHost:0x0 < CitadelHudRoot:0x0`.

- `node tools/tests/boot-carrier-test.js` → 9 checks, 0 failures. The test stands the component
  tree up in JavaScript: a 0x0 `CitadelHudRoot` with no parent, a laid-out `HudContent` child, an
  optional shipped anchor and an optional Deadworks host. It proves the carrier rule (ancestor with
  a box, else nearest laid-out descendant, else outermost with its box stated) and the yield.

## Open limit

The standalone mount lands in a `CitadelHud` component root that has no parent and no box, so the
bar measures 0×0 in game. Two paths are named in the ticket body below; neither is done. The theme
work above is independent of that mount problem and is verified without it.

Paths: (a) mount through the Deadworks UI channel (`openlock_shell_server.xml`, `openlock_ui open`)
so the shell lands in the live HUD; (b) override the match HUD layouts the way `base_hud.xml` is
overridden, with the anchor inside the laid-out `WindowRoot`.

## 2026-11-21 (second pass) — the ruling is structural, and the gate refuses drift

**What the tree said.** The folding the ruling demands had not happened: `ios.form` declared
`.Taskbar height 30px`, `.TabStrip width 60%`, `18x16` window buttons and its own title metrics;
`material.form` and `touchwiz.form` declared the same 30px bar, 2px tab underlines and 20x20 /
22x18 buttons; all three declared `.WindowFrame border-radius` and `border-width`. Those are the
contour, the window frame and the slot metrics, so every one of them replaced the pinned baseline
instead of layering on it.

**What changed.**

- `ios.form`, `material.form` and `touchwiz.form` are now identity and colour only: `form`, `label`,
  `renderer generic`, and a hand-written comment that names what was removed and why. The frame, the
  48px bar, the plate, the cells at ink 3 by 16 and the four grips come from `openlock_pinned.css`
  and cannot be moved by a form. No generated blob hides the contour.
- `tools/contour_options_gate.py` is the new gate. It reads the hand-editable `.theme` and `.form`
  files, not the generated data, and checks eight facts: `themes/default` is popit, `forms/default`
  is popit, `order[0]` is popit, the generated data agrees, no theme declares anything but colour,
  no form other than popit declares anything but colour, the pinned sheet and `docs/family-look.json`
  still carry 48px / 7.67x11.00 / the visible grips, and the popit form still owns the frame.
- The gate is wired twice: `tools/contour_gate.py` runs it as `C10 options-pinned`, so the shape gate
  cannot pass while an option has taken the contour back, and `install.ps1` runs it against the
  packed archive before anything is installed.
- `install.ps1` gained `-BuildOnly`: it builds and packs the archive the installer would install,
  writes nothing into the install tree, and is therefore the one build mode that runs while the
  client is open. It is how the artifact was inspected without touching the running game.

**Measured.**

- `python tools/contour_options_gate.py` → 8 checks, 0 refusals.
- `python tools/contour_options_gate.py --selftest` → 4 checks, 0 failures: a planted
  `.WindowFrame border-radius` in a theme and a planted `.Taskbar height` in a form are both
  refused, and the order reader is checked.
- Provoked on the real tree: appending `rule .Taskbar height 30px` to `material.form` produced
  `[FAIL] forms-colour-only: material:11 .Taskbar height`; restoring the file returned the gate to
  0 refusals.
- `python tools/contour_gate.py` → 10 checks, 0 refusals (was 9; `options-pinned` added).
- `chrome-test` 94 checks OK, `contour-test` 53 checks 0 failures, `boot-carrier-test` 9 checks
  0 failures, `gen_shell_data.py` 349 windows / 9 refusals / 22 wishes, `landing.py --check` ok
  after regenerating the landing shape record for the new check count.
- Archive: `install.ps1 -BuildOnly` packed **2,686,445 bytes** at `dist/openlock_ui/pak01_dir.vpk`,
  sha256 `8106e4b36079d150605faa19ae532114b0957ab02f9b82efdbfb81f5631ad971`, with the installer's own
  archive gate passing inline. `contour_options_gate.py --archive` reports 9 checks, 0 failures:
  popit default, popit default form, popit order[0], brass option present, 48px bar pinned, the four
  resize grips visible, the contour runtime archived and called, the carrier rule in
  `openlock_boot.js`, and no option form setting the taskbar height in the generated sheet.
- The install tree was not touched: `citadel/addons/mods/pak01_dir.vpk` kept md5 `d0706b3e…`
  before and after the build, and no `-Live` install was attempted.
