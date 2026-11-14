"""Compatibility calls into PulseSrcOps, the DMX importer/exporter."""
from __future__ import annotations

import sys
from contextlib import contextmanager

import bpy


def _flex_module():
    """The loaded PulseSrcOps flex module, whichever extension package owns it."""
    for name, module in list(sys.modules.items()):
        if name == "flex" or name.endswith(".flex"):
            if hasattr(module, "AddCorrectiveShapeDrivers"):
                return module
    return None


@contextmanager
def safe_corrective_drivers():
    """Tolerate PulseSrcOps' empty-modifier assumption while importing.

    ``AddCorrectiveShapeDrivers.addDrivers`` removes ``fcurve.modifiers[0]``
    without checking that Blender created a default modifier. On 5.4 a head DMX
    with corrective shape keys raises IndexError there and aborts the whole mesh
    import, which is how a hero head could be skipped because of a driver bug.
    The original is restored immediately after the operator returns.
    """
    module = _flex_module()
    if module is None:
        yield
        return
    cls = module.AddCorrectiveShapeDrivers
    original = cls.__dict__.get("addDrivers")

    def add_drivers(key, driver_names):
        key.driver_remove("value")
        fcurve = key.driver_add("value")
        if len(fcurve.modifiers):
            fcurve.modifiers.remove(fcurve.modifiers[0])
        fcurve.driver.type = "MIN"
        for driver_key in driver_names:
            variable = fcurve.driver.variables.new()
            variable.name = driver_key
            variable.targets[0].id_type = "KEY"
            variable.targets[0].id = key.id_data
            variable.targets[0].data_path = f'key_blocks["{driver_key}"].value'

    cls.addDrivers = staticmethod(add_drivers)
    try:
        yield
    finally:
        if original is None:
            delattr(cls, "addDrivers")
        else:
            cls.addDrivers = original


def import_dmx(path, append: str = "NEW_ARMATURE", up_axis: str = "Z", forward_axis: str = "-Y"):
    """Import one DMX with the PulseSrcOps compatibility guard in place."""
    with safe_corrective_drivers():
        return bpy.ops.import_scene.kst_dmx(
            filepath=str(path),
            append=append,
            upAxis=up_axis,
            forwardAxis=forward_axis,
        )
