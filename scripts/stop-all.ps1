# Soft stop of every Among Us copy (host + Sandboxie boxes), then hard stop for the rest and the legendary launchers.
# Output: "soft=<n> hard=<m>". -Wait: seconds to let windows close by themselves.
param([int]$Wait = 10)
$sbx = 'D:\Program Files\Sandboxie\Start.exe'
$procs = @(Get-Process -Name 'Among Us' -ErrorAction SilentlyContinue)
$total = $procs.Count
foreach ($p in $procs) { try { [void]$p.CloseMainWindow() } catch {} }
$deadline = (Get-Date).AddSeconds($Wait)
while ((Get-Date) -lt $deadline -and @(Get-Process -Name 'Among Us' -ErrorAction SilentlyContinue).Count -gt 0) { Start-Sleep -Milliseconds 500 }
$left = @(Get-Process -Name 'Among Us' -ErrorAction SilentlyContinue)
if ($left.Count -gt 0 -and (Test-Path $sbx)) {
    # fallback for sandboxed copies whose windows did not react: terminate each box that still has a process
    foreach ($i in 2..15) { & $sbx "/box:AU$i" /terminate 2>$null | Out-Null }
    Start-Sleep 2
    $left = @(Get-Process -Name 'Among Us' -ErrorAction SilentlyContinue)
}
$hard = $left.Count
if ($hard -gt 0) { $left | Stop-Process -Force -ErrorAction SilentlyContinue }
if (Test-Path $sbx) { & $sbx /terminate_all 2>$null | Out-Null }
Get-Process -Name 'legendary' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 2
Write-Output ("soft={0} hard={1}" -f ($total - $hard), $hard)
