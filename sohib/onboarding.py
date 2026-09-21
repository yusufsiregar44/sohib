"""Local installation state, explicit browser setup, and harness configuration."""

import argparse
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from .lock import try_lock


def home():
    if os.getenv('SOHIB_HOME'):
        return Path(os.environ['SOHIB_HOME']).expanduser().resolve()
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/SohiB'
    if sys.platform == 'win32':
        return Path(os.getenv('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'SohiB'
    return Path(os.getenv('XDG_DATA_HOME', Path.home() / '.local/share')) / 'sohib'


def read_config():
    path = home() / 'config.json'
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if data['version'] != 1 or data['browser_kind'] not in {'managed', 'existing'}:
            raise ValueError
        for key in ('connection_file', 'profile'):
            if not isinstance(data[key], str) or not Path(data[key]).is_absolute():
                raise ValueError
        return data
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError(
            'SohiB configuration is invalid; repair config.json before continuing.'
        ) from None


def save_private(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.sohib-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def setup(connection_file=None, profile=None):
    if read_config() is not None:
        return {'status': 'configured', 'message': 'Existing settings retained.'}
    root = home()
    if connection_file:
        from .stockbit.playwright_worker import connection_endpoint

        connection_file = Path(connection_file).expanduser().resolve()
        connection_endpoint(connection_file)
        if not profile:
            raise ValueError('Existing-browser setup requires its existing profile lock path.')
    else:
        connection_file = root / 'browser.json'
    config = {
        'version': 1,
        'browser_kind': 'existing' if profile else 'managed',
        'connection_file': str(connection_file),
        'profile': str(Path(profile).expanduser().resolve() if profile else root / 'chrome'),
    }
    if config['browser_kind'] == 'managed':
        save_private(connection_file, {'devtools_file': str(root / 'chrome/DevToolsActivePort')})
    save_private(root / 'config.json', config)
    return {
        'status': 'configured',
        'browser': config['browser_kind'],
        'message': 'Run sohib connect to open or reconnect the browser, then sohib doctor.',
    }


def require_config():
    config = read_config()
    if config is None:
        raise ValueError('Run sohib setup first.')
    return config


def endpoint_alive(config):
    from .stockbit.playwright_worker import connection_endpoint

    try:
        endpoint = connection_endpoint(config['connection_file'])
        # Ignore HTTP proxy environment variables for loopback browser control.
        with build_opener(ProxyHandler({})).open(endpoint + '/json/version', timeout=1) as response:
            data = json.loads(response.read(65536))
        return isinstance(data.get('webSocketDebuggerUrl'), str)
    except Exception:
        return False


def chrome_path():
    supplied = os.getenv('SOHIB_CHROME_BINARY')
    if supplied:
        candidate = Path(supplied).expanduser().resolve()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        raise ValueError('SOHIB_CHROME_BINARY must name an executable Chrome binary.')
    if sys.platform == 'darwin':
        candidate = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        if candidate.is_file():
            return str(candidate)
    if sys.platform == 'win32':
        for base in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            root = os.getenv(base)
            candidate = Path(root or '') / 'Google/Chrome/Application/chrome.exe'
            if root and candidate.is_file():
                return str(candidate)
    for name in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome'):
        if path := shutil.which(name):
            return path
    raise ValueError('Install Google Chrome or set SOHIB_CHROME_BINARY to its executable.')


def detached():
    """Let Chrome outlive this command on every platform."""
    if sys.platform == 'win32':
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
    return {'start_new_session': True}


def connect():
    config = require_config()
    if endpoint_alive(config):
        return {
            'status': 'browser_running',
            'message': 'Existing browser retained; run sohib doctor.',
        }
    if config['browser_kind'] == 'existing':
        raise ValueError(
            'Configured browser is unavailable. Restore it; no replacement was opened.'
        )
    root = home()
    with (root / 'browser-start.lock').open('a') as lock:
        if not try_lock(lock):
            raise ValueError('Another connect operation is already running.')
        if endpoint_alive(config):
            return {'status': 'browser_running'}
        profile = Path(config['profile'])
        profile.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(profile, 0o700)
        process = subprocess.Popen(
            [
                chrome_path(),
                f'--user-data-dir={profile}',
                '--remote-debugging-address=127.0.0.1',
                '--remote-debugging-port=0',
                '--no-first-run',
                '--no-default-browser-check',
                'https://stockbit.com/login',
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **detached(),
        )
        for _ in range(40):
            if endpoint_alive(config):
                return {
                    'status': 'browser_opened',
                    'message': 'Sign in and complete verification in Chrome. Then run sohib doctor. '
                    'The profile is retained across browser restarts.',
                }
            if process.poll() is not None:
                break
            time.sleep(0.25)
        raise ValueError(
            'Chrome did not expose its connection. Check the browser; no retry was started.'
        )


async def session_check(config):
    from playwright.async_api import async_playwright

    from .stockbit.playwright_worker import check_page, connection_endpoint

    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(
            connection_endpoint(config['connection_file']), timeout=10000
        )
        from urllib.parse import urlsplit

        pages = [
            p
            for c in browser.contexts
            for p in c.pages
            if urlsplit(p.url).scheme == 'https' and urlsplit(p.url).netloc == 'stockbit.com'
        ]
        if len(pages) != 1:
            raise ValueError('Keep exactly one Stockbit tab open in the configured browser.')
        await check_page(pages[0])
        # Disconnect the driver only; never close the user-owned browser.


def doctor(smoke=None):
    config = require_config()
    for module in ('mcp', 'playwright'):
        if importlib.util.find_spec(module) is None:
            raise ValueError('Install SohiB with pip so that mcp and playwright are available.')
    if not endpoint_alive(config):
        raise ValueError('Browser is unavailable. Run sohib connect explicitly.')
    asyncio.run(session_check(config))
    if smoke:
        from .tools.config import ToolSettings
        from .tools.service import ToolService

        result = ToolService(
            ToolSettings('browser', config['connection_file'], config['profile'])
        ).call('search_companies', {'query': smoke})
        return result
    return {
        'status': 'session_available',
        'message': 'Browser is connected and no login challenge is visible. '
        'Use --smoke SYMBOL to verify research access.',
    }


def harness_config(client):
    config = require_config()
    entry = {
        'command': sys.executable,
        'args': ['-m', 'sohib.interfaces.mcp_server'],
        'env': {
            'SOHIB_HOME': str(home()),
            'STOCKBIT_MODE': 'browser',
            'STOCKBIT_BROWSER_CONNECTION_FILE': config['connection_file'],
            'STOCKBIT_BROWSER_PROFILE': config['profile'],
        },
    }
    if client == 'codex':
        lines = [
            '[mcp_servers.sohib]',
            f'command = {json.dumps(entry["command"])}',
            f'args = {json.dumps(entry["args"])}',
            'startup_timeout_sec = 20',
            'tool_timeout_sec = 60',
            '',
            '[mcp_servers.sohib.env]',
        ]
        return '\n'.join(lines + [f'{k} = {json.dumps(v)}' for k, v in entry['env'].items()])
    if client == 'openclaw':
        return json.dumps({'mcpServers': {'sohib': entry}, 'imports': []}, indent=2)
    return json.dumps({'mcpServers': {'sohib': {'type': 'stdio', **entry}}}, indent=2)


def main():
    parser = argparse.ArgumentParser(description='SohiB local setup and browser lifecycle')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('setup')
    init.add_argument('--connection-file')
    init.add_argument('--profile')
    commands.add_parser('connect')
    health = commands.add_parser('doctor')
    health.add_argument('--smoke', metavar='SYMBOL')
    harness = commands.add_parser('config')
    harness.add_argument('client', choices=['codex', 'claude', 'openclaw', 'mcp'])
    args = parser.parse_args()
    try:
        if args.command == 'config':
            print(harness_config(args.client))
            return 0
        if args.command == 'setup':
            if args.profile and not args.connection_file:
                raise ValueError('--profile requires --connection-file.')
            result = setup(args.connection_file, args.profile)
        elif args.command == 'connect':
            result = connect()
        else:
            result = doctor(args.smoke)
        print(json.dumps(result, indent=2))
        return 1 if result.get('status') == 'error' else 0
    except Exception as error:
        from .stockbit.contracts import ToolError

        message = (
            str(error)
            if isinstance(error, ValueError | ToolError)
            else 'Setup operation failed. Check local browser and installation.'
        )
        print(json.dumps({'status': 'error', 'message': message}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
