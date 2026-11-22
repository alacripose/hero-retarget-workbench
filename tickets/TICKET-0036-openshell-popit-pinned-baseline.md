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

## 2026-11-21 (third pass) — roles by name, installed, and the mount measured in game

**The gate now covers ink roles.** `O9 roles-named` reads the pinned scheme's eleven roles and
refuses three things in any theme: a role the pinned scheme does not name (a new surface with no
pinned value behind it), a pinned role left unpainted, and a role value that is not a colour or a
token (`#…` or `@define`). The rule lives in `role_problems()` so the gate and its selftest read the
same code. The selftest grew `role-invented`, `role-dropped` and `role-shape` — 7 checks, 0 failures —
and the real tree was provoked: appending `corner-radius 7.67px` to `brass.theme` gave
`[FAIL] roles-named: role not named by the pinned scheme: brass:corner-radius` with exit 1, and
restoring the file returned 9 checks, 0 refusals.

**Installed.** Deadlock was closed (the owner's instruction for this pass), the installer packed and
installed with its own archive gate inline: **2,690,213 bytes**, sha256
`6dd70b7147de87a0a00ba82673e4a9282a25a56e9c2fe01ab211ddd6643f201a`, state `CURRENT`. The installed
archive passes all nine `--archive` facts (popit default, popit default form, popit order[0], brass
option, 48px bar, four grips, contour runtime, carrier rule, folded forms).

**What the client said.** The bar chain is still
`Taskbar:0x0 < OpenlockStandaloneHost:0x0 < CitadelHudRoot:0x0`, and the boot's own walk now counts
what it looked at: `carrier walk: visited=400 widest=0x0 carrier=CitadelHudRoot`. Four hundred panels
under the component root, and not one of them is laid out. That is not a sizing retry any more: this
`CitadelHud` instance is detached, so nothing mounted inside it can draw, and mounting the shell
there can never produce a bar.

**Two real defects were still removed on the way.** `Panorama` panels have no `Children()` — the
engine's accessors are `GetChildCount()`/`GetChild(i)` — so the first carrier walk was looking at
nothing; that is fixed and the walk now reports its own numbers. And the boot no longer trusts the
shipped anchor just because it exists: an anchor is used only when a panel above it has a box, and
otherwise the shell is mounted beside it on a laid-out carrier (new case in `boot-carrier-test`, which
is now 12 checks, 0 failures).

**Open.** The shell mounts and cannot draw, because the standalone host is not in the drawn HUD. The
two remaining paths are named: mount through the Deadworks UI channel (`openlock_shell_server.xml`,
`openlock_ui open`) so the shell is loaded into the live HUD, or put the anchor into the layout the
match actually draws. Both need a decision the owner holds: whether the client should run with the
Deadworks host, or whether a match-HUD layout override is acceptable.

## 2026-11-22 (fourth pass) — the bar was retired behind an inverted pair, and the blue was not Popit

**The owner's reading was the fix.** *"the changes that added the cloud bar and deprecated the old
openshell taskbar is the reason why nothing draws, we have to bring in the new popit shell taskbar in
place of it"* — and it is exactly what the source said once read:

```js
// The taskbar is retired. … no code path brings it back: the lower cloud band is the shell's only rail.
function showTaskbar() { taskbar.style.opacity = "0"; taskbar.style.visibility = "collapse"; }
function hideTaskbar() { taskbar.style.visibility = "visible"; taskbar.style.opacity = "1"; }
```

`showTaskbar()` was called on every pointer move, on every tab choice and on every expand, and each
call collapsed the strip. `render()` set `visibility: visible` and the next mouse move took it away,
and an idle timer (`lastInteractionAt > 5000`) hid it as well. The one element the owner saw for five
hours was the preload strip overflowing a collapsed bar.

**What changed.** `showTaskbar()` shows and `hideTaskbar()` collapses; every render asserts the bar;
the idle timer no longer hides it (the pinned client's strip is on screen whether the pointer moved);
`chrome-test` grew four checks that read the pair out of the source (98 checks, 0 failures).

**The blue was the old Popit, not the popit shell.** The scheme the client defaults to was
`SchemePopit` from `shell/alpha-shell/themes/popit.theme`, which still carried the LittleBigPlanet
blue (`#1F6E96F2`, `#267AA4F2`, cream edge, green accent) — so the window body painted blue through
`.ContourFill`. `popit.theme` now carries the inks the shell at `F:/Documents/popit-shell` actually
draws with (`ui/bar.css`, `ui/style.css`: ink `#0f1113`, paper `#e6dbc2`, brass `#b08d57`, brass-lit
`#d9b779`, dim `#8b8778`), `openlock_pinned.css` declares the bar and the plate in the same inks, and
`tools/gen_shell_theme.py` (already painting `.ContourInk`/`.ContourFill`) regenerated
`openlock_schemes.css`: 9 schemes, default popit, 0 refusals.

**Measured in the running client.** Installed `AA1EEFD4FF9533DF53320E467889846CE71D04105ABFE868650B2F17200F3EC3`
(archive passes all nine `--archive` facts), launched the normal path, pressed through the menu, and
the live log reads:

```
[Openlock] bar chain: Taskbar:1920x48 < OpenlockStandaloneHost:1920x1080 < CitadelHudRoot:1920x1080
```

No panel in the chain is 0×0, and the shell draws in the hideout: an ink window with a brass contour,
an uppercase brass-lit title over a keyline, brass list rows, and the 48 px bar with `Start`,
`Windows`, the build cell and the clock across the top. The boot's own settle pass is what gets there
(`settle: host laid out 1920x1080 at step 3`); the bar's first measurement is 0 because it is read
before layout, and the later passes report 1920×48.

**Gates.** contour 10/0 · options 9/0 · options selftest 7/0 · `--archive` on the installed VPK 9/0 ·
landing `--check` ok · chrome 98 · contour-test 53/0 · boot-carrier 12/0.

**Open.** The window body is still faintly translucent over the game (its fill comes from the contour
slice), the bar's cell spacing is the shell's own 6 px rather than the Popit shell's 5.76 px, and the
`Windows` cell is wider than the Popit's `max-width` of seven cap units. Those are look refinements,
not blockers; the surface and the inks are the new Popit shell's.

## 2026-11-22 (fifth pass) — the bar is the popit-shell's bar, value by value

**Authority first.** `F:/Documents/popit-shell` is the project the owner links: `origin` is
`https://github.com/alacripose/popit-shell.git`, `HEAD` is `e507d355153c8b7c9e5c6ea312555c1323a2588d`
and `git ls-remote origin` reports the same `e507d35…` for `refs/heads/main`, with a clean working
tree. No fetch was needed and no divergence exists; every number below is from that checkout at that
commit, read from `tools/bar_pin.json`, `tools/family_look.json`, `ui/bar.css`, `ui/bar.html`,
`ui/bar.js`, `ui/index.html`, `ui/style.css` and `ui/app.js`.

### The spec, and what our shell emits

| # | fact | popit-shell (source) | openshell (file) | measured in the live client |
|---|---|---|---|---|
| 1 | bar height | 48 (`bar_pin.BAR_HEIGHT`, `family_look.bar_height`) | `.Taskbar height: 48px` | `bar=1920x48` |
| 2 | bar padding | 5.12 down, 17.6 across (cap 32 × 0.16 / 0.55) | `padding: 5.12px 17.6px` | `startx=18` |
| 3 | cell gap | 5.76 (cap × 0.18) | cells `margin-right: 5.76px` | `gap=6` (the client's grid rounds 5.76 up) |
| 4 | cell inset | 3 by 16 (`--ink-y`, `--ink-x`) | `padding: 3px 16px` | `tab0=88` wide |
| 5 | cell width band | min 64, max 224 (cap × 2, × 7) | `min-width: 64px; max-width: 224px` | `tab0=88`, `windows=90`, both inside |
| 6 | cell text | 13.44 (cap × 0.42) paper | `font-size: 13.44px; color: #e6dbc2` | source-level |
| 7 | Start cell | 92.8 min, centred, 0.96 tracking, brass-lit | `.BarStart min-width: 92.8px; letter-spacing: 0.96px; #d9b779` | `start=93` |
| 8 | clock cell | 108.8 min, centred, dim | `.Clock min-width: 108.8px; #8b8778` | `clock=109` |
| 9 | cell fill | paper 6 % gradient, active brass 16 % | `#e6dbc20f`, active `#b08d5729` | pixel `#171615` |
| 10 | cell outline | brass 42 %, hover brass-lit 85 %, active brass-lit | `.ContourInk #b08d576b`, hover `#d9b779d9`, focus `#d9b779` | contour chip per cell |
| 11 | cell order | Start, one cell per open window, clock | Start, `TabStrip` cells, then the shell's own Windows/version/clock | `startx=18 tab0x=117 tabs=5` |
| 12 | plate padding | 3.78 top, 36 sides, 8.64 bottom (u 5.4) | `.WindowTitle padding: 3.78px 36px 8.64px` | source-level |
| 13 | title | 19.44 (u × 3.6), tracking 5.94 (u × 1.1), brass-lit, uppercase | same in `.WindowTitleLabel` | reference render: `h1 19.44px / 5.94px / rgb(217,183,121)` |
| 14 | keyline | brass 32 % under the plate | `border-bottom: 1px solid #b08d5752` | source-level |
| 15 | body | opaque ink `#0f1113` (two washes over it) | `.ShellRoot .ContourFill #0f1113`, `.WindowBody #0f1113` | pixel `#0F1114` inside the window |

### What had to change structurally

* **The strip was empty.** `renderBar()` set the version label and nothing else, so the bar drew Start
  and the readouts with a hole between them. It now builds one cell per open window through the
  shell's own `addTab`, keyed by a signature of the open set. Measured: `tabs=5`.
* **`Children()` does not exist in Panorama.** The cell count and the contour chips both asked for it.
  They use `GetChildCount`/`GetChild` now (the same defect the boot had last pass).
* **Start was in the right-hand cluster**, so the cells ran to its left and the clock sat beside it —
  a different bar. It leads the strip now: `startx=18`, first cell at `117` (18 + 93 + 6).
* **The body was a translucent contour slice**; it is solid ink at the shell root's specificity.

### The comparison

`popit-shell` was rendered from its own files (a local server over `F:/Documents/popit-shell/ui`,
`bar.html` with sample cells injected through its own render path, `index.html` for the window), and
captured beside a fresh capture of the running client. Reference bar: Start, `windows` (active),
`inventory`, `settings`, clock. Client bar: Start, five window cells, the shell's own Windows cell,
the build cell, clock. Reference window: brass-lit `POPIT` plate over an ink body with brass cards.
Client window: brass-lit `OPENSHELL` plate over an ink body with brass rows. Images:
`popit-compare.png` (full) and `popit-compare-small.png` in the model-forge root. The Freebuff chip
over the reference's Start cell is this app's preview overlay, not the page.

### Still different, measured, not hidden

1. **Two extra cells.** The bar carries the shell's `Windows` cell (90 px) and a build-hash cell,
   which the reference does not have; both are inside the 224 px limit and neither is a window cell.
2. **Gap is 6 px on screen, 5.76 in the sheet.** Panorama's layout grid rounds 5.76 up to 6; the
   stylesheet value and the reference agree, the pixel grid does not have thirds.
3. **Body washes.** The reference paints two radial washes over the ink; Panorama here has no radial
   gradient, so the body is flat `#0f1113` (measured `#0F1114`).
4. **Cell labels** are the game's own window titles (`gameplay_hud`, `windows`, …) where the reference
   shows application titles, because the cells are the game's windows.
5. **Cell clip.** The reference clips each cell to its contour with an SVG stroke; the shell uses its
   pinned nine-slice contour chip.

### Gates

contour 10/0 · options 9/0 · options selftest 7/0 · archive on the installed VPK 9/0 · landing
`--check` ok · chrome 99 · contour-test 53/0 · boot-carrier 12/0. The archive installed for this pass
is `bf7cf983da49c9d33cec90f97e1a9cb9b6329a9a90fc7e01b8e3a62ec0782a3a`, built after the layout order change and the metrics probe. Live chain:
`Taskbar:1920x48 < OpenlockStandaloneHost:1920x1080 < CitadelHudRoot:1920x1080`.

## 2026-11-22 (sixth pass) — the contour was on no cell, and where it was, it was a slab

The owner asked why the contour on the shell's items is not the contour in the popit shell, whose
docs and landing page already draw it. The answer was not a value: it was the accessor and the shape
of the paint.

**What was actually wrong, in the order it was found.**

1. `openlock_contour.js` cleared its own slices with `layer.Children()`. Panorama has no `Children()`;
   the call returned nothing, so a repaint left the previous slices in place and stacked a second set
   under the first. The same defect was in the bar's cell count last pass.
2. `layerFor` moved the slice layer under the surface's content with `host.GetFirstChild()`, which is
   also not this client's accessor. The throw was caught, the layer stayed last, and its fill painted
   over every bar cell's label — the text was there, under the paint. `GetChild(0)` after
   `GetChildCount()` is the accessor that works.
3. The stroke was drawn as a **slab**: one full-width, full-height panel between the crowns. A fill of
   six per cent paper cannot hide a 45 per cent brass slab, so every cell rendered solid brass. The
   ink is now an outline — the two crowns, one 1 px line down each side, and nothing between them —
   and the fill is the one surface inside it, inset by 1 px.
4. The bar cell's own padding (3 by 16) was inherited by the slice layer, so the contour started
   16 px into a 36 px cell and its crown was cut off. The inset moved to the label; the shape gets the
   whole box. Measured after: the cells read `Minimap`, `Abilities`, `inventory` in paper on ink,
   with a 1 px brass ink and the profile's crown.
5. Every frame is contoured where its geometry is written (`setRect`), not never: a 640x520 window
   now reports `contour 640x520 band=11 drawn`. A tracked game panel 1900 px wide was being contoured
   every frame as it animated; surfaces over 1200 by 900 are named as not shell surfaces and skipped.

**The profile is the reference's, unchanged.** `docs/contour.json` (the page 9 loop, 445.05..526.95 by
514.348..635.652) and `docs/family-look.json` (corner 7.67 by 11.00 px, clip pad 0.5, frame pad 1.5)
are byte-identical to `F:/Documents/popit-shell` at `e507d355`; the generated slice data carries the
same digest. The gate proves it: `contour-authority`, `contour-pinned`, `contour-data-current`,
`corner-is-the-button`, `nothing-stretched`, `outline-not-clipped`, `contour-slices-tested`,
`contour-wired`, `options-pinned` — 10 checks, 0 refusals.

**The test and the gate were widened, not weakened.** The slice test now asserts the ink is *two*
1 px side rails rather than one full-width rail, and that the fill is one inset surface; the gate's
`outline-not-clipped` reads the new call. The independent reading of the profile (a flattened polygon
sampled per row) is unchanged and still agrees with every crown row.

**The landing page already draws this contour** — `landing/index.html` with `landing/contour.js` and
`landing/family-look.json`, which embeds the same profile and the gate's own check count. It was
stale against this pass's check count (63 shape checks, not 10); `python tools/landing.py --check`
now reports the records are current.

**Measured in the client after the fixes** (installed
`BDEE7EBFF6D033289F5AB944450E19C47D634D3FA8E922281FD6A3AAAF1AC80C`, normal launch, hideout,
PrintWindow):

```
[openlock] contour 82x36 band=11 slices=48 drawn
[openlock] contour 188x36 band=11 slices=48 drawn
[openlock] contour 640x520 band=11 slices=39 drawn
[Openlock] bar metrics: bar=1920x48 start=93 tab0=85 gap=5.6 windows=90 clock=109 tabs=3
                        startx=18 tab0x=117 gapExact=5.6
```

**The gap is 5.6, and it is the measurement, not the sheet.** The cell margin is 5.76. The Start cell's
min-width is 92.8 and the client lays it out at 93; `gapExact` subtracts the laid-out width from the
next cell's position, so an 0.2 px width rounding comes out of the gap and 5.76 - 0.2 reads 5.6. The
two facts together pin it: the sheet and the reference agree at 5.76, and this client's layout grid
truncates a fractional width to a whole pixel before it positions the next cell. The remeasurement is
`gapExact`, unrounded, so a future build that stops truncating will read 5.76 without a code change.

**Still different, measured.** The window's body is opaque ink and its frame is contoured, but the
rows inside it (`Dashboard`, the HUD panel list) are plain 1 px bordered rows, not contoured cells;
the reference draws each card with its own contour. The bar's own two extra cells (Windows, build
hash) remain, as recorded last pass.

### Gates, all exit 0

contour 10/0 · options 9/0 · options selftest 7/0 · archive on the installed VPK 9/0 · landing
`--check` ok · chrome 99 · contour-test 63/0 · boot-carrier 12/0.

## 2026-11-22 (seventh pass) — the current button contour is pinned before the clip padding work

The owner asked for the contour the buttons carry today to be screenshotted and pinned, because the
next step is the clip padding, the interaction logic and the look from the pinned popit application and
taskbar. The pin is `pins/contour-pin.json` with `pins/contour-pin.png` and the four state captures it
is composed from (`contour-idle`, `-hover`, `-activated`, `-resized`).

**What the pin records, measured on the installed archive `1B8F849ADDC27B228891B606DF248CB5064F507B709DA58D8D85D6A15F26D8A4`.**
A normal launch into the hideout with PrintWindow, then the pointer driven to the first cell, clicked,
and the window's corner dragged:

```
bar=1920x48 start=93 tab0=85 gap=5.6 windows=90 clock=109 tabs=3 startx=18 tab0x=117 gapExact=5.6
contour 87x36  band=11 slices=48 drawn
contour 82x36  band=11 slices=48 drawn
contour 188x36 band=11 slices=48 drawn
contour 218x36 band=11 slices=48 drawn
contour 300x66 band=11 slices=48 drawn
contour 640x520 band=11 slices=39 drawn
```

The authority is unchanged and is what the runtime renders: `docs/contour.json` and
`docs/family-look.json` (corner 7.67 by 11.00 px, clip pad 0.5, frame pad 1.5, stroke 1 px, surfaces
`.WindowFrame`, `.ShellTab`, `.WindowsButton`, `.Clock`), digested into the pin beside the images. The
landing page still checks: `python tools/landing.py --check` → ok.

**One drift was found and closed in the same pass.** The Start cell had grown to 102 px because the
`.BarStart` rule still carried `padding: 3px 16px` while its label carries the inset too; with the
host's padding removed it measures 93 again, as the reference's 92.8 lays out.

**What the pin deliberately shows as not yet the reference.**

* The **hover and activated** cells fill brass over the crown (`.ShellTab:hover` and `.Active` paint a
  rectangle and the fill colour is not the reference's six per cent paper). The outline is still there;
  the fill is the next step's work.
* The **window after a resize** keeps its body and rows but does not repaint its crown — the frame's
  contour is taken on the geometry write, and a drag that ends without a further write leaves the
  previous crown. This is the clip padding step's first job.
* The rows inside a window (`Dashboard`, the HUD panel list) are still plain 1 px bordered rows; the
  contour on them is the step after this pin.

**Gates, all exit 0:** contour 10/0 · options 9/0 · options selftest 7/0 · archive on the installed
VPK 9/0 · landing `--check` ok · chrome 99 · contour-test 63/0 · boot-carrier 12/0.

## 2026-11-22 (eighth pass) — clip padding, interaction fills and rows: two of the three closed

The pin's three deltas were worked in order, against the pinned reference in `pins/` and the shape
authority in `docs/`.

**One shared padding implementation.** `openlock_contour.js` now derives every surface from
`OpenlockContour.pads()`, which reads `clip_pad` 0.5, `frame_pad` 1.5 and `stroke_width` 1 straight from
`docs/family-look.json`. The profile is cut at the frame pad, the ink is one stroke wide, and the fill
starts at `2 * stroke` inside the box. A cell, a row and a window crown all come through that one call;
none carries its own numbers. The test proves it (`pads()` equals the pin's constants, and the fill's
first row starts at the stroke), and the gate's `outline-not-clipped` now reads the padded call.

**Delta 1, hover and activated cells — closed, measured.** The flood was a rectangle: `.Taskbar
.ShellTab.Active { background-color: #b08d5729 }` painted a slab across the crown, and the fill colour
was a brass that carried over it. Both are gone. The fills are the reference's two paints composited
over the bar's ink — paper 6 per cent (#1c1d1e) and brass 16 per cent (#29251e) — and hover moves only
the ink, as `bar.css` does. Measured: `contour 85x36 / 82x36 / 188x36 / 218x36 band=11 slices=48`, cells
read paper-on-ink in all three states, no brass over a crown.

**Delta 3, rows inside a window — closed for the surfaces, measured.** `actionRow` and `rowXd` build a
`ViewRowBox` ground that takes the contour, with the Label inside keeping the text, the pointer and the
handler (`check_shell_clicks` still reads a Label, `row.text` and the activation event), and
`addControl` contours `ViewAction` surfaces. Measured: `contour 130x22 band=7 slices=28`,
`99x22 band=7`, `96x22 band=7` — a 22 px row cuts a 7 px crown from the same profile, and the rows show
the chamfer and the 1 px ink in the captures.

**Delta 2, the window crown after a drag — not closed, and the attempt is shown.** The drag now ends by
dropping the frame's size cache and drawing twice (`contourChip` immediately and again at 0.12 s), so
the frame is re-cut at the box the drag ended on and the log shows the window's own line. What does not
follow is the *visible* crown: the frame's plates (`WindowTitle`, `WindowMeta`, `WindowBody`) are
rectangles, this client has no clip for a child, and a plate inset by 2 px still squares the corner the
contour cut. The capture after the drag shows the contoured rows and the ink body with a square outer
corner. Recorded as open in the pin (`states.resized`) rather than claimed.

**Start stays at 93 px** (`bar metrics: start=93 tab0=85 gap=5.6`), the two non-reference cells are
untouched, and `docs/family-look.json`'s surface list is unchanged.

**Gates, all exit 0:** contour 11/0 (a new `contour-on-rows-and-crowns` check) · options 9/0 · options
selftest 7/0 · archive on the installed VPK (`26BA67D90DD7E7199D13C6FABD2A4346AA364BCAD04AC553A888F8C3482A07F9`) 9/0 ·
landing `--check` ok · chrome 99 · contour-test 74/0 · boot-carrier 12/0.

## 2026-11-22 (ninth pass) — the window crown is the contour, and the drag has no press to answer

**The corner is now cut, not painted over.** Three things stood between the contour and the screen, and
each was found by looking at a capture rather than by reading a log line:

* `.WindowFrame .WindowMeta` painted `#0f1113ee` and `.WindowTitle` painted a wash right up to the
  frame's edge, so both plates drew a square across the crown the contour had just cut.
* The four `GripNW/NE/SW/SE` pins were 22 px brass squares sitting in the corners: the loudest
  rectangle on the window, whatever the profile did underneath.
* The body's own background painted over the contour's fill.

The plates are transparent now and the shell insets them from the contour's own band
(`plateInsets()` calls `OpenlockContour.band(h)`, never a constant), so the title starts below the
crown and the body ends above the bottom one. The pins are 10 px brass marks inset 6 px inside the
crown. The plate's fill is the pin's `#1b1a16` instead of the bar's `#0f1113`. Nothing in a window
carries its own contour number: the crown, the plate inset and the fill all come from `pads()` and
`band()`.

**Measured, from the captures, not asserted.** With the window at 640x520 at (26,77):

| state | corner arc | ink | fill |
|---|---|---|---|
| idle | 5 px wide × 8 rows | 1 px | (28,26,22) `#1c1a16` |
| hover | 5 × 8 | 1 px | (28,26,22) |
| activated | 5 × 8 | 1 px | (28,26,22) |
| after the corner drag | 5 × 8 | 1 px | (28,26,22) |
| after the resize attempt | 5 × 8 | 1 px | (28,26,22) |

The reference corner is 7.67 × 11.00 px at the drawing's own pad; the pin cuts the profile at
`frame_pad` 1.5, so the captured arc should be 7.67 − 2×1.5 = 4.67 → 5 px across and 11 − 3 = 8 rows
down. That is exactly what the pixels read. The fill is one point off per channel from `#1b1a16`,
which is the capture's colour rounding; the sheet value is the pin's.

**What is still open, and why: the gesture does not change the box.** A press on the grip or the title
is performed by the harness and produces nothing: the window stays 640x520 at (26,77), the log carries
no new frame size and no `mousedown args`/`drag` line, while the same session's bar cells answer their
presses (the active cell moved from cell 1 to cell 2 to cell 3 on successive clicks). So this client
delivers a press to a bar cell as `onactivate` and does not deliver `onmousedown` at all to a window
frame over the hideout. The grips now bind `onactivate` as well as `onmousedown` (guarded so a press
during a drag is ignored, since the poll owns the release), and that press still does not arrive.

The crown therefore cannot be shown *surviving a resize the client refuses to make*. What the capture
does show is that the crown is the profile in every state, and the log shows the same crown cut at four
box sizes the shell does apply — 640x520, 640x440, 300x66 and 300x51, all `band=11` for the frames and
`band=7` for the 22 px rows. That is recorded as open in `pins/contour-pin.json` (`states.drag`,
`states.resized`, `next`) with this pass's reasoning, rather than claimed as closed.

**Unchanged and re-measured:** Start 93 px with no host padding (`start=93 tab0=85 gap=5.6`), cells
85x36 / 82x36 / 188x36 / 218x36 `band=11 slices=48`, rows 130x22 / 99x22 / 96x22 `band=7 slices=28`,
the `.WindowsButton` cell and the build-hash cell untouched, `docs/family-look.json`'s surface list
unchanged. The stale `.ShellTab:hover .ContourFill { #b08d5721 }` rule — a brass flood that survived
the previous pass's fill work — was found and removed; hover and active now read `#1d1e1f` and
`#2a261f`.

**Gates, all exit 0:** contour 11/0 · options 9/0 · options selftest 7/0 · archive on the installed
VPK (`74AC6E61ACAFBE2CA461C49DE1A10E892B8CEB9CEDABC3F31965FFBFB589EB59`) 9/0 · landing `--check` ok ·
chrome 99 · contour-test 74/0 · boot-carrier 12/0 · `check_shell_clicks` ok.

## 2026-11-22 (tenth pass) — the corner drag and the resize are real, and the pin is one artifact set

**The press path, found rather than re-logged.** The previous pass pressed the grip and nothing happened,
because `makeDraggable` bound `onmousedown`/`onmouseup`/`onactivate` while this client dispatches a press
on a hittable panel as **`onmouseactivate`** — the event `addControl` binds, and the reason the bar's
cells answer and a window's chrome did not. The grip, the move handle and the drag strip now bind
`onmouseactivate` too (guarded so a press during a drag is ignored and the poll keeps the release), and
`beginPointerDrag` runs. A press on the south-east grip now begins the poll and the window follows it.

**Both states are real resizes while the shell is live, measured by the log and the pixels:**

| state | window box | how | corner arc | ink | fill |
|---|---|---|---|---|---|
| idle | 640x520 at (26,77) | launch | 5 x 8 px | 1 px | (33,27,23) |
| drag | 823x689 → 833x698 at (26,77) | pointer presses the SE grip and drags to (830,740) | 5 x 8 px | 1 px | (34,27,23) |
| resized | 1177x395 → 1072x380 → 815x348 at (622,642) | second pointer drag of the SE grip to (690,610) | 5 x 8 px | 1 px | (28,28,23) |
| activated | 640x520 at (130,133) | cell press restored the window | 5 x 8 px | 1 px | (27,26,22) |

The interpolated boxes (`823x689`, `1072x380`, `815x348`) are the drag's own signature: a restore writes
one rect, a drag writes a series as the poll moves. Each box is re-cut — `band=11 slices=48` at every
step — and the crown at each is the pinned profile: `7.67 − 2×1.5 = 4.67 → 5 px` across and
`11 − 3 = 8` rows down, 1 px ink of `#b08d576b`, fill the plate's `#1b1a16` (measured 27–34 in red,
which is the title wash over the plate's fill and the capture's rounding). `states.drag` and
`states.resized` in `contour-pin.json` therefore point at captures of genuinely different windows, not
a redraw at 640x520.

**The pin is one artifact set.** `pins/` now holds exactly `contour-pin.png`, `contour-pin.json` and the
five per-state captures the pin hashes; the diagnostic crops (`check-*.png`, `corner-*.png`,
`probe-*.png`, `win-*.png`, `bar-*-zoom.png`, `window-resized.png`, `game-print.png`) moved to
`artifacts/diagnostics/contour-2026-11-22/` rather than being deleted. Every image sha256 in the pin
re-verifies against disk, as do `docs/contour.json` and `docs/family-look.json`; the installed archive is
`559D7B01A7529BA7EDC1D5F599EA41CCBF295E13C2E934269EDEC097D78D9F8C`. Schema stays
`openlock.contour-pin/2`: the pin's shape did not change, only its evidence.

**Unchanged:** Start 93 px with no host padding (`start=93 tab0=85 gap=5.6 startx=18 tab0x=117`), cells
85x36 / 82x36 / 188x36 / 218x36 `band=11 slices=48`, rows 130x22 / 99x22 / 96x22 `band=7 slices=28`,
`.WindowsButton` and the build-hash cell untouched, `docs/family-look.json`'s surface list unchanged, and
no window file gained a contour number — crown, plate inset, band and fill all come from `padsOf`/
`pads()` and `band()`.

**Gates, all exit 0:** contour 11/0 · options 9/0 · options selftest 7/0 · archive 9/0 · landing
`--check` ok · chrome 99 · contour-test 74/0 · boot-carrier 12/0 · `check_shell_clicks` ok. The
pre-existing `project.py gate` probe-lane failure is still recorded in `STATUS.md`, not hidden.
