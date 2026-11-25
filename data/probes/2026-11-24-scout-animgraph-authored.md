# 2026-11-24 — Scout's AnimGraph 2, authored and compiled

The graph step is built. The graph is a new `CNmGraphDocument` written by the forge from the schema the
live documents carry, over the port's own skeleton and the four port clips, compiled by the citadel
`resourcecompiler` with **0 failures**, and proved from the compiled artifact rather than the source.

## What the tool actually accepts (dumped, not guessed)

`python tools/scout_graph.py schema` reads the live documents and records the classes and keys:

| document | classes | clip refs | skeleton refs |
| --- | --- | --- | --- |
| `hero_aim.vnmgraph` | 24 | 2,532 | 142 |
| `hero.vnmgraph` | 38 | 0 | 52 |

The shapes the authored document now copies:

- `CNmGraphDocument` — `m_nVersion`, `m_pRootGraph`, `m_variationHierarchy`, `m_debugParameterSets`,
  `m_dictionaryIDSetIDs`.
- `CNmGraphDocFlowGraph` — `m_ID`, `m_nodes`, `m_graphType`, `m_viewOffset`, `m_flViewZoom`, `m_connections`.
- `CNmGraphDocAnimationPoseNode` — pins, `m_pDefaultVariationData { m_clip, m_variationTimeValue }`,
  `m_overrides`, then `m_defaultResourceName`, `m_inputTimeRemapRange`, `m_fixedTimeValue`,
  `m_useFramesAsInput`.
- `CNmGraphDocStateNode` — `m_pChildGraph` (the pose logic), `m_pSecondaryGraph` (its
  `CNmGraphDocStateLayerDataNode`), `m_type = "BlendTreeState"`, the six event arrays, and the timed-event flag.
- `CNmGraphDocStateMachineGraph` — `m_nodes`, `m_graphType = "StateMachine"`, `m_entryStateID`.
  Its nodes are the states **plus** a `CNmGraphDocEntryStateOverrideConduitNode` (conditions node with
  `m_pinToStateMapping`) and a `CNmGraphDocGlobalTransitionConduitNode` (one `CNmGraphDocGlobalTransitionNode`
  per state, each carrying `m_stateID`).
- `CNmGraphDocPoseResultNode` — `m_resultType = "Pose"` and one Pose input pin.

## Traps, kept in code and in tests

Each of these made the compiler **access-violate** (`0xC0000005`) with no message; `artifacts/scout-graph/bisect.py`
is the kept probe that found them, one variant at a time.

1. **The root variation must be `Default`.** A hierarchy whose root is named `Scout` sends the compiler
   looking for `scout.vnmgraph+scout.vnmgraph` and crashes when it is absent. The variation is `Default`
   and carries Scout's skeleton; the nodes carry Scout's names.
2. **A state machine needs the global transition conduit.** States plus the entry conduit compile to a
   crash; adding the global transition conduit compiled (`07-machine-default`, 2,088 B).
3. **A state's second graph slot is not optional.** It holds the `CNmGraphDocStateLayerDataNode`.
4. **A pose node carries four fields past its overrides** (`m_defaultResourceName`, the time remap range,
   `m_fixedTimeValue`, `m_useFramesAsInput`); absent, the loader dereferences null.
5. **A Pose input pin takes one connection, and unreachable pose nodes are pruned.** Aim pose nodes
   wired straight into the root's result were dropped from the compiled graph (2,227 B, `aim poses []`);
   they survive inside states of their own.

## The graph as built

`artifacts/scout-graph/models/heroes_wip/scout/scout.vnmgraph` — 35,702 B, 31 nodes, 23,070 B in the first
build, 4 clip references, **0 frank references**.

| branch | node | clip | frames |
| --- | --- | --- | --- |
| motion state | `state_Scout_Attack` | `clips/Scout_Attack.vnmclip` (from `AttackStand_PRIMARY`) | 21, moving |
| motion state | `state_Scout_Reload` | `clips/Scout_Reload.vnmclip` (from `PRIMARY_reload_loop`) | 20, moving |
| aim state | `aim_state_Scout_AimIdle` → pose `aim_Scout_AimIdle` | `clips/Scout_AimIdle.vnmclip` (`PRIMARY_aimmatrix_idle`) | 2, pose |
| aim state | `aim_state_Scout_AimRun` → pose `aim_Scout_AimRun` | `clips/Scout_AimRun.vnmclip` (`PRIMARY_aimmatrix_run`) | 2, pose |

## Compiled, and proved from the artifact

- `python tools/scout_graph.py compile` — **5/5 documents**: four clips (4,096–4,099 B each) and
  `scout.vnmgraph_c` **2,512 B**, `OK: 1 compiled, 0 failed, 0 skipped`.
- `python tools/scout_graph.py verify` — decompiles `scout.vnmgraph_c` (2,512 B) back to a 30,255 B
  document and reads it:
  - all four clips present, each at **78 channels**;
  - motion states `state_Scout_Attack`, `state_Scout_Reload`;
  - aim states `aim_state_Scout_AimIdle`, `aim_state_Scout_AimRun` with pose nodes `aim_Scout_AimIdle`,
    `aim_Scout_AimRun`;
  - skeleton named (`models/heroes_wip/scout/scout.vnmskel`), **78 joints**, and **78 bones** in the
    compiled skeleton;
  - `frank` absent from the decompiled text and from the compiled bytes.
  - `RESULT: PASS`.

## The toolchain, measured

The Dota 2 tools branch ships `dmxconvert.exe` (used for every clip DMX in this slice) and a
`resourcecompiler.exe`, but `probe-toolchain` shows that branch cannot compile this graph: pointed at
`game/dota` it fails loading `materials/error.vmat_c` and `surfaceproperties/surfaceproperties.vbc_c` and
reports no result — the branch's game data is not present in this install. The `.vnmgraph` compile is
therefore done by the same AnimGraph 2 compiler against the citadel game (`game/citadel`), which is what
produces `scout.vnmgraph_c`; the Dota branch's contribution here is the DMX conversion path.

## What the app now says

Probe **11/11**, steps: `inventory pass`, `skeleton pass`, `clips pass`, `graph pass` (`2,512 B compiled
graph, 4/4 port clips, 2 motion states, 2 aim poses, 78 joints`), and refusals by name: `pack-not-built`,
`hero-not-registered`, `mesh-not-built`, `not-observed`. The page's counts carry
`graph_compiled_documents`, `graph_clips`, `graph_joints`.

## Still refused

- **pack** — no `_dir.vpk` of this rig exists.
- **hero** — no model names this graph, so there is no hero to register.
- **mesh** — the port has no mesh SMD; `ref.smd` has no `triangles` block, so no render geometry exists.
- **in-game** — nothing was launched; the earlier addon crashed the client and stays disabled.

## Reproduce

```
python tools/scout_graph.py schema
python tools/scout_graph.py build
python tools/scout_graph.py compile --csdk C:/Users/ala/Downloads/Reduced_CSDK_13
python tools/scout_graph.py verify  --csdk C:/Users/ala/Downloads/Reduced_CSDK_13
python artifacts/scout-graph/bisect.py --csdk C:/Users/ala/Downloads/Reduced_CSDK_13
```
