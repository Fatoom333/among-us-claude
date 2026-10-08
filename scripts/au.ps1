# Клиент игрока: один JSON-запрос -> ssh pc -> mcp/cli.py (тот же код проверки ключа, что и у MCP-сервера) -> JSON-ответ.
# Вызов (из PowerShell, оператор & сохраняет кавычки и кириллицу):
#   & "C:\Users\<user>\Claude work\Among Us\scripts\au.ps1" '{"op":"wait","player":3,"key":"K","timeout":50,"since":0}'
# Через "powershell -File" Windows PowerShell 5.1 съедает двойные кавычки в аргументе, поэтому так не вызывай.
# Запрос можно подать и через конвейер:  '{"op":"state",...}' | & ...\au.ps1
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Json,
      [Parameter(ValueFromPipeline = $true)][string]$Piped)
$utf8 = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = $utf8                      # PowerShell -> ssh (stdin)
[Console]::OutputEncoding = $utf8            # ssh (stdout) -> PowerShell
[Console]::InputEncoding = $utf8
$req = if ($Json) { $Json -join ' ' } else { $Piped }
if (-not $req -or $req.TrimStart()[0] -ne '{') { '{"ok":false,"error":"no json request"}'; exit 2 }
try { $null = $req | ConvertFrom-Json } catch { '{"ok":false,"error":"bad json (use: & au.ps1 ''{...}'', not powershell -File)"}'; exit 2 }
$py = 'D:/AmongUs-tools/mcp/.venv/Scripts/python.exe'
$out = $req | ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 pc $py D:/AmongUs-tools/mcp/cli.py
if ($LASTEXITCODE -ne 0 -and -not $out) { '{"ok":false,"error":"ssh failed"}'; exit 1 }
$out
