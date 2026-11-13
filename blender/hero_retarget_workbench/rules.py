"""Rule learning for the bone map: one row teaches its mirror, and a button fills the rest.

``DMF_BoneEntry.target`` calls ``auto_fill`` when the user types a target, so
mapping ``elbow_L`` to ``arm_lower_L`` instantly files the same rule and places
``elbow_R`` on ``arm_lower_R``. Programmatic scans and fills run inside
``suppressed()`` so they never cascade into each other.
"""
from __future__ import annotations

import contextlib

from bpy.types import Operator
from forge import bonerules

from . import core, proofing

_DEPTH = 0  # nesting guard: an auto-fill must not start another auto-fill


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


def panel_rules(settings) -> list[bonerules.Rule]:
    """The rules stored in the file, plus the joint words the hero skeleton allows."""
    rows = [
        bonerules.Rule(
            source=row.source,
            target=row.target,
            regex=row.regex,
            side_aware=row.side_aware,
            origin=row.origin,
            enabled=row.enabled,
            support=row.support,
        )
        for row in settings.bone_rules
        if row.source and row.target
    ]
    return bonerules.ordered(rows + bonerules.builtin(target_names(settings)))


def store(settings, rules: list[bonerules.Rule]) -> int:
    """Merge learned rules into the panel rows without touching a user's own row."""
    existing = {
        (row.source.lower(), row.target.lower(), bool(row.regex)): row
        for row in settings.bone_rules
    }
    with suppressed():
        for rule in rules:
            key = (rule.source.lower(), rule.target.lower(), bool(rule.regex))
            row = existing.get(key)
            if row is None:
                row = settings.bone_rules.add()
                row.source = rule.source
                row.target = rule.target
                row.regex = rule.regex
                row.side_aware = rule.side_aware
                row.origin = rule.origin
                row.support = rule.support
                existing[key] = row
            else:
                row.support = max(int(row.support), int(rule.support))
    return len(settings.bone_rules)


def learn_from_map(settings) -> int:
    """Learn from the rows that are already mapped."""
    learned = bonerules.learn(mapping(settings))
    store(settings, learned)
    return len(learned)


def fill(settings) -> int:
    """Place every unmatched row a rule can answer, and say nothing it cannot."""
    rules = panel_rules(settings)
    sources = [entry.source for entry in settings.bone_map if entry.source]
    found = bonerules.suggest(rules, sources, target_names(settings), mapping(settings))
    changed = 0
    with suppressed():
        for entry in settings.bone_map:
            hit = found.get(entry.source)
            if hit is None:
                continue
            entry.target = hit.target
            entry.state = "MAPPED"
            entry.note = f"rule {hit.label}"
            changed += 1
    return changed


def auto_fill(settings, entry) -> int:
    """File the rule a typed target implies and place its opposite-side row.

    Called from the target field's update callback: the user sees ``elbow_R``
    move the moment ``elbow_L`` is answered. Only the exact mirror row is
    written here — broader filling stays an explicit action.
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
            placed += 1
    return placed


class DMF_OT_learn_rules(Operator):
    bl_idname = "dmf.learn_rules"
    bl_label = "Learn Rules"
    bl_description = "Turn the rows already mapped into side rules that answer their mirrors"

    def execute(self, context):
        settings = context.scene.dmf
        if settings.target_armature is None:
            self.report({"ERROR"}, "Import the hero skeleton first")
            core.set_status(settings, "Rules need the hero skeleton's bone names", "WARN")
            return {"CANCELLED"}
        count = learn_from_map(settings)
        if count:
            core.set_status(settings, f"{count} rules learned from the mapped rows", "OK")
        else:
            core.set_status(settings, "No paired row yet; map one left/right bone first", "WARN")
        return {"FINISHED"}


class DMF_OT_apply_rules(Operator):
    bl_idname = "dmf.apply_rules"
    bl_label = "Fill From Rules"
    bl_description = "Give every unmatched row the target a rule names; never overwrite a mapped row"

    def execute(self, context):
        settings = context.scene.dmf
        if not settings.bone_map:
            self.report({"ERROR"}, "Scan the bone map first")
            return {"CANCELLED"}
        try:
            changed = fill(settings)
        except Exception as error:
            core.set_status(settings, str(error), "ERROR")
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        proofing.bump_tick(settings)
        if changed:
            left = sum(1 for row in settings.bone_map if row.state == "UNMATCHED")
            core.set_status(settings, f"Rules filled {changed} rows; {left} still need a decision", "OK" if not left else "WARN")
        else:
            core.set_status(settings, "No rule answered an unmatched row", "WARN")
        return {"FINISHED"}


class DMF_OT_add_rule(Operator):
    bl_idname = "dmf.add_rule"
    bl_label = "Add Regex Rule"
    bl_description = "Add a pattern rule of your own; groups such as \\1 can be used in the target"

    def execute(self, context):
        settings = context.scene.dmf
        row = settings.bone_rules.add()
        row.source = ""
        row.target = ""
        row.regex = True
        row.side_aware = False
        row.origin = "regex"
        row.enabled = True
        settings.bone_rule_index = len(settings.bone_rules) - 1
        core.set_status(settings, "New rule: pattern matches a source name, target may use \\1", "INFO")
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
    bl_description = "Forget every learned and hand-written rule; the map itself is untouched"

    def execute(self, context):
        settings = context.scene.dmf
        settings.bone_rules.clear()
        settings.bone_rule_index = 0
        core.set_status(settings, "Rules cleared; mapped rows are unchanged", "INFO")
        return {"FINISHED"}


CLASSES = (
    DMF_OT_learn_rules,
    DMF_OT_apply_rules,
    DMF_OT_add_rule,
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
