"""The mapping-rule panel's operators and the one rule a typed row teaches.

A rule is written by the user: a pattern, a target and the state the answered row
gets. The only rule this addon adds on its own is the one implied by a row the
user just typed — ``elbow_L`` to ``arm_lower_L`` — which is their own mapping, not
a guess about the hero. ``suppressed()`` keeps programmatic batches from looking
like that.
"""
from __future__ import annotations

import contextlib
import time

import bpy
from bpy.types import Operator
from forge import bonerules

from . import core, poseview, proofing

_DEPTH = 0  # nesting guard: an auto-fill must not start another auto-fill

# A batch of rule answers is spread over timer ticks. One tick is the longest the
# main thread may be held, so the viewport keeps drawing while hundreds of rows
# are answered; the plan is computed once, up front.
_CHUNK = 150
_FILL: dict[str, object] = {
    "settings": None,
    "plan": {},
    "done": 0,
    "total": 0,
    "chunks": [],
    "chunk": _CHUNK,
    "timer": None,
}

_STATE_LABELS = {
    "MAPPED": "Mapped",
    "EXTRA": "Extra",
    "IGNORED": "Ignored",
}


@contextlib.contextmanager
def suppressed():
    """Run a batch of map writes without re-entering the rule callbacks."""
    global _DEPTH
    _DEPTH += 1
    try:
        yield
    finally:
        _DEPTH -= 1


def is_suppressed() -> bool:
    return _DEPTH > 0


def mapping(settings) -> dict[str, str]:
    """The rows the solver would read: mapped, with a source and a target."""
    return {
        entry.source: entry.target
        for entry in settings.bone_map
        if entry.state == "MAPPED" and entry.source and entry.target
    }


def target_names(settings) -> list[str]:
    armature = settings.target_armature
    if armature is None:
        return []
    return [bone.name for bone in armature.data.bones]


def rule_of(row) -> bonerules.Rule:
    """A panel row as the pure rule the matcher reads."""
    return bonerules.Rule(
        source=row.source,
        target=row.target,
        regex=row.regex,
        side_aware=row.side_aware,
        state=row.state if row.state in bonerules.STATES else "MAPPED",
        origin=row.origin,
        enabled=row.enabled,
        support=row.support,
    )


def panel_rules(settings) -> list[bonerules.Rule]:
    """Every enabled-or-not rule the user has in this file, in match order."""
    return bonerules.ordered(
        [rule_of(row) for row in settings.bone_rules if row.source and (row.target or row.state != "MAPPED")]
    )


def store(settings, rules: list[bonerules.Rule]) -> int:
    """Merge learned rules into the panel rows without touching a user's own row."""
    existing = {
        (row.source.lower(), row.target.lower(), bool(row.regex), row.state): row
        for row in settings.bone_rules
    }
    with suppressed():
        for rule in rules:
            key = (rule.source.lower(), rule.target.lower(), bool(rule.regex), rule.state)
            row = existing.get(key)
            if row is None:
                row = settings.bone_rules.add()
                row.source = rule.source
                row.target = rule.target
                row.regex = rule.regex
                row.side_aware = rule.side_aware
                row.state = rule.state
                row.origin = rule.origin
                row.support = rule.support
                existing[key] = row
            else:
                row.support = max(int(row.support), int(rule.support))
    return len(settings.bone_rules)


def learn_from_map(settings) -> int:
    """Learn the side rules the mapped rows already imply."""
    learned = bonerules.learn(mapping(settings))
    store(settings, learned)
    return len(learned)


def rows(settings) -> list[dict]:
    """The bone map as plain dicts, for the pure rule module."""
    return [
        {
            "source": entry.source,
            "state": entry.state,
            "target": entry.target,
            "note": entry.note,
            "scanned": entry.scanned,
            "scanned_state": entry.scanned_state,
        }
        for entry in settings.bone_map
    ]


def remembered(settings) -> dict[str, tuple[str, str, str]]:
    """Rows the user answered themselves, which neither a scan nor a rule may replace."""
    return bonerules.remembered(rows(settings))


