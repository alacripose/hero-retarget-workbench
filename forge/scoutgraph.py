"""Author a Deadlock AnimGraph 2 document from the port's own skeleton and clips.

The live `animgraphs/animgraph2/hero/*.vnmgraph` documents are fused: one `CNmGraphDocument` holding
every hero, each animation-pose node carrying an override per variation, and each variation in
`m_variationHierarchy` naming its own skeleton. This module writes a **standalone** document instead:
one variation (`Scout`), its skeleton, and only the port's clips — no override, no frank reference.

The field sets below are transcribed from the live documents (see `schema_inventory`), not guessed:
a node class, its pins, and the type-specific keys the tool accepts.

  python -m forge.scoutgraph --schema <a live graph>   # what the documents actually contain
"""
from __future__ import annotations

import argparse
import json
import re
import uuid
from pathlib import Path

KV3_HEADER = (
    "<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} "
    "format:generic:version{7412167c-06e9-4698-aff2-e63eb59037e7} -->\n"
)

# Every node class observed in the live hero graphs, with the keys found on the document, the flow
# graph, a state machine, its states and the clip-carrying pose node.
DOCUMENT_KEYS = ("_class", "m_nVersion", "m_pRootGraph", "m_variationHierarchy", "m_debugParameterSets", "m_dictionaryIDSetIDs")
FLOW_GRAPH_KEYS = ("_class", "m_ID", "m_nodes", "m_graphType", "m_viewOffset", "m_flViewZoom", "m_connections")
POSE_NODE_KEYS = (
    "_class",
    "m_ID",
    "m_name",
    "m_floatingComment",
    "m_position",
    "m_inputPins",
    "m_outputPins",
    "m_pDefaultVariationData",
    "m_overrides",
)
STATE_KEYS = (
    "m_type",
    "m_cloneSourceStateID",
    "m_stateEvents",
    "m_timedStateEvents",
    "m_events",
    "m_entryEvents",
    "m_executeEvents",
    "m_exitEvents",
    "m_timeRemainingEvents",
    "m_timeElapsedEvents",
    "m_bUseActualElapsedTimeInStateForTimedEvents",
)
NULL_ID = "00000000-0000-0000-0000-000000000000"


class GraphError(RuntimeError):
    """A refusal the caller can name: a graph that cannot be built as asked."""


def uid() -> str:
    return str(uuid.uuid4())


def dump(value, indent: int = 0) -> str:
    """kv3 text as the live documents write it: object members are newline-separated with **no**
    commas; array elements are comma-separated with none after the last. Short numeric arrays stay
    on one line (`m_position = [ 0.0, 0.0 ]`), everything else is one element per line.
    """
    pad = "\t" * indent
    if isinstance(value, dict):
        rows = [f"{pad}{{\n"]
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                rows.append(f"{pad}\t{key} = \n{dump(item, indent + 1)}")
            else:
                rows.append(f"{pad}\t{key} = {scalar(item)}\n")
        rows.append(f"{pad}}}\n")
        return "".join(rows)
    if isinstance(value, list):
        if not value:
            return f"{pad}[  ]\n"
        if len(value) <= 4 and all(not isinstance(item, (dict, list)) for item in value):
            return f"{pad}[ " + ", ".join(scalar(item) for item in value) + " ]\n"
        rows = [f"{pad}[\n"]
        for position, item in enumerate(value):
            piece = dump(item, indent + 1) if isinstance(item, (dict, list)) else f"{pad}\t{scalar(item)}\n"
            if position + 1 < len(value):
                piece = piece.rstrip("\n") + ",\n"
            rows.append(piece)
        rows.append(f"{pad}]\n")
        return "".join(rows)
    return f"{pad}{scalar(value)}\n"


def scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.1f}" if value == float(int(value)) else repr(value)
    if isinstance(value, (int,)):
        return str(value)
    if value is None:
        return "null"
    return f'"{value}"'


def pin(name: str, kind: str, *, dynamic: bool = False, multiple: bool = False) -> dict:
    return {
        "m_ID": uid(),
        "m_name": name,
        "m_type": kind,
        "m_bIsDynamicPin": dynamic,
        "m_bAllowMultipleOutConnections": multiple,
    }


