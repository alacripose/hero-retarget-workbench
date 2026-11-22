import sys
sys.path.insert(0, "<home>/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")
sys.path.insert(0, "tools")
from pulse_src_ops import datamodel
from tail_release_audit import _joint_table
pairs = [
 ("skeleton", "<home>/Downloads/Reduced_CSDK_13/content/citadel_addons/haze_tail/models/heroes_staging/haze/haze_model_tail.dmx"),
 ("clip", "artifacts/haze-tail/aligned132/ability_bullet_flurry.dmx"),
]
for label, path in pairs:
    table = _joint_table(datamodel, path)
    order = table["__order__"]["order"]
    print(label, "raw", len(order), "unique", len(set(order)))
    print("   spaced/DMF:", [n for n in order if (" " in n or n.startswith("DMF "))][:6])
    print("   tail:", [n for n in order if n.startswith("tail")][:3], "...", [n for n in order if n.startswith("tail")][-1:])