def plan_fill(settings) -> dict:
    """What the rules answer right now: source -> suggestion, user rows excluded."""
    found = bonerules.suggest(
        panel_rules(settings),
        [entry.source for entry in settings.bone_map if entry.source],
        target_names(settings),
        mapping(settings),
    )
    kept = set(remembered(settings))
    return {source: hit for source, hit in found.items() if source not in kept}


def _entry(settings, source: str):
    for entry in settings.bone_map:
        if entry.source == source:
            return entry
    return None


def _answer(entry, hit) -> None:
    if hit.state == "EXTRA":
        entry.state = "EXTRA"
        entry.target = entry.source
    elif hit.state == "IGNORED":
        entry.state = "IGNORED"
        entry.target = ""
    else:
        entry.state = "MAPPED"
        entry.target = hit.target
    entry.note = f"rule {hit.label}"
    # What a rule wrote is not a decision the user made: a rescan may answer the
    # row again if the rule changes.
    entry.scanned = entry.target
    entry.scanned_state = entry.state


def fill(settings) -> int:
    """Apply the rules now, in this call. Panels use ``start_fill`` instead."""
    plan = plan_fill(settings)
    changed = 0
    with suppressed():
        for source, hit in plan.items():
            entry = _entry(settings, source)
            if entry is None:
                continue
            _answer(entry, hit)
            changed += 1
    return changed


def _finish_fill(settings, cancelled: bool = False) -> None:
    timer = _FILL.get("timer")
    if timer is not None:
        try:
            bpy.app.timers.unregister(timer)
        except ValueError:
            pass
    _FILL["timer"] = None
    _FILL["plan"] = {}
    if settings is None:
        return
    settings.rule_fill_running = False
    if cancelled:
        core.set_status(settings, f"Stopped after answering {_FILL['done']} rows", "INFO")
        return
    answered = int(_FILL.get("done") or 0)
    left = sum(1 for entry in settings.bone_map if entry.state == "UNMATCHED")
    # One pose refresh for the whole batch, never one per row.
    try:
        poseview.refresh(settings)
    except Exception:
        pass
    proofing.bump_tick(settings)
    core.set_status(
        settings,
        f"Rules answered {answered} rows; {left} still need a decision"
        if left
        else f"Rules answered {answered} rows; every row is answered",
        "WARN" if left else "OK",
    )


def _fill_tick():
    settings = _FILL.get("settings")
    plan = _FILL.get("plan") or {}
    if settings is None or not plan:
        _finish_fill(settings)
        return None
    started = time.monotonic()
    sources = list(plan)[: int(_FILL.get("chunk") or _CHUNK)]
    with suppressed():
        for source in sources:
            hit = plan.pop(source, None)
            entry = _entry(settings, source)
            if hit is None or entry is None:
                continue
            _answer(entry, hit)
            _FILL["done"] = int(_FILL["done"]) + 1
    settings.rule_fill_done = int(_FILL["done"])
    _FILL["chunks"].append(round((time.monotonic() - started) * 1000.0, 1))
    if plan:
        core.set_status(settings, f"Rules {settings.rule_fill_done}/{settings.rule_fill_total}", "BUSY")
        return 0.0
    _finish_fill(settings)
    return None


def start_fill(settings, chunk: int | None = None) -> int:
    """Plan the rule answers and apply them a chunk per timer tick."""
    timer = _FILL.get("timer")
    if timer is not None:
        try:
            bpy.app.timers.unregister(timer)
        except ValueError:
            pass
    _FILL["timer"] = None
    _FILL["plan"] = {}
    plan = plan_fill(settings)
    _FILL.update(
        settings=settings,
        plan=dict(plan),
        done=0,
        total=len(plan),
        chunks=[],
        chunk=max(1, int(chunk or _CHUNK)),
    )
    settings.rule_fill_total = len(plan)
    settings.rule_fill_done = 0
    settings.rule_fill_running = bool(plan)
    if not plan:
        return 0
    _FILL["timer"] = bpy.app.timers.register(_fill_tick, first_interval=0.0, persistent=True)
    return len(plan)


