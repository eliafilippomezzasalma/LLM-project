"""Server MCP di prova: lo strumento `muori` termina il processo, come un server che si blocca."""

import os

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server


async def _elenca(contesto, parametri) -> types.ListToolsResult:
    return types.ListToolsResult(
        tools=[types.Tool(name="muori", description="termina il server", input_schema={"type": "object"})]
    )


async def _chiama(contesto, parametri) -> types.CallToolResult:
    os._exit(1)


async def principale() -> None:
    server = Server("che-muore", on_list_tools=_elenca, on_call_tool=_chiama)
    async with stdio_server() as (lettura, scrittura):
        await server.run(lettura, scrittura, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(principale)
