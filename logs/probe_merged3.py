import sys
sys.path.insert(0, "<home>/AppData/Roaming/Blender Foundation/Blender/5.4/extensions/user_default")
sys.path.insert(0, "tools")
from pulse_src_ops import datamodel
from tail_release_audit import _joint_table
import collections, pathlib
counts = collections.Counter()
for path in sorted(pathlib.Path("artifacts/haze-tail/merged3").glob("*.dmx")):
    order = _joint_table(datamodel, str(path))["__order__"]["order"]
    counts[(len(order), len(set(order)))] += 1
print("MERGED3 (elements, unique) -> clips:", dict(counts))
