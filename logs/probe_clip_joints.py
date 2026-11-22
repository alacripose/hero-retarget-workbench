import os
import sys
sys.path.insert(0, os.path.expanduser("~/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default"))
sys.path.insert(0, "tools")
from pulse_src_ops import datamodel
from tail_release_audit import _joint_table
for path in ["artifacts/haze-tail/merged2/ability_bullet_flurry.dmx",
             "artifacts/haze-tail/bodies/ability_bullet_flurry.dmx"]:
    table = _joint_table(datamodel, path)
    order = table["__order__"]["order"]
    print(path, "count", len(order), "unique", len(set(order)))
    print("  first", order[:5], "tail", [n for n in order if n.startswith("tail")][:9])
