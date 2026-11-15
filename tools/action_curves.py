"""Read an Action's fcurves on Blender 5.x, where actions are slotted.

`Action.fcurves` was removed when actions gained layers, strips and channelbags.
A tool that reads it raises `'Action' object has no attribute 'fcurves'` and then
reports "0 clips with a moving tail" over 28 failures, which reads as a tail
defect instead of a broken measurement.  That happened on `tail_swing_probe`
(the Tengu source sweep) on Blender 5.4.

Every measurement tool reads curves through `action_fcurves()` so the modern and
legacy layouts both work.
"""
from __future__ import annotations


def action_fcurves(action):
    """Every fcurve in `action`, legacy or slotted."""
    if action is None:
        return []
    legacy = list(getattr(action, "fcurves", []) or [])
    if legacy:
        return legacy
    curves = []
    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            for bag in getattr(strip, "channelbags", []) or []:
                curves.extend(bag.fcurves)
    return curves


def action_slot_bags(action):
    """Every channelbag in `action`, for tools that edit instead of read."""
    bags = []
    for layer in getattr(action, "layers", []) or []:
        for strip in getattr(layer, "strips", []) or []:
            bags.extend(getattr(strip, "channelbags", []) or [])
    return bags
