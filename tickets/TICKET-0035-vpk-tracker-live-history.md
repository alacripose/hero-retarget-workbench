# TICKET-0035 — live patch tracking and a git-style build history

**Status:** implemented; real signed-in fetch and a real game patch remain unobserved.
**Owner:** ala
**Opened:** 2026-11-18

## Requirement

The owner's corrections, verbatim:

> anywhere where this slop text bullshit appears in the ui in any place if it is redunant and can't be scanned in 2 seconds or less then it needs to be simplified to be human readable instead of the if not x then y or say stupid bullshit.

> also when the ui is open it needs to be able to safely handle when the game on the user side gets updated so it can keep a track of what files changed between patches as they come through so deleted files and even small changes are visible.

> additionally the snapshots panel when signed in should be able to show historical builds and tools and the diffs between them, the ui should be a little closer to a git repo type of thing with each deadlock version treated like the ci and the game tracking here: https://github.com/SteamTracking/GameTracking-Deadlock/compare/

## Contract

1. **Every visible string is scannable.** Labels and notes are one short phrase or one short
   sentence. No implementation trivia, conditional prose, or paths in the primary surface.
   Completed job logs are not shown as a wall; failures show a short error.
2. **The server watches the local install while the UI is open.** It reads `steam.inf`, the
   build, and every `*_dir.vpk` size/mtime. A changed signature is a patch candidate.
3. **A patch is captured only after it settles.** The watcher requires the signature to stay
   unchanged across a settle interval. `snapshot --wait-stable` rechecks the signature
   immediately before writing and aborts without writing a snapshot if the game changed
   during S2V reading. The watcher retries after the next stable interval.
4. **No duplicate or overlapping jobs.** One launcher job at a time. A patch arriving during
   a snapshot is queued as the next candidate, not run concurrently.
5. **Old snapshots are never overwritten.** A live capture is a new snapshot. The previous
   local snapshot remains the diff base. The UI follows the new pair and resets the change
   filter so removed and added files are both visible.
6. **History is real, not invented.** Existing snapshots get per-version stats versus their
   predecessor. Upstream builds come from the public GameTracking-Deadlock commit history for
   `manifests/manifest_1422456.txt`; a build's manifest ID is read from that commit's manifest
   file only when the owner asks to fetch it.
7. **Steam access is explicit.** The history and launcher show whether a saved Steam login
   exists. Fetching a historical manifest is offered only when a login is available; the
   public build list is still visible.
8. **The tracker remains the reader.** S2V reads directory VPKs; SteamFileDownloader fetches
   historical directory VPKs; the tracker never parses or writes a VPK.

## Implementation

- `serve` starts a live watcher by default (`--no-watch` disables it).
- `snapshot --wait-stable` guards the snapshot write with a before/after local signature.
- `/api/live` reports watch state, current build, candidate, last capture and errors.
- `/api/builds` reads and caches GameTracking commits; `/api/login/status` reads
  SteamFileDownloader's saved-login list without exposing a token.
- The Launcher is shortened to three actions: installed snapshot, historical build, Steam
  sign-in. The History panel lists captured snapshots with stats and upstream builds with
  Fetch actions.
- The top bar carries a live status chip; a completed live capture selects the new
  previous→current diff.

## Evidence

- `python -m unittest discover -s tests -p "test_vpk_tracker.py" -v` — **17 tests pass**.
  The new tests cover GameTracking commit parsing, manifest-ID parsing, mtime signatures,
  the pre-write guard, and the watcher starting a stable snapshot after a change.
- `python -m compileall -q tools/vpk_tracker.py` — pass. `node --check
  tools/vpk_tracker_ui/app.js` — pass.
- Live server at `http://127.0.0.1:8765/`: `/api/live` reports `state=watching`,
  `build=6863`; after repeated polling the snapshot count stayed at 2, so the watcher did
  not duplicate a matching build.
- `/api/history` returned both captured versions with per-version stats. `/api/builds`
  returned 30 real GameTracking commits; build **6864** is the latest and build **6863**
  maps to the captured local snapshot. `fetch_manifest_id` for the 6864 commit returned
  `756140601198168750` from that commit's tracked manifest file.
- `Launch-VPK-Tracker.cmd` invoked through `cmd //c '.\Launch-VPK-Tracker.cmd'` printed
  `VPK tracker already running http://127.0.0.1:8765/` and exited 0.
- UI inspection at 1440px and 440px: Launcher shows only Viewer / Steam tools / Snapshots,
  three actions, and no completed log wall. History shows snapshots with digest, build,
  source, time and stats, plus the upstream build list with one sign-in action. The phone
  table hides VPK/old/new columns so Path and Δ remain readable without horizontal scroll.
- Artifacts: `artifacts/vpk-tracker/ui-history-final.png`,
  `artifacts/vpk-tracker/ui-launcher-mobile-2.png`,
  `artifacts/vpk-tracker/ui-history-mobile.png`.

## Not checked

- A real local update to build 6864 while the watcher is running; the watcher path is
  exercised with a synthetic changed signature, not a Steam download.
- A real Steam login and historical manifest download; `steam_login_status` reports
  `known=true, logged_in=false`, so the fetch action is shown disabled/signed-out and no
  old-build download was attempted.
- The desktop launcher's cold-start path (server not already running); the reuse path was
  verified, and the server cold-start path was verified separately.
