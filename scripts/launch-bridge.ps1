# Launches N Among Us copies with AUBridge: copy 1 on host (hosts lobby), 2..N in Sandboxie boxes AU2..AUN (join).
# -HumanSeat $true (default): copy 1 (the human, Tarti) gets a fullscreen-sized 1920x1080 borderless window; $false: copy 1 is small like the others.
param([int]$N = 10, [switch]$NewTokens, [int]$Delay = 15, [bool]$HumanSeat = $true)
$ErrorActionPreference = 'Stop'
$tools = 'D:\AmongUs-tools'
$tokDir = "$tools\bridge\tokens"; $runDir = "$tools\bridge\run"; $logDir = "$tools\logs"
New-Item -ItemType Directory -Force $tokDir, $runDir, $logDir | Out-Null

& "$tools\stop-all.ps1"

# roster: optional [{"id":2,"name":"..","color":3}]
$roster = @{}
$rf = "$tools\bridge\roster.json"
if (Test-Path $rf) { foreach ($r in (Get-Content $rf -Raw -Encoding UTF8 | ConvertFrom-Json)) { $roster[[int]$r.id] = $r } }

function New-Token { $b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); -join ($b | ForEach-Object { $_.ToString('x2') }) }

$game = '963137e4c29d4c79a81323b8fab03a40'
$leg = "$tools\legendary\legendary.exe"
$sbx = 'D:\Program Files\Sandboxie\Start.exe'

foreach ($id in 1..$N) {
    $tf = "$tokDir\p$id.txt"
    if ($NewTokens -or -not (Test-Path $tf)) { [IO.File]::WriteAllText($tf, (New-Token)) }
    $tok = ([IO.File]::ReadAllText($tf)).Trim()
    $name = "P$id"; $color = ($id - 1) % 18
    if ($roster.ContainsKey($id)) { if ($roster[$id].name) { $name = $roster[$id].name }; if ($null -ne $roster[$id].color) { $color = [int]$roster[$id].color } }
    $mode = if ($id -eq 1) { 'host' } else { 'join' }
    $size = if ($id -eq 1 -and $HumanSeat) { '-popupwindow -screen-fullscreen 0 -screen-width 1920 -screen-height 1080' } elseif ($id -eq 1) { '-screen-width 960 -screen-height 540' } else { '-screen-width 640 -screen-height 400' }
    $cmd = "$runDir\run-au$id.cmd"
    $line = "@`"$leg`" launch $game --skip-version-check --override-exe `"D:\AmongUs-mod\Among Us.exe`" -logFile `"$logDir\bridge$id.log`" -screen-fullscreen 0 $size --aub-id=$id --aub-mode=$mode `"--aub-name=$name`" --aub-color=$color --aub-token=$tok > `"$logDir\legendary-bridge$id.log`" 2>&1"
    Set-Content -Path $cmd -Value $line -Encoding ASCII
    if ($id -eq 1) { Start-Process -FilePath $cmd -WindowStyle Hidden }
    else { Start-Process -FilePath $sbx -ArgumentList "/box:AU$id", $cmd }
    Write-Output "started copy $id ($mode, $name)"
    if ($id -lt $N) { Start-Sleep $Delay }
}
