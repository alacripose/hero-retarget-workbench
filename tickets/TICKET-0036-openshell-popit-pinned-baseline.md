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
