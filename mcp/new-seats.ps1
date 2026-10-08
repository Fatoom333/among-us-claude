# Генерирует D:\AmongUs-tools\bridge\seats.json: случайный ключ (32 байта hex) на каждое место 1..10.
# Ключи на экран не выводятся. Запускать перед партией; старые ключи перестают действовать.
$ErrorActionPreference = 'Stop'
$dir = 'D:\AmongUs-tools\bridge'
New-Item -ItemType Directory -Force $dir | Out-Null
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$seats = [ordered]@{}
foreach ($i in 1..10) {
    $b = New-Object byte[] 32
    $rng.GetBytes($b)
    $seats["$i"] = ($b | ForEach-Object { $_.ToString('x2') }) -join ''
}
$json = $seats | ConvertTo-Json
[System.IO.File]::WriteAllText("$dir\seats.json", $json, (New-Object System.Text.UTF8Encoding($false)))
# доступ только текущему пользователю
icacls "$dir\seats.json" /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
Write-Host "seats.json written: 10 keys"