def pose_node(name: str, clip: str, position: tuple[float, float]) -> dict:
    """`CNmGraphDocAnimationPoseNode`: one clip. The default variation *is* the only variation here."""
    return {
        "_class": "CNmGraphDocAnimationPoseNode",
        "m_ID": uid(),
        "m_name": name,
        "m_floatingComment": "",
        "m_position": [float(position[0]), float(position[1])],
        "m_inputPins": [pin("Time", "Float")],
        "m_outputPins": [pin("Pose", "Pose")],
        "m_pDefaultVariationData": {
            "_class": "CNmGraphDocAnimationPoseNode::CData",
            "m_clip": clip,
            "m_variationTimeValue": -1.0,
        },
        "m_overrides": [],
        # The loader reads these on every pose node; a document without them access-violates instead
        # of reporting a missing field (measured: artifacts/scout-graph/bisect.py, 2026-11-24).
        "m_defaultResourceName": "",
        "m_inputTimeRemapRange": {"m_flMin": 0.0, "m_flMax": 1.0},
        "m_fixedTimeValue": 0.0,
        "m_useFramesAsInput": False,
    }


def pose_result_node(position: tuple[float, float]) -> dict:
    return {
        "_class": "CNmGraphDocPoseResultNode",
        "m_ID": uid(),
        "m_name": "",
        "m_floatingComment": "",
        "m_position": [float(position[0]), float(position[1])],
        "m_inputPins": [pin("Out", "Pose")],
        "m_outputPins": [],
        "m_resultType": "Pose",
    }


def connection(from_node: dict, to_node: dict, *, output: int = 0, input_index: int = 0) -> dict:
    return {
        "m_ID": uid(),
        "m_fromNodeID": from_node["m_ID"],
        "m_outputPinID": from_node["m_outputPins"][output]["m_ID"],
        "m_toNodeID": to_node["m_ID"],
        "m_inputPinID": to_node["m_inputPins"][input_index]["m_ID"],
    }


def flow_graph(nodes: list[dict], connections: list[dict], graph_type: str) -> dict:
    return {
        "_class": "CNmGraphDocFlowGraph",
        "m_ID": uid(),
        "m_nodes": nodes,
        "m_graphType": graph_type,
        "m_viewOffset": [0.0, 0.0],
        "m_flViewZoom": 1.0,
        "m_connections": connections,
    }


def state_layer_data_node(position: tuple[float, float] = (0.0, 0.0)) -> dict:
    """The state's layer data node: weight, root-motion weight and bone mask, result type Special.

    Every live state carries one in its `m_pSecondaryGraph`; the loader reads the state's layer slot
    through it, so an empty secondary graph is not equivalent.
    """
    return {
        "_class": "CNmGraphDocStateLayerDataNode",
        "m_ID": uid(),
        "m_name": "",
        "m_floatingComment": "",
        "m_position": [float(position[0]), float(position[1])],
        "m_inputPins": [
            pin("Layer Weight", "Float"),
            pin("Root Motion Weight", "Float"),
            pin("Layer Mask", "BoneMask"),
        ],
        "m_outputPins": [],
        "m_resultType": "Special",
    }


def state_node(name: str, clip: str, position: tuple[float, float], *, pose_name: str = "") -> dict:
    """A `CNmGraphDocStateNode` of type `BlendTreeState` holding one clip on its pose result.

    ``pose_name`` names the pose node inside the state, which is how an aim pose keeps a name of its
    own (`aim_<clip>`) while still being reachable from the graph's single output.
    """
    source = pose_node(pose_name or f"{name} clip", clip, (0.0, 0.0))
    result = pose_result_node((400.0, 0.0))
    state = {
        "_class": "CNmGraphDocStateNode",
        "m_ID": uid(),
        "m_name": name,
        "m_floatingComment": "",
        "m_position": [float(position[0]), float(position[1])],
        "m_pChildGraph": flow_graph([source, result], [connection(source, result)], "ValueTree"),
        # A state carries a second graph slot holding its layer data node; the compiler reads it.
        "m_pSecondaryGraph": flow_graph(
            [state_layer_data_node((0.0, 120.0)), pose_result_node((520.0, 120.0))], [], "ValueTree"
        ),
        "m_type": "BlendTreeState",
        "m_cloneSourceStateID": NULL_ID,
        "m_stateEvents": [],
        "m_timedStateEvents": [],
        "m_events": [],
        "m_entryEvents": [],
        "m_executeEvents": [],
        "m_exitEvents": [],
        "m_timeRemainingEvents": [],
        "m_timeElapsedEvents": [],
        "m_bUseActualElapsedTimeInStateForTimedEvents": False,
    }
    return state