def cancel_fill(settings=None, quiet: bool = False) -> None:
    if _FILL.get("timer") is None and not _FILL.get("plan"):
        return
    _finish_fill(_FILL.get("settings") if settings is None else settings, cancelled=not quiet)


def flush_fill(settings) -> dict:
    """Run a scheduled fill to completion now — headless probes and tests."""
    if _FILL.get("settings") is not settings or (not _FILL.get("plan") and _FILL.get("timer") is None):
        start_fill(settings)
    while _FILL.get("plan"):
        _fill_tick()
    return {"done": int(_FILL.get("done") or 0), "chunks": list(_FILL.get("chunks") or [])}


def is_filling() -> bool:
    return _FILL.get("timer") is not None


def auto_fill(settings, entry) -> int:
    """File the rule the typed row implies and place its opposite-side row.

    Called from the target field's update callback, so the user sees ``elbow_R``
    answer the moment ``elbow_L`` is given a target. Only the exact mirror row is
    written here; applying the rest of the rules stays an explicit action.
    """
    if is_suppressed():
        return 0
    if entry is None or entry.state != "MAPPED" or not entry.source or not entry.target:
        return 0
    learned = bonerules.learn({entry.source: entry.target})
    if not learned:
        return 0
    store(settings, learned)
    partner = bonerules.mirror(entry.source)
    if partner == entry.source:
        return 0
    _stem, side = bonerules.split_side(partner)
    if not side:
        return 0
    placed = 0
    with suppressed():
        for row in settings.bone_map:
            if row is entry or row.source != partner:
                continue
            if row.state == "MAPPED" and row.target:
                continue
            row.target = bonerules.set_side(entry.target, side)
            row.state = "MAPPED"
            row.note = f"mirror of {entry.source}"
            row.scanned = row.target
            row.scanned_state = row.state
            placed += 1
    return placed


def rule_from_entry(settings, entry) -> object | None:
    """Write a rule that reproduces the row the user just mapped.

    A paired row becomes a side rule on its stem; a one-sided row becomes a
    prefix rule ending in ``*``, which is the form the panel shows for it.
    """
    if entry is None or not entry.source:
        return None
    source_stem, source_side = bonerules.split_side(entry.source)
    target_stem, target_side = bonerules.split_side(entry.target or "")
    side_aware = bool(source_side and target_side and source_side == target_side)
    source = source_stem if side_aware else f"{entry.source}*"
    rule = bonerules.Rule(
        source=source,
        target=entry.target or "",
        side_aware=side_aware,
        state=entry.state if entry.state in bonerules.STATES else "MAPPED",
        origin="row",
        support=1,
    )
    store(settings, [rule])
    settings.bone_rule_index = max(0, len(settings.bone_rules) - 1)
    return rule


def preview(settings, row) -> list[str]:
    """Unanswered rows the selected rule would catch right now."""
    rule = rule_of(row)
    if not rule.source:
        return []
    existing = mapping(settings)
    return [
        entry.source
        for entry in settings.bone_map
        if entry.source and not existing.get(entry.source) and bonerules.matches(rule, entry.source)
    ]


class DMF_OT_learn_rules(Operator):
    bl_idname = "dmf.learn_rules"
    bl_label = "Learn From Mapped Rows"
    bl_description = "Write the side rule each mapped left/right row already implies"

    def execute(self, context):
        settings = context.scene.dmf
        if settings.target_armature is None:
            self.report({"ERROR"}, "Import the hero skeleton first")
            core.set_status(settings, "Rules need the hero skeleton's bone names", "WARN")
            return {"CANCELLED"}
        count = learn_from_map(settings)
        core.set_status(
            settings,
            f"{count} rules learned from the mapped rows" if count else "No paired row yet; map a left/right bone first",
            "OK" if count else "WARN",
        )
        return {"FINISHED"}


