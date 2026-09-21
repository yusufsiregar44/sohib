"""Call SohiB via OpenClaw's mcporter workflow without configuring OpenClaw."""

import argparse
import importlib.util
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def python_executable():
    """The interpreter that has SohiB installed; session paths come from `sohib setup`."""
    if os.environ.get('SOHIB_PYTHON'):
        return os.environ['SOHIB_PYTHON']
    if importlib.util.find_spec('sohib') is not None:
        return sys.executable
    candidate = ROOT / ('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    if candidate.is_file():
        return str(candidate)
    raise ValueError('Install SohiB in this Python (pip install sohib) or set SOHIB_PYTHON.')


def command(args):
    node = shutil.which('node')
    client = HERE / 'node_modules/mcporter/dist/cli.js'
    if not node or not client.is_file():
        raise ValueError(
            'Install Node and run npm ci --prefix integrations/openclaw --ignore-scripts.'
        )
    python = python_executable()
    env = os.environ.copy()
    env.setdefault('STOCKBIT_MODE', 'browser')
    argv = [node, str(client), '--config', str(HERE / 'mcporter.json'), args.command]
    argv += [
        '--stdio',
        shlex.quote(str(python)),
        '--stdio-arg',
        '-m',
        '--stdio-arg',
        'sohib.interfaces.mcp_server',
        '--cwd',
        str(ROOT),
        '--name',
        'sohib',
        '--timeout',
        '60000',
    ]
    if args.command == 'list':
        argv += ['--json']
    else:
        payload = json.loads(args.arguments)
        if not isinstance(payload, dict):
            raise ValueError('Tool arguments must be a JSON object.')
        argv += [args.tool, '--args', json.dumps(payload), '--output', 'json']
    return argv, env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    call = commands.add_parser('call')
    call.add_argument(
        'tool',
        choices=[
            'search_companies',
            'get_key_statistics',
            'list_metrics',
            'get_company_summary',
            'get_financial_statements',
            'get_fundamental_history',
            'get_price_series',
            'get_price_performance',
            'get_analyst_consensus',
            'get_peer_comparison',
            'get_corporate_actions',
            'get_dividend_calendar',
            'screen_equities',
        ],
    )
    call.add_argument('--arguments', required=True)
    args = parser.parse_args()
    try:
        argv, env = command(args)
    except ValueError as error:
        parser.error(str(error))
    # Replace the launcher so the calling harness owns the mcporter process directly.
    os.chdir(ROOT)
    os.execvpe(argv[0], argv, env)


if __name__ == '__main__':
    main()
