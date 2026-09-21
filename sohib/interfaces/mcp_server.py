import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from ..tools.catalogue import VERSION
from ..tools.service import ToolService


def create_server(service=None):
    service = service or ToolService()

    async def list_tools(ctx, params):
        return ListToolsResult(tools=[Tool.model_validate(t) for t in service.catalogue['tools']])

    async def call_tool(ctx, params):
        result = await service.call_async(params.name, params.arguments)
        return CallToolResult(
            content=[TextContent(type='text', text=json.dumps(result))],
            structured_content=result,
            is_error=result['status'] == 'error',
        )

    return Server(
        'SohiB',
        version=VERSION,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        instructions='Read-only IDX research. Preserve provenance and warnings in answers. '
        'Resolve ambiguous company matches. Browser mode uses the existing session only.',
    )


async def serve():
    server = create_server()
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


def main():
    asyncio.run(serve())


if __name__ == '__main__':
    main()
