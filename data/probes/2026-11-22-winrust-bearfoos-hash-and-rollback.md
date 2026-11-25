# 2026-11-22 — WinRust "Bearfoos.B!ml": restored, hashed, rolled back

Kept probe. Machine: this Windows 11 box, local time UTC-5. Everything below was measured, not inferred;
the only numbers quoted from outside the machine are the GitHub release metadata and the Microsoft
threat page.

## Question

`Trojan:Win32/Bearfoos.B!ml` (ID 2147731849, Severe) was raised against `WinRust.exe` from
`https://github.com/Lemxy/WinRust/releases`. The file came from the project's own releases page.
Is the detection real, and if not, what is left on the machine?

## What Defender recorded

| When | What |
|---|---|
| 15:59:45 | 1116 detection, Real-Time Protection, **FastPath**, `file:F:\Downloaded Files\WinRust.exe`, process `pid:45692` (the installer itself) |
| 15:59:46 / :48 | further 1116 rows as `TabTip.exe` and `topbar.exe` read the same file — not separate infections |
| 16:00:17 | 1117 quarantine of the download folder copy |
| 16:05:04 | 1117 quarantine of `%ProgramFiles%\WinRust\WinRust.exe` **and** the scheduled task `WinRust-update` plus its TaskCache keys |

The install log showed the plugins were installed 15:59:32–16:00:05, i.e. **the installer ran to completion
before the first quarantine landed**. It also showed the promised restore point was never created
(`Checkpoint-Computer` failed, `ServiceDisabled`), so the installer's advertised safety net did not exist on
this machine.

## Hash: the deciding measurement

Official v0.5.6 release asset, from the GitHub API:

- size `8477184`
- `sha256:836d2a10b896d39dfd1fd8a4241341ee927a0d8fa32022ab1752b5bfe6e8f93e`

Restored the quarantined item with `MpCmdRun.exe -Restore -FilePath "F:\Downloaded Files\WinRust.exe"` and
hashed it in the same elevated session:

```
restored size=8477184
restored sha256=836D2A10B896D39DFD1FD8A4241341EE927A0D8FA32022AB1752B5BFE6E8F93E
local restored copy matched: True
```

**The flagged file is the official release, byte for byte.** The detection is a machine-learning false
positive, not a tampered build. `!ml` is a heuristic verdict; the same label has been raised on unsigned
Rust/Go/PyInstaller binaries from Microsoft, QOwnNotes, MakeMKV, rtk and others.

## Re-quarantine attempt — it did not happen

`Start-MpScan -ScanType CustomScan -ScanPath <restored file>` completed and **did not re-flag the file**:
three seconds later it was still present. The 15:59 history row moved from status 3 (quarantined) to 7 after
the restore. The script then deleted the restored copy so no flagged bytes stay on disk. Net result:

- no copy on disk, no copy in quarantine;
- detection history retained (`IsActive: False`);
- the hash above is the durable evidence, and it matches the published digest.

Deviation from the instruction ("let Defender quarantine it again") is recorded here: the scan refused to
reproduce the verdict, and the file was removed instead.

## Rollback: what the installer wrote, and what was undone

The installer that would have run **Remove all** was itself quarantined, so the rollback replays
`src/install/*.rs` (tag v0.5.6) and the on-disk journal. Script: `tools/winrust_rollback.ps1`; raw log:
`data/winrust-rollback.log`; journal copies: `data/winrust-journal/`.

| Installed piece | What it had changed | Undone |
|---|---|---|
| `topbar` + `reshell` | tasks `\topbar`, `\reshell`; bar hides the stock taskbar at window level; PowerShell profile block | `topbar.exe --restore`, processes killed, both tasks deleted, Run values cleared, profile block stripped (profile file removed as it held nothing else), `%ProgramFiles%\topbar` deleted |
| `rust-search` | WSearch disabled; `SearchHost.exe` IFEO `Debugger=cmd.exe /c exit`; `SearchboxTaskbarMode=0`; tasks `rs-search-C…J`, `rs-launcher`; 4 `rs.exe` indexers | `rs.exe --uninstall`, indexers killed, tasks deleted, WSearch → `AUTO_START (DELAYED)` and **RUNNING**, IFEO value removed, `SearchboxTaskbarMode=2`, `%ProgramFiles%\rs-search` deleted |
| `rtaskmgr-win32` | `taskmgr.exe` IFEO `Debugger=rtaskmgr-win32.exe`; task `rtaskmgr`; Start menu "Task manager" | no prior replacement was saved, so the Debugger value was removed; task and state key deleted; shortcut and `%ProgramFiles%\rtaskmgr` deleted |
| `wiztree` | one exe, "WinRust Disk" shortcut | shortcut and `%ProgramFiles%\wiztree` deleted |
| installer | `%ProgramFiles%\WinRust` (self copy + journal), `%ProgramData%\plugin-launcher`, `WinRust-update` task | task already gone with the quarantine; folders removed after copying the journal out |

`rust-explorer` was never installed, so `PcaSvc`, `InventorySvc`, `lfsvc`, `cbdhsvc` and `DoSvc` were never
touched (checked: the first three RUNNING, `DoSvc` `AUTO_START (DELAYED)`).

## Shell verification, after the rollback

- Explorer restarted; `Shell_TrayWnd` `IsWindowVisible=True` (before the restart the window existed but was
  hidden — topbar hides it at window level, so killing the bar is not enough).
- Explorer PID 13744, session 1, not elevated.
- `sc query WSearch` → RUNNING; `sc qc WSearch` → AUTO_START (DELAYED).
- IFEO `taskmgr.exe\Debugger` and `SearchHost.exe\Debugger` → not found.
- `SearchboxTaskbarMode` → `0x2`.
- No `topbar|reshell|rtaskmgr|rs-launcher|rs-search|WinRust` task, process, Run value, Program Files folder,
  `HKLM\SOFTWARE\plugin-launcher`, `HKLM|HKCU\SOFTWARE\WinRust`, or `%LOCALAPPDATA%\WinRust`.

## Verdict

Benign build, hostile-looking footprint. The binary is an unsigned PE with no version resource that embeds
seven executables, writes to Program Files, disables Windows Search, hooks `SearchHost` and `taskmgr`, edits
the PowerShell profile, and registers a **SYSTEM-level daily task** that downloads and swaps executables
(`WinRust-update`, ed25519-signed manifest checked against `update-key.pub`). That profile is why the ML
model fired. Nothing malicious was observed: no listeners or connections from the installed programs, no
Winlogon shell replacement, and every change matched the public source.

Residual risk was not the label but the design: an unsigned shell from a five-day-old account with a
SYSTEM auto-updater. Both the binaries and the updater are now removed.

## Reproduce

```
powershell -NoProfile -ExecutionPolicy Bypass -File tools\winrust_rollback.ps1   # elevated
```

Phase 1 restores and hashes, phase 2 rescans, phase 3 replays the uninstall, phase 4 verifies. Idempotent;
it was run twice (the first run failed phase 1 because `MpCmdRun -Restore` rejects `-FilePath` combined with
`-Name`/`-All`, `hr=0x80070057`; the corrected call passed on the second run).