def state_machine_node(name: str, states: list[dict], position: tuple[float, float], *, conduits: bool = True) -> dict:
    if not states:
        raise GraphError("state-machine-empty: a state machine needs at least one state")
    nodes = list(states)
    if conduits:
        nodes.append(entry_override_conduit(states, (0.0, 0.0)))
        nodes.append(global_transition_conduit(states, (400.0, 0.0)))
    child = {
        "_class": "CNmGraphDocStateMachineGraph",
        "m_ID": uid(),
        "m_nodes": nodes,
        "m_graphType": "StateMachine",
        "m_viewOffset": [0.0, 0.0],
        "m_flViewZoom": 1.0,
        # Without an entry state the machine has no state to start in, and the loader crashes.
        "m_entryStateID": states[0]["m_ID"],
    }
    return {
        "_class": "CNmGraphDocStateMachineNode",
        "m_ID": uid(),
        "m_name": name,
        "m_floatingComment": "",
        "m_position": [float(position[0]), float(position[1])],
        "m_inputPins": [],
        "m_outputPins": [pin("Pose", "Pose")],
        "m_pChildGraph": child,
    }


def entry_override_conduit(states: list[dict], position: tuple[float, float]) -> dict:
    """The state machine's entry-state override conduit, with one Bool pin per state.

    A `CNmGraphDocStateMachineGraph` in the live documents carries this conduit beside its states and
    keeps `m_pinToStateMapping` aligned with the condition pins; a machine without it access-violates
    the loader (measured, 2026-11-24).
    """
    conditions = {
        "_class": "CNmGraphDocEntryStateOverrideConditionsNode",
        "m_ID": uid(),
        "m_name": "",
        "m_floatingComment": "",
        "m_position": [0.0, 0.0],
        "m_inputPins": [pin(state["m_name"], "Bool", dynamic=True) for state in states],
        "m_outputPins": [],
        "m_resultType": "Special",
        "m_pinToStateMapping": [state["m_ID"] for state in states],
    }
    result = pose_result_node((520.0, 0.0))
    return {
        "_class": "CNmGraphDocEntryStateOverrideConduitNode",
        "m_ID": uid(),
        "m_name": "",
        "m_floatingComment": "",
        "m_position": [float(position[0]), float(position[1])],
        "m_pSecondaryGraph": flow_graph([conditions, result], [], "ValueTree"),
    }


def global_transition_node(state: dict, position: tuple[float, float]) -> dict:
    """A global transition into one state: the beside-the-states node the conduit's graph holds.

    Its keys and defaults are the live document's; the Condition pin is left unconnected, which means
    the transition is authored but not triggered until a condition node drives it.
    """
    return {
        "_class": "CNmGraphDocGlobalTransitionNode",
        "m_ID": uid(),
        "m_name": state["m_name"],
        "m_floatingComment": "",
        "m_position": [float(position[0]), float(position[1])],
        "m_inputPins": [
            pin("Condition", "Bool"),
            pin("Duration Override", "Float"),
            pin("Sync Event Override", "Float"),
            pin("Start Bone Mask", "BoneMask"),
            pin("Target Sync ID", "ID"),
        ],
        "m_outputPins": [],
        "m_resultType": "Special",
        "m_flDurationSeconds": 0.1,
        "m_bClampDurationToSource": False,
        "m_rootMotionBlend": "Blend",
        "m_blendWeightEasing": "Linear",
        "m_flBoneMaskBlendInTimePercentage": 0.33,
        "m_timeMatchMode": "None",
        "m_flTimeOffset": 0.0,
        "m_bCanBeForced": False,
        "m_stateID": state["m_ID"],
    }


def global_transition_conduit(states: list[dict], position: tuple[float, float]) -> dict:
    """The machine's global transition conduit; the loader expects this slot beside the entry one."""
    nodes = [global_transition_node(state, (1040.0, 140.0 * index)) for index, state in enumerate(states)]
    result = pose_result_node((520.0, 0.0))
    graph = {
        "_class": "CNmGraphDocFlowGraph",
        "m_ID": uid(),
        "m_nodes": nodes + [result],
        "m_graphType": "GlobalTransitionConduit",
        "m_viewOffset": [0.0, 0.0],
        "m_flViewZoom": 1.0,
        "m_connections": [],
    }
    return {
        "_class": "CNmGraphDocGlobalTransitionConduitNode",
        "m_ID": uid(),
        "m_name": "",
        "m_floatingComment": "",
        "m_position": [float(position[0]), float(position[1])],
        "m_pSecondaryGraph": graph,
    }


