# Architecture

## Flow

```
live Deadlock install
  game/citadel/pak01_dir.vpk
  game/citadel/gameinfo.gi
          │
          ▼
Source 2 Viewer (CLI or GUI)
  models/heroes_staging/<hero>/<hero>.vmdl_c
          │
          ├── hero body DMX ──────────────► Blender addon
          ├── hero materials (.vmat) ─────► stage (verbatim)
          └── hero vmdl ──────────────────► stage (byte-for-byte)
                                                │
custom model (glTF/GLB/FBX/OBJ/DMX) ──► fit ──► retarget ──► PulseSrcOps DMX
                                                │
                                                ▼
                              content/citadel_addons/<addon>/
                                models/.../<hero>.vmdl       (unchanged)
                                models/.../<body>.dmx        (custom)
                                materials/.../*.vmat         (copied)
                                stage.json                   (hashes)
                                                │
                                                ▼
                              CSDK13 resourcecompiler.exe -i <vmdl>
```

## Responsibilities

### `forge/paths.py`

Reads the Steam library manifest and explicit environment overrides. It finds
the live game by `game/citadel/gameinfo.gi` + `pak01_dir.vpk`, then reads build
and version date from `steam.inf`. It finds S2V, Blender, and CSDK13; missing
paths are reported, not guessed.

### `forge/live.py`

Wraps S2V:

- `--vpk_list` for heroes;
- `--vpk_filepath <hero.vmdl_c> -o <dir> -d` for the extraction;
- inventories `.vmdl`, `.dmx`, `.gltf`, `.vmat` files.

It does **not** read the vmdl. The extraction is the source of truth.

### `forge/axis.py`

Defines exact permutation matrices for Blender, Source 2, and glTF. Positions and
normals use the matrix; weights and joint indices do not. Mirrors have a negative
determinant and require an explicit preset name.

### `forge/names.py`

Matches custom vertex-group names to target bone names:

1. exact,
2. declared alias,
3. normalized only when exactly one target matches.

No nearest-bone guessing. Ambiguous mappings and unmatched groups are returned
to the operator for display.

### `forge/stage.py`

Builds the compiler handoff:

- creates `content/citadel_addons/<addon>/`;
- copies the vmdl unchanged and checks its SHA-256;
- writes the custom DMX at the logical target path;
- copies material files and any requested extras;
- writes `stage.json` with `vmdl_modified: false`.

It refuses path traversal, wrong file types, blank addon names, and any vmdl
hash change.

### `forge/compile.py`

Copies the staged addon into a unique temporary CSDK build folder under
`content/citadel_addons/` because that is where `resourcecompiler` resolves
content, then runs the compiler from the SDK content root. It captures
stdout/stderr and writes a log. On success it copies only compiled `_c` files
(the `.vmdl_c` plus generated `.vmat_c`/`.vtex_c`) back under
`<stage>/compiled/<addon>/`; on failure it preserves the previous compiled
output. In `finally` it deletes both the temporary content folder and its
`game/citadel_addons/<build>` counterpart. It does not leave a source mirror in
CSDK and does not alter the staged vmdl.

### Blender addon

`blender/deadlock_model_forge/` is an Operate-mode sidebar:

- hero detection/extraction and vmdl selection;
- hero body import through PulseSrcOps;
- custom model import (native glTF/FBX/OBJ plus Pulse DMX);
- fit and weight mapping/transfer;
- hero material assignment;
- DMX export and stage;
- compiler action.

The exported mesh is temporarily named after the target DMX stem because
PulseSrcOps names its output from the exported object. The original name is
restored in `finally`.

## Boundary

Everything above the stage is asset preparation. The vmdl is a black box. The
only model file the addon authors is the replacement DMX; the only material
files it handles are copied vmat files. There is intentionally no parser for
vmdl or vmat, and no model interchange format.