class DMF_OT_stop_rules(Operator):
    bl_idname = "dmf.stop_rules"
    bl_label = "Stop Answering"
    bl_description = "Stop the rule fill; the rows already answered keep their targets"

    def execute(self, context):
        settings = context.scene.dmf
        cancel_fill(settings)
        return {"FINISHED"}


class DMF_OT_apply_rules(Operator):
    bl_idname = "dmf.apply_rules"
    bl_label = "Apply Rules"
    bl_description = "Apply every rule to the rows that have no target; a mapped row is never overwritten"

    def execute(self, context):
        settings = context.scene.dmf
        if not settings.bone_map:
            self.report({"ERROR"}, "Scan the bone map first")
            return {"CANCELLED"}
        try:
            changed = start_fill(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        left = sum(1 for row in settings.bone_map if row.state == "UNMATCHED")
        if changed:
            core.set_status(settings, f"Answering {changed} rows from the rules", "BUSY")
        else:
            core.set_status(settings, "No rule answered an unanswered row", "WARN")
        return {"FINISHED"}


class DMF_OT_add_rule(Operator):
    bl_idname = "dmf.add_rule"
    bl_label = "Add Rule"
    bl_description = "Add an empty rule row: a pattern, a target, and the row state it sets"

    def execute(self, context):
        settings = context.scene.dmf
        row = settings.bone_rules.add()
        row.source = ""
        row.target = ""
        row.regex = False
        row.side_aware = True
        row.state = "MAPPED"
        row.origin = "user"
        row.enabled = True
        row.support = 0
        settings.bone_rule_index = len(settings.bone_rules) - 1
        core.set_status(settings, "New rule: type a pattern such as Sp_Hi_* and its target", "INFO")
        return {"FINISHED"}


class DMF_OT_rule_from_row(Operator):
    bl_idname = "dmf.rule_from_row"
    bl_label = "Rule From Row"
    bl_description = "Write a rule that reproduces the selected bone-map row"

    def execute(self, context):
        settings = context.scene.dmf
        if not settings.bone_map:
            self.report({"ERROR"}, "Choose a bone-map row first")
            return {"CANCELLED"}
        index = max(0, min(settings.bone_map_index, len(settings.bone_map) - 1))
        entry = settings.bone_map[index]
        rule = rule_from_entry(settings, entry)
        if rule is None:
            self.report({"ERROR"}, "The row has no source name")
            return {"CANCELLED"}
        core.set_status(settings, f"Rule {rule.source} → {rule.target or rule.state} written from {entry.source}", "OK")
        return {"FINISHED"}


class DMF_OT_remove_rule(Operator):
    bl_idname = "dmf.remove_rule"
    bl_label = "Remove Rule"
    bl_description = "Remove the selected rule"

    def execute(self, context):
        settings = context.scene.dmf
        if not settings.bone_rules:
            return {"CANCELLED"}
        index = max(0, min(settings.bone_rule_index, len(settings.bone_rules) - 1))
        settings.bone_rules.remove(index)
        settings.bone_rule_index = max(0, min(index, len(settings.bone_rules) - 1))
        return {"FINISHED"}


class DMF_OT_clear_rules(Operator):
    bl_idname = "dmf.clear_rules"
    bl_label = "Clear Rules"
    bl_description = "Remove every rule; the bone map itself is untouched"

    def execute(self, context):
        settings = context.scene.dmf
        settings.bone_rules.clear()
        settings.bone_rule_index = 0
        core.set_status(settings, "Rules cleared; mapped rows are unchanged", "INFO")
        return {"FINISHED"}


CLASSES = (
    DMF_OT_learn_rules,
    DMF_OT_apply_rules,
    DMF_OT_stop_rules,
    DMF_OT_add_rule,
    DMF_OT_rule_from_row,
    DMF_OT_remove_rule,
    DMF_OT_clear_rules,
)


def register() -> None:
    import bpy

    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    import bpy

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
