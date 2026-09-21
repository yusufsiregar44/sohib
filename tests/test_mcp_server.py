import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import anyio
from jsonschema import validate
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from sohib.interfaces.mcp_server import create_server
from sohib.stockbit.contracts import ToolError, envelope
from sohib.tools.catalogue import OUTPUT_SCHEMA
from sohib.tools.config import ToolSettings
from sohib.tools.service import ToolService

ROOT = Path(__file__).resolve().parents[1]


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_domain_errors_preserve_envelope(self):
        service = ToolService(ToolSettings('fixture'))
        async with Client(create_server(service)) as client:
            for code in [
                'AUTH_REQUIRED',
                'AUTH_EXPIRED',
                'AUTH_CHALLENGE',
                'TIMEOUT',
                'SCHEMA_CHANGED',
                'FORBIDDEN',
            ]:
                evidence = envelope(error=ToolError(code, 'Research unavailable.'))
                with patch('sohib.tools.service.StockbitTools.call', return_value=evidence):
                    result = await client.call_tool('search_companies', {'query': 'SIDO'})
                self.assertTrue(result.is_error)
                self.assertEqual(result.structured_content, evidence)
                self.assertEqual(json.loads(result.content[0].text), evidence)

    async def test_client_cancellation_reaches_worker_and_server_recovers(self):
        service = ToolService(ToolSettings('fixture'))
        started, cleaned = threading.Event(), threading.Event()

        def slow_call(name, args, cancel):
            started.set()
            if not cancel.wait(3):
                raise AssertionError('MCP cancellation did not reach worker')
            cleaned.set()
            return envelope(error=ToolError('CANCELLED', 'Cancelled'))

        async with Client(create_server(service)) as client:
            with patch.object(service, 'call', side_effect=slow_call):
                async with anyio.create_task_group() as group:
                    group.start_soon(client.call_tool, 'search_companies', {'query': 'AKRA'})
                    with anyio.fail_after(2):
                        while not started.is_set():
                            await anyio.sleep(0.01)
                    group.cancel_scope.cancel()
                with anyio.fail_after(2):
                    while not cleaned.is_set():
                        await anyio.sleep(0.01)
            result = await client.call_tool('search_companies', {'query': 'AKRA'})
            self.assertFalse(result.is_error)

    async def test_stdio_discovery_and_three_tool_calls(self):
        params = StdioServerParameters(
            command=sys.executable,
            args=['-m', 'sohib.interfaces.mcp_server'],
            cwd=str(ROOT),
            env={**os.environ, 'STOCKBIT_MODE': 'fixture'},
        )
        async with Client(params, read_timeout_seconds=10) as client:
            discovered = await client.list_tools()
            self.assertEqual(
                {t.name for t in discovered.tools},
                {'search_companies', 'get_key_statistics', 'list_metrics'},
            )
            for name, args in [
                ('search_companies', {'query': 'AKRA'}),
                ('get_key_statistics', {'symbol': 'MAPI', 'query': '', 'page': 1}),
                (
                    'list_metrics',
                    {'symbol': 'MAPI', 'namespace': 'keystats', 'query': '', 'page': 1},
                ),
            ]:
                result = await client.call_tool(name, args)
                self.assertFalse(result.is_error)
                validate(result.structured_content, OUTPUT_SCHEMA)
                self.assertEqual(json.loads(result.content[0].text), result.structured_content)
                self.assertTrue(result.structured_content['records'])
            for name, args in [('unknown', {}), ('search_companies', {'query': 12})]:
                result = await client.call_tool(name, args)
                self.assertTrue(result.is_error)
                self.assertEqual(result.structured_content['error']['code'], 'UNSUPPORTED_INPUT')

    async def test_missing_browser_connection_is_explicit_error(self):
        with tempfile.TemporaryDirectory() as directory:
            params = StdioServerParameters(
                command=sys.executable,
                args=['-m', 'sohib.interfaces.mcp_server'],
                cwd=str(ROOT),
                env={
                    **os.environ,
                    'STOCKBIT_MODE': 'browser',
                    'STOCKBIT_BROWSER_CONNECTION_FILE': str(Path(directory) / 'missing.json'),
                    'STOCKBIT_BROWSER_PROFILE': str(Path(directory) / 'profile'),
                },
            )
            async with Client(params, read_timeout_seconds=20) as client:
                result = await client.call_tool('search_companies', {'query': 'SIDO'})
        self.assertTrue(result.is_error)
        self.assertEqual(result.structured_content['error']['code'], 'UPSTREAM_ERROR')
