@echo off
rem MCP server "au" launcher for both machines (stdio passthrough).
rem On the PC the server runs directly; elsewhere it runs on the PC over ssh.
if /i "%COMPUTERNAME%"=="STAND-PC" (
  "D:\AmongUs-tools\mcp\.venv\Scripts\python.exe" "D:\AmongUs-tools\mcp\server.py"
) else (
  ssh -o BatchMode=yes -o ServerAliveInterval=15 pc D:/AmongUs-tools/mcp/.venv/Scripts/python.exe D:/AmongUs-tools/mcp/server.py
)
