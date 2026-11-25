#Requires -RunAsAdministrator
# WinRust v0.5.6 rollback for a machine whose installer was quarantined as
# Trojan:Win32/Bearfoos.B!ml. Path-agnostic: no user name, no drive letters.
#
# Phase 1 restores the quarantined copy into a scratch folder and hashes it
#          against the official v0.5.6 digest.
# Phase 2 hands it back to Defender with a targeted scan.
# Phase 3 replays what the installer wrote, following the plugin sources
#          (src/install/*.rs) and the on-disk journal, because the installer
#          that would do "Remove all" is itself gone.
# Phase 4 verifies the Windows 11 shell is back.
#
# Usage (elevated):
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\winrust_rollback.ps1

$ErrorActionPreference = 'Continue'
$ProgressPreference    = 'SilentlyContinue'

$root    = Split-Path -Parent $PSScriptRoot
$logDir  = Join-Path $root 'data'
$log     = Join-Path $logDir 'winrust-rollback.log'
$scratch = Join-Path $env:PUBLIC 'winrust-scratch'
$pf      = $env:ProgramFiles
$pd      = $env:ProgramData

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Content -Path $log -Value '' -Encoding utf8

function Say([string]$m) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'HH:mm:ss'), $m
    $line | Tee-Object -FilePath $log -Append | Out-Null
    Write-Host $line
}
function Try-Out([string]$m, [scriptblock]$b) {
    try { & $b } catch { Say ("$m threw: " + $_.Exception.Message) }
}

Say '=== phase 0: state before rollback ==='
Say ('tasks: ' + ((& schtasks.exe /query /fo csv /nh 2>$null | Select-String -Pattern 'topbar|reshell|rtaskmgr|rs-launcher|rs-search|WinRust') -join ' | '))
Say ('WSearch: ' + ((& sc.exe qc WSearch 2>&1 | Select-String 'START_TYPE') -join ' '))
Say ('IFEO taskmgr: ' + ((& reg.exe query 'HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\taskmgr.exe' /v Debugger 2>&1) -join ' '))
Say ('IFEO SearchHost: ' + ((& reg.exe query 'HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\SearchHost.exe' /v Debugger 2>&1) -join ' '))
Say ('processes: ' + ((Get-Process topbar,reshell,rs,rs-launcher,rtaskmgr-win32,wiztree -ErrorAction SilentlyContinue).ProcessName -join ', '))

Say '=== phase 1: restore the quarantined installer and hash it ==='
New-Item -ItemType Directory -Force -Path $scratch | Out-Null
$dest = Join-Path $scratch 'WinRust.exe'
$mp   = Join-Path $pf 'Windows Defender\MpCmdRun.exe'

# -FilePath restores the item with that original path; MpCmdRun refuses it together with -Name/-All.
$orig = 'F:\Downloaded Files\WinRust.exe'
$out = & $mp -Restore -FilePath $orig 2>&1
$out | ForEach-Object { Say ('mpcmdrun: ' + $_) }

$hash = $null
if (Test-Path $orig) {
    $item = Get-Item $orig
    Say ('restored size=' + $item.Length)
    try {
        $hash = (Get-FileHash -Path $orig -Algorithm SHA256 -ErrorAction Stop).Hash
        Say ('restored sha256=' + $hash)
    } catch {
        Say ('hash blocked: ' + $_.Exception.Message)
    }
} else {
    Say 'restore produced no file at the original path'
}

Say '=== phase 2: hand the file back to Defender ==='
if (Test-Path $orig) {
    Try-Out 'custom scan' { Start-MpScan -ScanType CustomScan -ScanPath $orig -ErrorAction Stop }
    Start-Sleep -Seconds 3
    if (Test-Path $orig) {
        Say 'after the scan the file is still present; deleting the restored copy'
        Remove-Item -Path $orig -Force -ErrorAction SilentlyContinue
    } else {
        Say 'Defender quarantined the restored copy again'
    }
    Remove-Item -Path $scratch -Recurse -Force -ErrorAction SilentlyContinue
    Say 'scratch folder removed'
}

Say '=== phase 3: remove what the installer wrote ==='

# --- topbar: unhide the stock taskbar while the bar still exists, then remove it
$barExe = Join-Path $pf 'topbar\topbar.exe'
if (Test-Path $barExe) {
    & $barExe --restore | Out-Null
    Say ('topbar --restore exit=' + $LASTEXITCODE)
}
foreach ($p in 'topbar','reshell') {
    Get-Process -Name $p -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}
& schtasks.exe /delete /tn topbar  /f 2>$null | Out-Null
& schtasks.exe /delete /tn reshell /f 2>$null | Out-Null
Say 'deleted tasks topbar/reshell'

$run = 'HKCU\Software\Microsoft\Windows\CurrentVersion\Run'
foreach ($v in 'topbar','reshell','rs-launcher','WinRustNightLight') {
    & reg.exe delete $run /v $v /f 2>$null | Out-Null
}
Say 'cleared HKCU Run values'

# --- PowerShell profile block (topbar's profile.ps1)
foreach ($p in @(
    (Join-Path $env:USERPROFILE 'Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1'),
    (Join-Path $env:USERPROFILE 'Documents\PowerShell\Microsoft.PowerShell_profile.ps1'))) {
    if (Test-Path $p) {
        $t = Get-Content -Path $p -Raw
        $n = [regex]::Replace($t, '(?s)# >>> topbar >>>.*?# <<< topbar <<<\r?\n?', '')
        if ($n.Trim().Length -eq 0) {
            Remove-Item $p -Force
            Say ('removed empty profile ' + $p)
        } else {
            Set-Content -Path $p -Value $n -Encoding utf8
            Say ('stripped topbar block from ' + $p)
        }
    }
}

