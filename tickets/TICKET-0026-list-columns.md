# TICKET-0026 — List rows get headers and a name-width control

**Status:** implemented in 0.8.27; gate and installed-zip probe pass.
**Owner:** ala
**Opened:** 2026-11-15

## Requirement

The owner's report, verbatim:

> okay fantastic work but also now in these views where sometimes content will be right aligned it cuts off because there's no categories or options to resize them in the panes

The screenshot showed the Packages list with the package name on the left and
hero/date pushed to the right, both clipped, and no header or width control.

## Contract

1. `scene.dmf.list_name_width` is a 0.25–0.80 factor, default 0.5, labelled
   **Name width** under the affected lists and saved with the scene.
2. Every affected row uses `layout.split(factor=list_name_width)` instead of
   packing a left label and a right-aligned label into one row. The name column
   gets that share; the detail columns share the rest.
3. **Package**, **Install** and **Component** lists draw a header row aligned to
   the same split, so the columns have names: `Package / Hero · updated`,
   `Install / Kind · build`, `Component / Kind`.
4. The fixed `_short()` truncation in these rows is gone; Blender clips to the
   real width, so widening the name column reveals more rather than keeping a
   20/14/18-character cap.
5. Scope: Packages, Clients & installs, and Live components. Other lists keep
   their existing layout until they are reviewed.

Blender UIList has no draggable column separators, so the control is a factor
slider per pane rather than a mouse-resized grid.

## Evidence

- `v0.8.27` installed-zip probe 14/14 including `find-clients-reads-installs`
  count 9.
- `artifacts/receipts/mods-width-0.8.27b.png` at width 0.55: headers, longer
  names, hero and date visible.
- `artifacts/receipts/clients-width-0.8.27.png` at width 0.6: the full
  `game · compiler · vpk · 6861 Nov 09 2026` detail is readable.
- Gate green.

## Not checked

- Parts, clips, materials and hierarchy lists were not converted in this pass.
- Dragging a separator with the mouse is not available in Blender's UIList API;
  the slider is the supported resize.
