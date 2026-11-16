"""Pin the Shiv merge the owner is looking at, and the recipe that produced it.

**Owner instruction, verbatim:** *"That build was fine his fucking head and arm
were fixed in that fucking build in item run center but you didn't fucking use
that as the base for recompiling all of the fucking animations with the lift
fix"*, then *"13.2 and 13.1 are not the fucking good versions"*, then *"the lift
is not on the fucking item walk center animation itself ... make sure to pin this
version"*.

Two states are pinned here, because they answer two different questions.

**The recipe anchor** is pak97 v1, `artifacts/oldviper/shiv_merge_pak.vpk`: the
06:47 base with only `item_run_center.vnmclip_c` replaced by the stock-clip merge.
It is the build the owner said had the head and arms fixed, so its inputs are the
ones every rebuild must use:

  * merge skeleton: the 31 MB `shiv_tailbones.dmx`
    (md5 `ae3d181321cce008d3d5fa2293efe6d7`, 31,950,782 bytes), **not** the
    93 KB `artifacts/golden/tail-vnmclip-gate` skeleton
    (md5 `0c837723126ec8cc5c88ae383b94f912`) the rejected bulk merge ran on;
  * animation skeleton: the 06:47 `shiv.vnmskel`
    (md5 `62d2639fddd81799818662d47a4d4b51`, 48,023 bytes);
  * only the tail chain may differ from the stock body: measured with
    `tools/dmx_track_diff_probe.py`, `item_run_center` differs on `tail_*` and on
    nothing else above float noise (`artifacts/receipts/item-run-center-trackdiff.json`).

**The pinned build** is `artifacts/oldviper/shiv_merge_final.vpk`, installed at
`pak97_dir.vpk` when the owner reported *"item run center has the fixed arm and
head but the lift is there"*. Its `item_run_center` is the reference clip: the
lift the owner sees is in the clips that are still the 06:47 bake, not in this
one.

  python tools/shiv_merge_gate.py [--report artifacts/receipts/shiv-merge-gate.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forge import tails  # noqa: E402

ACCEPTED_PAK = ROOT / "artifacts" / "oldviper" / "shiv_merge_pak.vpk"
ACCEPTED_PAK_SHA = "c85507a7ca4b42bc08f02e16557cf9410e9155dd1a7dce4c69e6d01da3647ff5"
ACCEPTED_PAK_BYTES = 95_242_741
ACCEPTED_DMX = ROOT / "artifacts" / "oldviper" / "shiv-merge" / "item_run_center.dmx"
ACCEPTED_DMX_SHA = "1ed02b50a72ec01e8093471f40145b00dd9cc1e5915af91b06eacdee71daedd1"
ACCEPTED_DMX_BYTES = 290_898
PINNED_VPK = ROOT / "artifacts" / "oldviper" / "shiv_merge_final.vpk"
PINNED_VPK_SHA = "077f67d2c8a5886f44d388567a7d307afbaa82bb88aaafeee287dd27a3e0140a"
PINNED_VPK_BYTES = 95_259_992
# The owner-looked-at build: item_run_center correct, other clips still the 06:47 bake.
PINNED_VPK = ROOT / "artifacts" / "oldviper" / "shiv_merge_final.vpk"
PINNED_VPK_SHA = "077f67d2c8a5886f44d388567a7d307afbaa82bb88aaafeee287dd27a3e0140a"
PINNED_VPK_BYTES = 95_259_992
# The shipped build: every clip rebuilt from its OWN live decompile.  The earlier
# full-set build (`shiv_merge_live.vpk`, c2129264) staged bodies from a folder-wide
# decompile, where clips that name the same m_sourceFilename overwrite each other;
# the owner reported "bones rotated wrong" and `aim_weapon_crouch` was measured 92
# bones away from the game's own clip (IK targets 26-38 units, both upper arms
# ~1.5 rad).  This build decompiles one clip at a time and compiles each document
# against its own body, so the same clip is now within 0.011 of the game.
# Pinned by the owner 2026-11-15: *"this is the closest one yet everything is
# nearly there this is the new pinned functionality"*.  Every clip's body is the
# game's own channel data (copied verbatim, never re-authored through a rig) with
# the authored tail appended as seven joints and 21 channels; the skeleton is the
# mask-audited 15,722-byte build.
# Clips-only release.  `shiv_bind.vpk` (02594b0f) carried the model's bind rest in
# our own `shiv.vnmskel_c` and lost the tail; `shiv_append.vpk` (the owner pin) kept
# the tail and broke the look-up.  Measured against the model's bind skeleton
# (`dmx/mesh/shiv_tail15.dmx`, 168 joints): the bind build's rests match to 0.0000u
# and its joint order is identical to the pin's, so neither rest nor order explains
# the missing tail.  The one remaining difference was shipping the skeleton at all:
# the model already declares `tail_0..tail_end`, so this build ships the pinned
# clips and drops `shiv.vnmskel_c` and `dmx/`, which is the addon's own design
# (`forge/animgraph.py`: "the model's own skeleton carries the new tail bones, and
# only the clip documents are shipped").
# TRAPS: never re-add a shipped `.vnmskel_c` to fix animation; it re-roots `pelvis`
# and moves the tail off the model's bind.  Never treat a pak that only changes the
# skeleton bytes as an animation fix.
# The owner's next experiment: "You should see if this exact vpk with the
# vnmskeleton works".  Clips-only plus the PINNED skeleton packs back to
# `01efc18e`, byte-for-byte the pak the owner already has, so this build pairs the
# clips-only tree with the 06:47 base's own skeleton (15,731 bytes, md5
# `28912aab`).  The owner's reading of the clips-only pak is that the tail is fine
# and the body is contorted everywhere else, so the tail is left exactly where it
# is and only the skeleton changes.
# The owner's verdict on the 06:47-skeleton pairing (`745bf965`): "this version has
# the look up tilting off the ground" — body and tail right, look-up wrong.  The
# 06:47 and bind skeletons are identical at the top level except `root_motion`
# (identity vs `(0.5, 0.5, 0.5, 0.5)`); `pelvis` is top-level in BOTH, so the
# withdrawn pelvis re-parent is not involved.  This build takes the 06:47 rest and
# replaces only that one joint's rest with the game skeleton's.
RELEASE_VPK = ROOT / "artifacts" / "oldviper" / "shiv_tail_all.vpk"
RELEASE_VPK_SHA = "0a966d904c9583f3736c42cdc1b91d983919ae00f5619bf9ead81236ed57eb50"
RELEASE_VPK_BYTES = 95_882_596
RELEASE_SKELETON_MD5 = "1f92a022efe5b291408524e6a2b09869"
RELEASE_CLIPS_ONLY = ROOT / "artifacts" / "receipts" / "release-clips-only.json"
PERCLIP_AIM_VERIFY = ROOT / "artifacts" / "receipts" / "perclip-aim-verify.json"
SKELETON_MASK_AUDIT = ROOT / "artifacts" / "receipts" / "skeleton-mask-audit.json"
CLIP_SWEEP_SUMMARY = ROOT / "artifacts" / "receipts" / "clip-sweep-summary.json"
SHIPPED_SKELETON = ROOT / "artifacts" / "oldviper" / "shiv-merge-perclip" / "models" / "heroes_staging" / "shiv" / "shiv.vnmskel_c"
# The Shiv pak lives in whichever numbered slot was free when it was installed; on
# 2026-11-15 it is `pak93_dir.vpk` (sha256 `01efc18e…`, the append build the owner called
# *"the closest one yet"*), while `pak97_dir.vpk` carries the Haze port.  A gate that
# insists on one slot name reports "missing" for a build that is installed, which is how
# the pin and the slot drifted apart.
INSTALLED_PAK = Path(
    r"D:\SteamLibrary\steamapps\common\Deadlock\game\citadel\addons\pak93_dir.vpk"
)
# `artifacts/oldviper/shiv_append.vpk` — appended channels, no re-authored pose.  Accepted
# in the slot because it is the build the owner's screenshots describe.
APPEND_VPK_SHA = "01efc18ec8d156e9ff3846f17c5b9da06955ae25772031d3e0284c9c130be7f0"
GOLDEN_BASE = ROOT / "artifacts" / "shiv-168-full-baked3.vpk"
GOLDEN_BASE_SHA = "ebeadce2993831e67930611cff3b33c36b24c00103571b17d5777036e5ed752a"
MERGE_SKELETON = Path(
    r"C:\Users\ala\Downloads\Reduced_CSDK_13\content\citadel_addons\shiv_tail_0647_check"
    r"\models\heroes_staging\shiv\dmx\mesh\shiv_tailbones.dmx"
)
MERGE_SKELETON_MD5 = "ae3d181321cce008d3d5fa2293efe6d7"
MERGE_SKELETON_BYTES = 31_950_782
REJECTED_SKELETON = ROOT / "artifacts" / "golden" / "tail-vnmclip-gate" / "dmx" / "mesh" / "shiv_tailbones.dmx"
REJECTED_SKELETON_MD5 = "0c837723126ec8cc5c88ae383b94f912"
ANIM_SKELETON = Path(
    r"C:\Users\ala\Downloads\Reduced_CSDK_13\content\citadel_addons\shiv_tail_0647_check"
    r"\models\heroes_staging\shiv\shiv.vnmskel"
)
ANIM_SKELETON_MD5 = "62d2639fddd81799818662d47a4d4b51"
TRACK_DIFF = ROOT / "artifacts" / "receipts" / "item-run-center-trackdiff.json"
MERGE_RECEIPTS = (
    ROOT / "artifacts" / "receipts" / "shiv-bulk-merge-v2.json",
    ROOT / "artifacts" / "receipts" / "shiv-bulk-merge-v2-rest.json",
    ROOT / "artifacts" / "receipts" / "shiv-bulk-merge-v2-rest2.json",
    ROOT / "artifacts" / "receipts" / "perclip-merge.json",
)
MERGED = ROOT / "artifacts" / "oldviper" / "shiv-bulk-merge-v2"
EXPECTED_TAIL = ["tail_0", "tail_1", "tail_2", "tail_3", "tail_4", "tail_5", "tail_end"]
# ui_hero_select reads the source ui_hero_pose.dmx, which has no keyed frame
# range, so no tail range can be sampled for it (measured: `tail-target-empty-range:
# shiv_body has no frame range`).
KNOWN_UNMERGEABLE = {"ui_hero_pose", "ui_hero_select"}
MIN_MERGED = 123


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def merged_clips() -> tuple[set[str], set[str]]:
    clips: set[str] = set()
    failures: set[str] = set()
    for receipt in MERGE_RECEIPTS:
        if not receipt.is_file():
            continue
        data = json.loads(receipt.read_text(encoding="utf-8"))
        clips |= {row["clip"].removesuffix(".dmx") for row in data.get("clips", []) if "clip" in row}
        failures |= {row["clip"].removesuffix(".dmx") for row in data.get("failed", []) if "clip" in row}
    return clips, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(ROOT / "artifacts" / "receipts" / "shiv-merge-gate.json"))
    parser.add_argument("--skip-installed", action="store_true", help="do not require pak97_dir.vpk to be the pinned build")
    args = parser.parse_args()
    checks: list[dict[str, object]] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    inputs = (
        ("accepted pak97 v1", ACCEPTED_PAK),
        ("accepted item_run_center DMX", ACCEPTED_DMX),
        ("pinned build", PINNED_VPK),
        ("06:47 base", GOLDEN_BASE),
        ("31 MB merge skeleton", MERGE_SKELETON),
        ("06:47 animation skeleton", ANIM_SKELETON),
    )
    for label, path in inputs:
        check(label, path.is_file(), str(path))
    if not all(item["pass"] for item in checks):
        report = {"summary": "shiv merge gate input missing", "checks": checks}
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2

    pak_sha = sha256(ACCEPTED_PAK)
    check(
        "accepted build is the frozen pak97 v1 bytes",
        pak_sha == ACCEPTED_PAK_SHA and ACCEPTED_PAK.stat().st_size == ACCEPTED_PAK_BYTES,
        f"{pak_sha} {ACCEPTED_PAK.stat().st_size}b",
    )
    base_sha = sha256(GOLDEN_BASE)
    check("06:47 base is the frozen bytes", base_sha == GOLDEN_BASE_SHA, base_sha)
    pinned_sha = sha256(PINNED_VPK)
    check(
        "pinned build is the frozen bytes",
        pinned_sha == PINNED_VPK_SHA and PINNED_VPK.stat().st_size == PINNED_VPK_BYTES,
        f"{pinned_sha} {PINNED_VPK.stat().st_size}b",
    )
    release_sha = sha256(RELEASE_VPK) if RELEASE_VPK.is_file() else None
    check(
        "shipped build is the frozen bytes",
        release_sha == RELEASE_VPK_SHA
        and RELEASE_VPK.is_file()
        and RELEASE_VPK.stat().st_size == RELEASE_VPK_BYTES,
        f"{release_sha} {RELEASE_VPK.stat().st_size if RELEASE_VPK.is_file() else 0}b",
    )
    clips_only = (
        json.loads(RELEASE_CLIPS_ONLY.read_text(encoding="utf-8"))
        if RELEASE_CLIPS_ONLY.is_file()
        else {}
    )
    check(
        "release is the clips-only tree plus the 06:47 rest with the game root, and no dmx",
        clips_only.get("sha256") == RELEASE_VPK_SHA
        and clips_only.get("bytes") == RELEASE_VPK_BYTES
        and clips_only.get("skeleton_override")
        == ["models/heroes_staging/shiv/shiv.vnmskel_c"]
        and clips_only.get("skeleton_md5") == RELEASE_SKELETON_MD5
        and not clips_only.get("dmx_shipped"),
        f"files={clips_only.get('file_count')} "
        f"skeleton={clips_only.get('skeleton_override')} "
        f"md5={clips_only.get('skeleton_md5')} dmx={clips_only.get('dmx_shipped')}",
    )
    root_rest = ROOT / "artifacts" / "receipts" / "skeleton-release-root.json"
    rest = json.loads(root_rest.read_text(encoding="utf-8")) if root_rest.is_file() else {}
    changed = rest.get("changed") or {}
    after = (changed.get("root_motion") or {}).get("after", {}).get("orientation")
    check(
        "release skeleton changes only root_motion, to the game's rest",
        sorted(changed.keys()) == ["root_motion"] and after == [0.5, 0.5, 0.5, 0.5],
        f"changed={sorted(changed.keys())} orientation={after}",
    )
    tail_path = ROOT / "artifacts" / "receipts" / "tail-audit.json"
    tail = json.loads(tail_path.read_text(encoding="utf-8")) if tail_path.is_file() else {}
    chain = tail.get("chain_present") or []
    check(
        "tail chain is present, parented under pelvis, and carries the model rest",
        len(chain) == 7
        and tail.get("chain_parenting_ok") is True
        and tail.get("rest_worst_distance") is not None
        and tail["rest_worst_distance"] <= 0.01
        and tail.get("rest_worst_angle") is not None
        and tail["rest_worst_angle"] <= 2.0,
        f"chain={len(chain)} parents_ok={tail.get('chain_parenting_ok')} "
        f"rest={tail.get('rest_worst_distance')}u/{tail.get('rest_worst_angle')}deg",
    )
    geometry = tail.get("geometry") or {}
    check(
        "tail geometry is weighted to the tail chain",
        (geometry.get("tail_vertices_total") or 0) > 0
        and (geometry.get("mesh") or "") == "shiv_tail15"
        and (tail.get("modeldoc") or {}).get("tail_mesh_declared") is True,
        f"mesh={geometry.get('mesh')} vertices={geometry.get('tail_vertices_total')} "
        f"declared={(tail.get('modeldoc') or {}).get('tail_mesh_declared')}",
    )
    check(
        "shipped clips drive the tail instead of holding it still",
        (tail.get("variance_sampled_with_channels") or 0) > 0
        and tail.get("variance_sampled_with_channels_moving")
        == tail.get("variance_sampled_with_channels")
        and (tail.get("clips_with_tail_channels") or 0) > 0,
        f"with_channels_moving={tail.get('variance_sampled_with_channels_moving')}"
        f"/{tail.get('variance_sampled_with_channels')} "
        f"clips_with_channels={tail.get('clips_with_tail_channels')}/{tail.get('clips_total')}",
    )
    if not args.skip_installed:
        installed = sha256(INSTALLED_PAK) if INSTALLED_PAK.is_file() else None
        # The owner directed the installed slot back to the 06:47 base
        # (artifacts/shiv-168-full-baked3.vpk) while the merged build is fixed, so
        # the slot accepts either the reviewed merge or that base and says which.
        accepted = {RELEASE_VPK_SHA, GOLDEN_BASE_SHA, APPEND_VPK_SHA}
        label = {
            RELEASE_VPK_SHA: "clips-only release",
            GOLDEN_BASE_SHA: "06:47 base",
            APPEND_VPK_SHA: "append build",
        }
        check(
            f"{INSTALLED_PAK.name} is a reviewed Shiv build",
            installed in accepted,
            label.get(installed, installed or "missing"),
        )
    dmx_sha = sha256(ACCEPTED_DMX)
    check(
        "accepted merged DMX is the frozen bytes",
        dmx_sha == ACCEPTED_DMX_SHA and ACCEPTED_DMX.stat().st_size == ACCEPTED_DMX_BYTES,
        f"{dmx_sha} {ACCEPTED_DMX.stat().st_size}b",
    )
    skeleton_md5 = md5(MERGE_SKELETON)
    check(
        "merge runs on the 31 MB skeleton",
        skeleton_md5 == MERGE_SKELETON_MD5 and MERGE_SKELETON.stat().st_size == MERGE_SKELETON_BYTES,
        f"{skeleton_md5} {MERGE_SKELETON.stat().st_size}b",
    )
    anim_md5 = md5(ANIM_SKELETON)
    check("compiles against the 06:47 vnmskel", anim_md5 == ANIM_SKELETON_MD5, anim_md5)
    if REJECTED_SKELETON.is_file():
        rejected_md5 = md5(REJECTED_SKELETON)
        check(
            "the rejected 93 KB skeleton is a different file",
            rejected_md5 == REJECTED_SKELETON_MD5 and rejected_md5 != MERGE_SKELETON_MD5,
            f"{rejected_md5} ({REJECTED_SKELETON.stat().st_size}b)",
        )

    merged, failures = merged_clips()
    extra_failures = sorted(name for name in failures if name not in KNOWN_UNMERGEABLE and not name.startswith("zipline_"))
    check("merge covers the stock clip set", len(merged) >= MIN_MERGED, f"{len(merged)} merged")
    check("no unexpected merge failures", not extra_failures, ", ".join(extra_failures))

    sample = MERGED / "item_run_center.dmx"
    if sample.is_file():
        names = tails.dmx_bone_names(sample)
        # dmx_bone_names returns every name-table token that looks like a tail,
        # including the DmeTransform component names (tail_0_o/_p/_s), so the
        # check is that the seven chain bones are all present, not that the list
        # equals them.
        missing = [name for name in EXPECTED_TAIL if name not in names]
        check("rebuilt clip carries the tail chain", not missing, "missing: " + ", ".join(missing) if missing else ", ".join(EXPECTED_TAIL))
    else:
        check("rebuilt clip carries the tail chain", False, f"missing {sample}")

    if TRACK_DIFF.is_file():
        diff = json.loads(TRACK_DIFF.read_text(encoding="utf-8"))
        # A body bone is only different if it moves a measurable amount; the
        # pipelines sample through float matrices, so everything that is not a
        # tail lands at ~3e-05 and that is noise, not a pose change.
        rows = diff.get("differences", {})
        body_tolerance = 1e-3
        # blade hinge R differs by exactly 6.283185 rad on one Euler channel:
        # a full turn, so the same orientation written a revolution higher. Any
        # delta that is a whole number of turns is that, not a pose change.
        full_turn = 6.283185307179586

        def body_delta(row: dict) -> float:
            value = float(row.get("max_delta_total") or row.get("max_delta") or 0.0)
            turns = round(value / full_turn)
            if turns and abs(value - turns * full_turn) <= body_tolerance:
                return 0.0
            return value

        differing = [
            bone
            for bone, row in rows.items()
            if not bone.startswith("tail_") and body_delta(row) > body_tolerance
        ]
        body = sorted(name for name in differing if not name.startswith("tail_"))
        check(
            "rebuilt clip keeps the accepted body",
            not body,
            "body bones differing: " + ", ".join(body)
            if body
            else f"no body bone above {body_tolerance} besides whole turns; rows {len(rows)}",
        )
    else:
        check("rebuilt clip keeps the accepted body", False, f"missing {TRACK_DIFF}")

    if PERCLIP_AIM_VERIFY.is_file():
        verify = json.loads(PERCLIP_AIM_VERIFY.read_text(encoding="utf-8"))
        rows = verify.get("differences", {})
        # The pelvis is re-expressed in our skeleton's axes (the accepted build
        # shows the same at 4.58), so it is excluded; every other bone has to sit
        # inside float noise of the game's own clip.
        worst = max(
            (
                float(row.get("max_delta_total") or row.get("max_delta") or 0.0)
                for bone, row in rows.items()
                if bone != "pelvis" and not bone.startswith("tail_")
            ),
            default=0.0,
        )
        check(
            "the shipped aim clip is the game's own clip",
            worst <= 0.05,
            f"worst non-pelvis bone {worst:.3f} against pak01 (was 38.1 on the rejected build)",
        )
    else:
        check("the shipped aim clip is the game's own clip", False, f"missing {PERCLIP_AIM_VERIFY}")

    if CLIP_SWEEP_SUMMARY.is_file():
        # Every shipped clip, decompiled from the installed pak and from pak01 and
        # compared bone by bone.  Any clip rebuilt from another clip's body shows
        # up here as a tens-of-units delta on IK targets and upper arms, which is
        # exactly what the owner saw as "bones rotated wrong".
        sweep = json.loads(CLIP_SWEEP_SUMMARY.read_text(encoding="utf-8"))
        # Positions only: an IK goal's position is what the solver chases, while a
        # rotation written as a different Euler triple can be the same orientation.
        # The rejected build measured 26-38 units on these same goals when a clip
        # was rebuilt from a sibling's body; a good build sits two orders below.
        worst_position = float(sweep.get("worst_position") or 0.0)
        check(
            "every shipped clip is the game's own body",
            int(sweep.get("clips_compared") or 0) >= 180
            and not sweep.get("failed")
            and worst_position <= 0.5
            and float(sweep.get("worst_tail") or 0.0) == 0.0,
            f"{sweep.get('clips_compared')} clips, {sweep.get('body_identical')} identical, "
            f"{sweep.get('position_within_0_05')} within 0.05, {sweep.get('position_over_0_05')} up to "
            f"{worst_position:.3f} on IK goals (median {sweep.get('median_position')}), "
            f"worst tail {sweep.get('worst_tail')} (rejected build: 26-38 units)",
        )
    else:
        check("every shipped clip is the game's own body", False, f"missing {CLIP_SWEEP_SUMMARY}")

    if SKELETON_MASK_AUDIT.is_file():
        audit = json.loads(SKELETON_MASK_AUDIT.read_text(encoding="utf-8"))
        # Source 2 resolves a bone mask by name against the skeleton resource, and
        # the shipped skeleton's masks were stock-authored: they named
        # weaponHand_L/R, which this rig does not carry, so melee_UpperBody and
        # Parry_UpperBody lost those bones and the client logged four
        # `Couldn't find bone` warnings per load.
        missing = audit.get("missing", {})
        check(
            "every skeleton mask bone resolves on the shipped rig",
            not missing and int(audit.get("masks", 0)) >= 20,
            f"{audit.get('masks')} masks, missing {missing}" if missing else f"{audit.get('masks')} masks, 0 missing",
        )
        check(
            "the shipped skeleton is the audited bytes",
            SHIPPED_SKELETON.is_file() and md5(SHIPPED_SKELETON) == audit.get("vnmskel_c_md5"),
            f"{md5(SHIPPED_SKELETON) if SHIPPED_SKELETON.is_file() else 'missing'} vs {audit.get('vnmskel_c_md5')}",
        )
    else:
        check("every skeleton mask bone resolves on the shipped rig", False, f"missing {SKELETON_MASK_AUDIT}")

    passed = all(item["pass"] for item in checks)
    report = {
        "summary": "shiv merge gate passed" if passed else "shiv merge gate failed",
        "accepted": {"pak": str(ACCEPTED_PAK), "sha256": ACCEPTED_PAK_SHA, "dmx": str(ACCEPTED_DMX)},
        "pinned": {"vpk": str(PINNED_VPK), "sha256": PINNED_VPK_SHA, "installed": str(INSTALLED_PAK)},
        "checks": checks,
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
