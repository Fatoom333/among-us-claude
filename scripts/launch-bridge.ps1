# Launches N Among Us copies with AUBridge: copy 1 on host (hosts lobby), 2..N in Sandboxie boxes AU2..AUN (join).
# Default: copy 1 first, wait until its bridge reports stage=lobby (max -LobbyTimeout s), then the rest in batches of -Batch with -BatchDelay s between batches.
# -Sequential: old mode, one copy after another with -Delay s pause. Stage timings go to D:\AmongUs-tools\logs\launch-<time>.log.
# -HumanSeat $true (default): copy 1 (the human, Tarti) gets a fullscreen-sized 1920x1080 borderless window; $false: copy 1 is small like the others.
param([int]$N = 10, [switch]$NewTokens, [int]$Delay = 15, [bool]$HumanSeat = $true, [switch]$Sequential, [int]$Batch = 3, [int]$BatchDelay = 5, [int]$LobbyTimeout = 120)
$ErrorActionPreference = 'Stop'
$tools = 'D:\AmongUs-tools'
$tokDir = "$tools\bridge\tokens"; $runDir = "$tools\bridge\run"; $logDir = "$tools\logs"
New-Item -ItemType Directory -Force $tokDir, $runDir, $logDir | Out-Null
# tokens and run-au*.cmd (they carry --aub-token): current user, SYSTEM and Administrators only (not BUILTIN\Users)
# (OI)(CI) only on the folder, files then inherit; /T with (OI)(CI) on files leaves them with an empty ACL. Checked: Sandboxie copies still read run-au*.cmd.
foreach ($d in $tokDir, $runDir) {
    icacls $d /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /Q | Out-Null
    if (Get-ChildItem $d -File) { icacls "$d\*" /reset /Q | Out-Null }
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$launchLog = "$logDir\launch-$stamp.log"
$t0 = Get-Date
function Log([string]$m) { Add-Content -Path $launchLog -Value ("{0:HH:mm:ss} (+{1,5:N1}s) {2}" -f (Get-Date), ((Get-Date) - $t0).TotalSeconds, $m) -Encoding UTF8 }
Log "start N=$N sequential=$($Sequential.IsPresent) batch=$Batch batchDelay=$BatchDelay"

# keep the previous mod logs (evidence) before the new run overwrites them
$prev = "$logDir\prev"; New-Item -ItemType Directory -Force $prev | Out-Null
$srcLogs = @(@{ n = 1; p = 'D:\AmongUs-mod\BepInEx\LogOutput.log' })
if ($N -ge 2) { foreach ($i in 2..$N) { $srcLogs += @{ n = $i; p = "C:\Sandbox\$($env:USERNAME)\AU$i\drive\D\AmongUs-mod\BepInEx\LogOutput.log" } } }
foreach ($l in $srcLogs) { if (Test-Path $l.p) { try { Copy-Item $l.p "$prev\LogOutput-au$($l.n)-$stamp.log" -ErrorAction Stop } catch { Log "prev log au$($l.n): $($_.Exception.Message)" } } }
Log "previous logs saved"

& "$tools\stop-all.ps1" | ForEach-Object { Log "stop-all: $_" }
Log "stopped old copies"

# Asks the bridge of seat 1 for state until stage == lobby. The token is read from the file and never printed or logged.
function Wait-Lobby([int]$TimeoutSec) {
    $tok = ([IO.File]::ReadAllText("$tokDir\p1.txt")).Trim()
    $end = (Get-Date).AddSeconds($TimeoutSec)
    $last = ''
    while ((Get-Date) -lt $end) {
        $c = New-Object Net.Sockets.TcpClient
        try {
            $iar = $c.BeginConnect('127.0.0.1', 47001, $null, $null)
            if ($iar.AsyncWaitHandle.WaitOne(2000) -and $c.Connected) {
                $c.EndConnect($iar)
                $ns = $c.GetStream(); $ns.ReadTimeout = 3000; $ns.WriteTimeout = 3000
                $req = [Text.Encoding]::UTF8.GetBytes((@{ cmd = 'state'; token = $tok } | ConvertTo-Json -Compress) + "`n")
                $ns.Write($req, 0, $req.Length)
                $sb = New-Object Text.StringBuilder; $buf = New-Object byte[] 65536
                while (-not $sb.ToString().EndsWith("`n")) { $n = $ns.Read($buf, 0, $buf.Length); if ($n -le 0) { break }; [void]$sb.Append([Text.Encoding]::UTF8.GetString($buf, 0, $n)) }
                $r = $sb.ToString() | ConvertFrom-Json
                if ($r.stage -ne $last) { $last = $r.stage; Log "host stage=$last" }
                if ($r.stage -eq 'lobby') { return $true }
            }
        } catch { } finally { $c.Close() }
        Start-Sleep -Milliseconds 1000
    }
    return $false
}

# roster: optional [{"id":2,"name":"..","color":3}]
$roster = @{}
$rf = "$tools\bridge\roster.json"
if (Test-Path $rf) { foreach ($r in (Get-Content $rf -Raw -Encoding UTF8 | ConvertFrom-Json)) { $roster[[int]$r.id] = $r } }

function New-Token { $b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); -join ($b | ForEach-Object { $_.ToString('x2') }) }

