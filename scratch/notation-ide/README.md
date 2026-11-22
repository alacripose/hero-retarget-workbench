# Notation IDE (scratch)

A proof workspace for one question: where did a shorthand rewrite take something out of the prose,
and what does the line look like when the rule is put back. It runs in a real window, on the family
stack: a Rust core compiled to wasm, three.js for the visual notation, and Qt6 for the window.

## Run

```sh
cd scratch/notation-ide
python window.py          # opens the Notation IDE window
```

The window starts its own server when the port is closed and stops only the server it started.
`node server.js` alone serves the same page at `http://127.0.0.1:5177` for a browser tab.

## How the live loop works

- **Paste prose into the left box.** Every non-empty line becomes a node on the grid, coloured by the
  crudity ladder: `whole`, `annotated`, `lossy`, `shorthand`.
- **The gaps are named.** A line is refused for a bold lead with no rule, a pointer where the
  reasoning was, a counter dump, a title with no verb, a number with no unit, or a line cut off
  mid-thought. Nothing is scored; the ladder is named.
- **The comment box sits under the prose.** Type there and press **Send comment**. The note reaches
  the same channel the agent reads, so the work can continue while the window stays open.
- **Repair a line.** Select a node, write the full sentence, press **Save the pair**. The pair is
  appended to `data/pairs.jsonl`, which is the training row for the Debian judge.

## Files

| path | role |
|---|---|
| `core/src/lib.rs` | the classifier in Rust, a scalar ABI with no allocator and no JSON |
| `public/core.js` | the page side of the ABI |
| `public/app.js` | the scene, the selection, the repair loop, the comment box |
| `window.py` | the Qt6 window, its server, and its `--grab` picture |
| `tools/build-wasm.mjs` | `cargo build --release --target wasm32-unknown-unknown` and a receipt |
| `tools/name_prose.py` | the gate that refuses shorthand names, across four surfaces |
| `tools/axis_push.sh` | witnesses the judge artifact with the Debian axis, blake3 named |
| `data/pairs.jsonl` | repair pairs, append only |
| `data/notes.json` | the live notes, both speakers |

## Checks

```sh
cargo test --manifest-path core/Cargo.toml     # 5 classifier claims
python tools/name_prose.py --selftest          # 13 planted names
python tools/name_prose.py --repo ../../       # 1052 names, 0 refused
node tools/build-wasm.mjs                      # wasm plus artifacts/wasm-build.json
```

## Digests

The family hashes with blake3. `name_prose.py --json` writes `artifacts/name-judge.json` and its
`artifacts/name-judge.blake3` sidecar.

The Debian axis recomputes `sha256` only, so a receipt names both: `expected` carries the blake3
digest and `observed` carries the sha256 the axis computed over the same bytes. The axis was not
edited to make the two look interchangeable.

## Not checked

The classifier judges the shape of a line, never whether the rule it names is true. The comment box
was confirmed in a window that is now open; the axis receipt was read from its own state endpoint,
not from a second machine.
