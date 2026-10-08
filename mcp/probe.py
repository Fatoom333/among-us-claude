import mcp, inspect
from mcp.server.fastmcp import FastMCP
print(mcp.__file__)
print(inspect.signature(FastMCP.__init__))
print(inspect.signature(FastMCP.run))
