"""Gate the working tail vnmclip: exact clip, exact skeleton, tail bones.

The owner identified the 03:50 `weapon_stand_idle.vnmclip_c` as the visual
reference: the body is upright and the tail is present and animated.  This gate
does not reinterpret its pose in Blender (the S2V root-motion axis fixup makes a
raw Blender pose look sideways).  It pins the compiled bytes and the compiled
skeleton, then proves the skeleton DMX carries the appended tail chain.
"""

from __future__ import annotations
import os

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge import tails  # noqa: E402

GOLDEN = ROOT / "artifacts" / "golden" / "tail-vnmclip-gate"
DEFAULT_CLIP = Path(
    os.path.expanduser(r"~\Downloads\Reduced_CSDK_13\game\citadel_addons\shiv_tail_anim\models\heroes_staging\shiv\clips\weapon_stand_idle.vnmclip_c")
)
DEFAULT_SKELETON = Path(
    os.path.expanduser(r"~\Downloads\Reduced_CSDK_13\game\citadel_addons\shiv_tail_anim\models\heroes_staging\shiv\shiv.vnmskel_c")
)
EXPECTED_CLIP_SHA = "3451df8946908d91dee22fa8792feee227a2c64bdd7a1ac30d1daf3d6654352d"
EXPECTED_SKELETON_SHA = "c2f1e2439d773a350bf224c7069890c50479f381cab2e6b4a792c349670ac847"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", default=str(DEFAULT_CLIP))
    parser.add_argument("--skeleton", default=str(DEFAULT_SKELETON))
    parser.add_argument("--golden", default=str(GOLDEN))
    parser.add_argument("--report", default=str(ROOT / "artifacts" / "receipts" / "tail-vnmclip-gate.json"))
    args = parser.parse_args()

    clip = Path(args.clip)
    skeleton = Path(args.skeleton)
    golden = Path(args.golden)
    golden_clip = golden / "weapon_stand_idle.vnmclip_c"
    golden_skeleton = golden / "shiv.vnmskel_c"
    golden_dmx = golden / "dmx" / "mesh" / "shiv_tailbones.dmx"

    checks: list[dict[str, object]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    for label, path in (
        ("live clip", clip),
        ("live skeleton", skeleton),
        ("golden clip", golden_clip),
        ("golden skeleton", golden_skeleton),
        ("golden skeleton DMX", golden_dmx),
    ):
        check(label, path.is_file(), str(path))

    if not all(item["pass"] for item in checks):
        report = {"summary": "missing tail vnmclip gate input", "checks": checks}
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2

    live_clip_sha = sha256(clip)
    live_skeleton_sha = sha256(skeleton)
    golden_clip_sha = sha256(golden_clip)
    golden_skeleton_sha = sha256(golden_skeleton)
    tail_names = tails.dmx_bone_names(golden_dmx)

    check("live clip is the frozen 03:50 frame", live_clip_sha == EXPECTED_CLIP_SHA, live_clip_sha)
    check("golden clip matches the frozen bytes", golden_clip_sha == EXPECTED_CLIP_SHA, golden_clip_sha)
    check("live skeleton matches the frozen bytes", live_skeleton_sha == EXPECTED_SKELETON_SHA, live_skeleton_sha)
    check("golden skeleton matches the frozen bytes", golden_skeleton_sha == EXPECTED_SKELETON_SHA, golden_skeleton_sha)
    check(
        "compiled skeleton carries the tail chain",
        tail_names == ["tail_0", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5", "tail_end"],
        ", ".join(tail_names),
    )

    passed = all(item["pass"] for item in checks)
    report = {
        "summary": "03:50 tail vnmclip gate passed" if passed else "03:50 tail vnmclip gate failed",
        "clip": str(clip),
        "skeleton": str(skeleton),
        "checks": checks,
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
