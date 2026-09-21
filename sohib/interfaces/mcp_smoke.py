"""Launch the stdio server as a real client; preserve only a compact evidence summary."""

import argparse
import asyncio
import json
import os
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters


async def smoke(symbol):
    env = {**os.environ, 'STOCKBIT_MODE': os.getenv('STOCKBIT_MODE', 'fixture')}
    query = 'Mitra Adiperkasa' if env['STOCKBIT_MODE'] == 'fixture' and symbol == 'MAPI' else symbol
    params = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'sohib.interfaces.mcp_server'],
        env=env,
    )
    async with Client(params, read_timeout_seconds=60) as client:
        print('Discovered:', ', '.join(t.name for t in (await client.list_tools()).tools))
        for name, args in [
            ('search_companies', {'query': query}),
            ('get_key_statistics', {'symbol': symbol, 'query': 'return on', 'page': 1}),
            (
                'list_metrics',
                {'symbol': symbol, 'query': 'return on', 'page': 1, 'namespace': 'keystats'},
            ),
        ]:
            response = await client.call_tool(name, args)
            result = response.structured_content
            print(
                json.dumps(
                    {
                        'tool': name,
                        'status': result['status'],
                        'error': result['error'],
                        'records': [
                            {
                                'label': r['label'],
                                'value': r['value'],
                                'source_url': r['attributes'].get('source_url'),
                            }
                            for r in result['records']
                        ],
                    }
                ),
                flush=True,
            )
            if response.is_error:
                return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol', default='MAPI', help='Use SIDO for browser smoke testing')
    return asyncio.run(smoke(parser.parse_args().symbol))


if __name__ == '__main__':
    raise SystemExit(main())
