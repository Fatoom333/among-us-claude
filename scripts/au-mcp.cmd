@echo off
rem MCP server "au" launcher for both machines (stdio passthrough).
rem On the stand PC (where D:\AmongUs-tools exists) the server runs directly; elsewhere it runs there over ssh (host alias "pc").
if exist "D:\AmongUs-tools\mcp\server.py" (
  "D:\AmongUs-tools\mcp\.venv\Scripts\python.exe" "D:\AmongUs-tools\mcp\server.py"
) else (
  ssh -o BatchMode=yes -o ServerAliveInterval=15 pc D:/AmongUs-tools/mcp/.venv/Scripts/python.exe D:/AmongUs-tools/mcp/server.py
)
