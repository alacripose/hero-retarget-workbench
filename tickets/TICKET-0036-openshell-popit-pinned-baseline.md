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

## Open limit

The standalone mount lands in a `CitadelHud` component root that has no parent and no box, so the
bar measures 0×0 in game. Two paths are named in the ticket body below; neither is done. The theme
work above is independent of that mount problem and is verified without it.

Paths: (a) mount through the Deadworks UI channel (`openlock_shell_server.xml`, `openlock_ui open`)
so the shell lands in the live HUD; (b) override the match HUD layouts the way `base_hud.xml` is
overridden, with the anchor inside the laid-out `WindowRoot`.
