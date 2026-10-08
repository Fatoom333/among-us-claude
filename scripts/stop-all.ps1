# Kills every Among Us copy (host and all Sandboxie boxes) and the legendary launchers.
$sbx = 'D:\Program Files\Sandboxie\Start.exe'
if (Test-Path $sbx) { & $sbx /terminate_all 2>$null | Out-Null }
Get-Process -Name 'Among Us','legendary' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 3