def document(nodes: list[dict], connections: list[dict], *, variation: str, skeleton: str) -> dict:
    return {
        "_class": "CNmGraphDocument",
        "m_nVersion": 0,
        "m_pRootGraph": flow_graph(nodes, connections, "BlendTree"),
        "m_variationHierarchy": {
            "m_variations": [{"m_ID": variation, "m_parentID": "", "m_skeleton": skeleton}],
        },
        "m_debugParameterSets": [],
        "m_dictionaryIDSetIDs": [],
    }


def build_scout_graph(*, variation: str, skeleton: str, clips: dict[str, str], states: list[str]) -> dict:
    """The port's graph: motion clips as real states, the aim clips as named poses.

    ``clips`` maps a name to a clip path and ``states`` names the motion clips. Each motion clip becomes
    a `state_<name>` state carrying the clip. Each aim clip becomes an `aim_state_<name>` state whose
    pose node is named `aim_<name>`: a pose has to be reachable from the graph's single output to
    survive compilation, and the compiler prunes a pose node that feeds a result of its own (measured),
    so the poses live in states of their own rather than beside the machine.
    """
    missing = [name for name in states if name not in clips]
    if missing:
        raise GraphError(f"graph-clip-missing: {', '.join(missing)}")
    if not states:
        raise GraphError("graph-states-empty: a state machine needs at least one state")

    rows = [state_node(f"state_{name}", clips[name], (0.0, 140.0 * index)) for index, name in enumerate(states)]
    aim = [name for name in clips if name not in states]
    for index, name in enumerate(aim):
        rows.append(
            state_node(
                f"aim_state_{name}",
                clips[name],
                (0.0, 140.0 * (len(states) + index)),
                pose_name=f"aim_{name}",
            )
        )
    machine = state_machine_node("ScoutMotion", rows, (0.0, 0.0))
    result = pose_result_node((900.0, 0.0))
    return document([machine, result], [connection(machine, result)], variation=variation, skeleton=skeleton)


def write_document(payload: dict, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(KV3_HEADER + dump(payload), encoding="utf-8")
    return destination


def graph_facts(text: str) -> dict:
    """What a graph document says it is: its clip paths, skeleton references, named states and poses.

    The same reader is applied to the authored document and to the decompiled compiled graph, so the
    verify step compares what was written with what the compiler produced using one definition.
    """
    return {
        "nodes": len(re.findall(r'_class = "CNmGraphDoc[A-Za-z]+Node"', text)),
        "clips": sorted(set(re.findall(r'm_clip = "([^"]+)"', text))),
        "skeletons": sorted(set(re.findall(r'm_skeleton = "([^"]+)"', text))),
        "states": sorted(set(re.findall(r'm_name = "(state_[A-Za-z0-9_]+)"', text))),
        "aim_states": sorted(set(re.findall(r'm_name = "(aim_state_[A-Za-z0-9_]+)"', text))),
        "aim_poses": sorted(set(re.findall(r'm_name = "(aim_Scout_[A-Za-z0-9_]+)"', text))),
        "frank_matches": text.lower().count("frank"),
    }


def scan_for(paths: list[Path], needle: str) -> dict:
    """How many times a string appears in each file, for a claim that has to be measured per file."""
    rows = {}
    for path in paths:
        if not Path(path).is_file():
            continue
        data = Path(path).read_bytes().lower()
        rows[str(path)] = data.count(needle.encode("utf-8").lower())
    return rows


def schema_inventory(text: str) -> dict:
    """What a document actually contains: its class, per-node-class counts and field sets."""
    classes = sorted(set(re.findall(r'_class = "([A-Za-z0-9_:]+)"', text)))
    counts: dict[str, int] = {}
    for name in classes:
        counts[name] = len(re.findall(r'_class = "%s"' % re.escape(name), text))
    keys: dict[str, list[str]] = {}
    for name in classes:
        found = re.search(r'_class = "%s"\n((?:\t*m_[A-Za-z0-9_]+ = .*\n)+)' % re.escape(name), text)
        if found:
            keys[name] = re.findall(r"m_([A-Za-z0-9_]+) =", found.group(1))
    return {
        "classes": counts,
        "keys": keys,
        "clip_references": len(re.findall(r'm_clip = "', text)),
        "skeleton_references": len(re.findall(r"m_skeleton = ", text)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", help="a live graph to inventory")
    args = parser.parse_args()
    if not args.schema:
        parser.print_help()
        return 2
    text = Path(args.schema).read_text(encoding="utf-8", errors="replace")
    print(json.dumps(schema_inventory(text), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
