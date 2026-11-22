# TICKET-0034 — historical VPK snapshots from depot manifests

**Status:** implemented; live historical fetch requires the owner's Steam login.
**Owner:** ala
**Opened:** 2026-11-18

## Requirement

The owner's corrections, verbatim:

> the baseline should not be based on when the user installed the game SteamFileDownloader get 1422450 1422456:322100466064667547 -- "game/citadel/pak01_dir.vpk:models/heroes_wip/abrams/abrams.vmdl_c"

> there's already plenty of tools and options for comparing vpks between versions of the game the user doesn't have installed

> and again it needs to be able to see historical changes without keeping every single installed build of the game and the whole point of seeing every vpk is because of the vpk structure

The baseline is a chosen depot manifest, not the local install and not the
install date. A historical build costs its directory VPKs, not a game install.

## Contract

1. **Manifest identity is the baseline.** `snapshot --manifest
   <depot>:<manifest>` records the app, depot and manifest id in the snapshot
   and in `index.json`. The local install is a separate, labelled snapshot.
2. **SteamFileDownloader is the fetch layer.** It is the tool the owner named;
   the tracker does not implement a Steam client, depot reader or downloader.
   One login covers every target in one run.
3. **Every directory VPK is tracked.** The fetch pattern is
   `game/citadel/*_dir.vpk`, not `pak01_dir.vpk`. `pak01`, `shaders_pc` and
   `shaders_vulkan` are captured when the manifest has them.
4. **The VPK structure is preserved.** Each directory file is read by S2V's
   `--vpk_dir`; the snapshot keeps every entry path, CRC, stored size, archive
   chunk number and offset. The tracker never parses or writes a VPK.
5. **No archive chunks are downloaded for a snapshot.** The directory files and
   `game/citadel/steam.inf` are fetched. `SteamFileDownloader ls
   game/citadel/*.vpk` supplies the chunk names, sizes and SHA-1s, so the
   archive layout and chunk structure are recorded without the 30 GB of chunks.
6. **The cache is addressed by depot and manifest.** Files live under
   `artifacts/vpk-tracker/depots/<depot>/<manifest>/...`; a repeated snapshot
   reuses them. The binary and cache stay ignored by git.
7. **Provenance reaches the UI.** Snapshot rows carry `source.kind` =
   `manifest` or `local`, with the depot, manifest id and cache path for a
   manifest snapshot. The timeline and inspector show which build came from
   Steam and which came from the installed game.
8. **BLAKE3 binds the evidence.** The directory file, canonical entry records
   and the assembled snapshot each get a BLAKE3 digest, as before.
9. **A missing login is a refusal, not a fallback.** Exit code 3 from
   SteamFileDownloader becomes `steam-login-required`; exit 5 becomes
   `steam-no-access`. The tracker must not quietly substitute the local install
   for the requested historical manifest.

## Implementation

- `tools/vpk_tracker.py` adds `login` and `snapshot --manifest`, plus `--app`,
  `--sfd` and `--depot-output`. Multiple `--manifest` targets are fetched in one
  SteamFileDownloader run and become one snapshot each.
- `fetch_manifests` runs `get` and `ls`, writes both outputs to
  `artifacts/vpk-tracker/logs/manifest-*.log`, and refuses a partial or missing
  directory VPK instead of publishing a partial snapshot.
- `steam.inf` supplies the build number and version date; a manifest without it
  is labelled by the manifest id.
- `manifest_chunks` maps archive chunks to their directory VPK by prefix, so
  `pak01_*`, `shaders_pc_*` and `shaders_vulkan_*` do not get mixed.
- `_chunk_changed` compares SHA-1 when both snapshots have it (manifest
  snapshots) and falls back to size/mtime when they do not (local captures).
- The Popit UI labels the source in the build chip, timeline and inspector, and
  shows a chunk's SHA-1 when a downloaded manifest has no local mtime.

## Evidence

- `dotnet publish artifacts/tools/SteamFileDownloader-src/SteamFileDownloader.csproj
  -c Release -o artifacts/tools/sfd -p:PublishAot=false -p:PublishSingleFile=true`
  returned 0; `artifacts/tools/sfd/SteamFileDownloader.exe` is 86,710,256 bytes.
  AOT publish failed because `vswhere.exe` was not on PATH; the non-AOT
  single-file publish is the working local build.
- `python -m unittest discover -s tests -p "test_vpk_tracker.py" -v`: 11 tests
  pass, including manifest row parsing, the two-command fetch into a cache,
  chunk-family grouping, SHA-1 chunk comparison and source provenance.
- `python -m compileall -q tools/vpk_tracker.py`: pass.
- `node --check tools/vpk_tracker_ui/app.js`: pass.
- Directory-only proof: copied the installed `pak01_dir.vpk` into an empty
  temporary folder with none of its archive chunks and read it through S2V.
  `capture_vpk(..., chunks=[])` returned 158,588 entries, 0 local chunks and
  `blake3:766d4cd229111a436e45c0e56fe930559054fc4a09d9130001c4f6989eb0f225`.
  The historical download is therefore sufficient for the entry/offset
  structure; the chunk inventory comes from the manifest listing.
- The existing live snapshot is
  `artifacts/vpk-tracker/snapshots/2026-11-18t22-16-33-6863.json`: build 6863,
  159,120 entries across `pak01_dir.vpk`, `shaders_pc_dir.vpk` and
  `shaders_vulkan_dir.vpk`, 330 chunks, digest
  `blake3:fb663b79d8e77e9d49ba1b79a3d2f618c226dd5ba9465d5c5f8e86efb4aef43a`.
- Live manifest attempt:
  `python tools/vpk_tracker.py snapshot --manifest 1422456:322100466064667547`
  reached Steam and was refused with `steam-no-access`: the session was
  anonymous, and Steam gave no depot key for app `1422450`. The exact command
  and Steam error are in
  `artifacts/vpk-tracker/logs/manifest-1422456-322100466064667547-20261118T222648Z.log`.
  No historical snapshot was written, so the local build was not used as a
  substitute.

## Not checked

- The actual download and S2V listing of manifest `322100466064667547`; it needs
  the owner to run `python tools/vpk_tracker.py login` once and scan the QR with
  the Steam mobile app. Steam may also decline older manifests even with a
  login; that would be reported as `steam-no-access`, not worked around.
- A diff between the historical manifest snapshot and the current local
  snapshot, because the historical side does not exist yet.
- The manifest provenance labels in a live browser with a real manifest
  snapshot; the current preview has only the local snapshot.