$game = '963137e4c29d4c79a81323b8fab03a40'
$leg = "$tools\legendary\legendary.exe"
$sbx = 'D:\Program Files\Sandboxie\Start.exe'

function Start-Copy([int]$id) {
    $tf = "$tokDir\p$id.txt"
    if ($NewTokens -or -not (Test-Path $tf)) { [IO.File]::WriteAllText($tf, (New-Token)) }
    $tok = ([IO.File]::ReadAllText($tf)).Trim()
    $name = "P$id"; $color = ($id - 1) % 18
    if ($roster.ContainsKey($id)) { if ($roster[$id].name) { $name = [string]$roster[$id].name }; if ($null -ne $roster[$id].color) { $color = [int]$roster[$id].color } }
    # the name lands in a .cmd line: keep only what the mod accepts anyway (ASCII letters, digits, space _ . -; the .cmd is ASCII), no quotes/&/|/%/^
    $name = ($name -replace '[^A-Za-z0-9 _.-]', '').Trim(); if ($name.Length -gt 10) { $name = $name.Substring(0, 10).Trim() }; if (-not $name) { $name = "P$id" }
    # Russian name (roster.json "ru") goes as base64 of UTF-8: only [A-Za-z0-9+/=] reaches the .cmd line; the mod decodes and validates it
    $ru = if ($roster.ContainsKey($id) -and $roster[$id].ru) { ([string]$roster[$id].ru -replace '[^\p{L}\p{Nd} _.-]', '').Trim() } else { '' }
    if ($ru.Length -gt 10) { $ru = $ru.Substring(0, 10).Trim() }
    $ruArg = if ($ru) { ' --aub-nameb64=' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($ru)) } else { '' }
    # outfit (roster.json "outfit": {hat,skin,visor,pet,nameplate}) goes as base64 of UTF-8 JSON; the mod validates ids against the catalog and ownership
    $ofArg = ''
    if ($roster.ContainsKey($id) -and $roster[$id].outfit) {
        $of = [ordered]@{}
        foreach ($f in 'hat','skin','visor','pet','nameplate') { $v = $roster[$id].outfit.$f; if ($v -is [string] -and $v.Length -gt 0 -and $v.Length -le 100) { $of[$f] = $v } }
        if ($of.Count -gt 0) { $ofArg = ' --aub-outfit=' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($of | ConvertTo-Json -Compress))) }
    }
    if ($color -lt 0 -or $color -gt 17) { $color = ($id - 1) % 18 }
    $mode = if ($id -eq 1) { 'host' } else { 'join' }
    # sound only from the human's copy; every bot copy is muted by the mod
    $mute = if ($id -eq 1 -and $HumanSeat) { '' } else { ' --aub-mute=1' }
    $size = if ($id -eq 1 -and $HumanSeat) { '-popupwindow -screen-fullscreen 0 -screen-width 1920 -screen-height 1080' } elseif ($id -eq 1) { '-screen-width 960 -screen-height 540' } else { '-screen-width 640 -screen-height 400' }
    $cmd = "$runDir\run-au$id.cmd"
    $line = "@`"$leg`" launch $game --skip-version-check --override-exe `"D:\AmongUs-mod\Among Us.exe`" -logFile `"$logDir\bridge$id.log`" -screen-fullscreen 0 $size --aub-id=$id --aub-mode=$mode `"--aub-name=$name`"$ruArg$ofArg --aub-color=$color$mute --aub-token=$tok > `"$logDir\legendary-bridge$id.log`" 2>&1"
    Set-Content -Path $cmd -Value $line -Encoding ASCII
    if ($id -eq 1) { Start-Process -FilePath $cmd -WindowStyle Hidden }
    else { Start-Process -FilePath $sbx -ArgumentList "/box:AU$id", $cmd }
    Write-Output "started copy $id ($mode, $name)"
    Log "started copy $id ($mode)"
}

if ($Sequential) {
    foreach ($id in 1..$N) { Start-Copy $id; if ($id -lt $N) { Start-Sleep $Delay } }
} else {
    Start-Copy 1
    $ok = Wait-Lobby $LobbyTimeout
    if ($ok) { Log "lobby created" } else { Log "WARNING: lobby not confirmed in $LobbyTimeout s, launching the rest anyway" }
    $rest = @(); if ($N -ge 2) { $rest = @(2..$N) }
    for ($k = 0; $k -lt $rest.Count; $k += $Batch) {
        $grp = $rest[$k..([Math]::Min($k + $Batch, $rest.Count) - 1)]
        Log ("batch: " + ($grp -join ','))
        foreach ($id in $grp) { Start-Copy $id }
        if ($k + $Batch -lt $rest.Count) { Start-Sleep $BatchDelay }
    }
}
Log "all launched"
