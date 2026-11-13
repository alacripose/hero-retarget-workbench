# TICKET-0016 — Write an imported clip back out as animation DMX

Authority: `logs/authority/2026-11-13-bone-rules-ref-pose-clips.jsonl` (the owner
asked for AG1/AG2 clips to be imported, edited and carried, not only read) and
the 0.4.1 correction that the addon does not invent the owner's mapping. This
ticket closes the half 0.4.1 stated plainly: import, rename and preview of the
clips existed; writing the edited action back to a DMX did not.

## The claim to make true

An action this panel imported can be written back as an animation DMX named after
its clip, under a folder that never overwrites the extraction it came from, and
the file it writes is an animation DMX that imports again with the same length.

## Contract

1. **One row, one file.** Writing a clip calls PulseSrcOps' own animation export:
   the hero armature is the only exportable, `action_selection` is
   `FILTERED_ACTIONS`, and the armature's action filter is the escaped name of
   that one action. The file lands at `<folder>/anims/<clip>.dmx` — the name and
   layout an animgraph clip is compiled from, and the stem the `.vnmclip` beside
   it carries.
2. **Never over the extraction.** A blank write folder means
   `<clip folder>/edited`. An explicit folder is used as given. The extraction's
   DMX files, the `.vnmclip` pairs and every compiled file stay untouched.
3. **The export is not the file's state.** Scene export path, format, engine,
   DMX format and encoding, the export list, the armature's action, action
   selection, action filter, subdir and export flag, and the scene's current
   frame are saved before and restored after, including after a refusal.
4. **A refusal is reported, not swallowed.** No DMX written, an empty DMX or a
   missing action sets the row `FAILED` with the reason in the status line; it
   never marks a clip written because a command returned.
5. **The row records evidence.** `written` path and byte count are stored on the
   row only after the file exists and is non-empty.
6. **Bulk writes do not block.** Writing several clips uses the same timer queue
   as import, one clip per step, with a running status and a stop that leaves
   the finished files in place.

## Out of scope

- Compiling a `.vnmclip` or running the game's animgraph compiler. This ticket
  ends at a written, re-importable DMX.
- Writing a skeleton or animgraph file: only the clip's own DMX is written.
- Editing keyframe content for the owner: the panel writes the action as it is.

## Checks

- `tests/test_clips.py`: the write folder never equals the extraction, the
  written path is the `anims` layout, and the action filter escapes glob
  metacharacters so one clip name matches exactly one action.
- `tools/blender_clip_export_probe.py`: with PulseSrcOps enabled, one action is
  written, the file is non-empty and named after the clip, the row records it,
  the rig keeps its own action selection/subdir/export path, and the DMX imports
  back as an action of the same length with bone channels.