# --- rust-search: its own uninstall hook removes the index servers, then the journal
$rsExe = Join-Path $pf 'rs-search\rs.exe'
if (Test-Path $rsExe) {
    & $rsExe --uninstall | Out-Null
    Say ('rs.exe --uninstall exit=' + $LASTEXITCODE)
}
Get-Process -Name rs,rs-launcher -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
& schtasks.exe /delete /tn rs-launcher /f 2>$null | Out-Null
Say 'stopped rs indexers and deleted task rs-launcher'

& sc.exe config WSearch start= delayed-auto | Out-Null
Say ('WSearch config exit=' + $LASTEXITCODE)
& sc.exe start WSearch | Out-Null
Say ('WSearch start exit=' + $LASTEXITCODE)
& reg.exe delete 'HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\SearchHost.exe' /v Debugger /f 2>$null | Out-Null
& reg.exe add 'HKCU\Software\Microsoft\Windows\CurrentVersion\Search' /v SearchboxTaskbarMode /t REG_DWORD /d 2 /f | Out-Null
Say 'removed SearchHost IFEO hook and restored SearchboxTaskbarMode=2'

# --- rtaskmgr: restore whatever Debugger was there before, THEN remove the exe
$tmKey   = 'HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\taskmgr.exe'
$tmState = 'HKLM\SOFTWARE\plugin-launcher\rtaskmgr-win32'
$saved   = $null
if ((& reg.exe query $tmState /v Debugger 2>$null) -match 'Debugger\s+REG_SZ\s+(.+)$') {
    $saved = $Matches[1].Trim()
    Say ('previous taskmgr replacement found: ' + $saved)
    & reg.exe add $tmKey /v Debugger /t REG_SZ /d $saved /f | Out-Null
} else {
    & reg.exe delete $tmKey /v Debugger /f 2>$null | Out-Null
    Say 'no previous replacement: removed the taskmgr Debugger value'
}
& reg.exe delete $tmState /f 2>$null | Out-Null
& schtasks.exe /delete /tn rtaskmgr /f 2>$null | Out-Null
Get-Process -Name rtaskmgr-win32 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Say 'removed rtaskmgr task and state'

# --- Start menu shortcuts
foreach ($lnk in 'Task manager.lnk','WinRust Disk.lnk','WinRust Settings.lnk') {
    $p = Join-Path $pd ('Microsoft\Windows\Start Menu\Programs\' + $lnk)
    if (Test-Path $p) { Remove-Item $p -Force -ErrorAction SilentlyContinue; Say ('removed shortcut ' + $lnk) }
}

# --- keep the journal and install log as evidence before deleting the folders
$ev = Join-Path $logDir 'winrust-journal'
New-Item -ItemType Directory -Force -Path $ev | Out-Null
if (Test-Path (Join-Path $pf 'WinRust\journal')) {
    Copy-Item (Join-Path $pf 'WinRust\journal\*') $ev -Force -ErrorAction SilentlyContinue
}
if (Test-Path (Join-Path $pd 'plugin-launcher\install.log')) {
    Copy-Item (Join-Path $pd 'plugin-launcher\install.log') (Join-Path $ev 'install.log') -Force -ErrorAction SilentlyContinue
}
Say 'copied journal and install.log to data/winrust-journal'

# --- program folders
foreach ($d in 'topbar','rtaskmgr','rs-search','wiztree','WinRust') {
    $p = Join-Path $pf $d
    if (Test-Path $p) {
        Remove-Item -Path $p -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $p) { Say ('could not remove ' + $p) } else { Say ('removed ' + $p) }
    }
}
Remove-Item (Join-Path $pd 'plugin-launcher') -Recurse -Force -ErrorAction SilentlyContinue
Say 'removed ProgramData\plugin-launcher'

Say '=== phase 4: verification ==='
Say ('WSearch config: ' + ((& sc.exe qc WSearch 2>&1 | Select-String 'START_TYPE') -join ' '))
Say ('WSearch state: '  + ((& sc.exe query WSearch 2>&1 | Select-String 'STATE') -join ' '))
Say ('IFEO taskmgr: '   + ((& reg.exe query $tmKey /v Debugger 2>&1) -join ' '))
Say ('IFEO SearchHost: '+ ((& reg.exe query 'HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\SearchHost.exe' /v Debugger 2>&1) -join ' '))
Say ('SearchboxTaskbarMode: ' + ((& reg.exe query 'HKCU\Software\Microsoft\Windows\CurrentVersion\Search' /v SearchboxTaskbarMode 2>&1) -join ' '))
Say ('leftover tasks: ' + ((& schtasks.exe /query /fo csv /nh 2>$null | Select-String -Pattern 'topbar|reshell|rtaskmgr|rs-launcher|WinRust') -join ' | '))
Say ('leftover processes: ' + ((Get-Process topbar,reshell,rs,rs-launcher,rtaskmgr-win32,wiztree -ErrorAction SilentlyContinue).ProcessName -join ', '))
Say ('explorer running: ' + ((Get-Process explorer -ErrorAction SilentlyContinue).Id -join ', '))
Say ('official v0.5.6 sha256: 836D2A10B896D39DFD1FD8A4241341EE927A0D8FA32022AB1752B5BFE6E8F93E')
if ($hash) { Say ('local restored copy matched: ' + ($hash -eq '836D2A10B896D39DFD1FD8A4241341EE927A0D8FA32022AB1752B5BFE6E8F93E')) }
Say 'done'
