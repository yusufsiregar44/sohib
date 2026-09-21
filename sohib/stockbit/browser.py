"""Synchronous harness boundary for an isolated Playwright browser worker."""

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from ..lock import try_lock
from .api_routes import validate_api_path, validate_body
from .contracts import ToolError

# The worker inherits only what Python, the Playwright driver and Chrome need to start.
ENVIRONMENT = frozenset(
    {
        'HOME',
        'PATH',
        'TMPDIR',
        'DISPLAY',
        'LANG',
        'XDG_RUNTIME_DIR',
        'PLAYWRIGHT_BROWSERS_PATH',
        'SYSTEMROOT',
        'SYSTEMDRIVE',
        'USERPROFILE',
        'APPDATA',
        'LOCALAPPDATA',
        'PROGRAMDATA',
        'PROGRAMFILES',
        'PROGRAMFILES(X86)',
        'TEMP',
        'TMP',
        'PATHEXT',
        'COMSPEC',
    }
)


def default_paths():
    from ..onboarding import home

    root = home()
    return root / 'browser.json', root / 'chrome'


def isolation():
    if sys.platform == 'win32':
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}


def terminate(process):
    """Stop the worker and its browser driver. The user's browser is never touched."""
    if process.poll() is not None:
        return
    if sys.platform == 'win32':
        subprocess.run(
            ['taskkill', '/F', '/T', '/PID', str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


class Reader:
    """Pump a pipe on a thread so waiting stays portable and interruptible."""

    def __init__(self, stream):
        self.chunks = queue.Queue()
        self.thread = threading.Thread(target=self._pump, args=(stream,), daemon=True)
        self.thread.start()

    def _pump(self, stream):
        try:
            while chunk := os.read(stream.fileno(), 65536):
                self.chunks.put(chunk)
        except OSError:
            pass
        finally:
            self.chunks.put(None)

    def __iter__(self):
        while True:
            try:
                chunk = self.chunks.get(timeout=0.05)
            except queue.Empty:
                yield b''
                continue
            if chunk is None:
                return
            yield chunk


class PlaywrightBrowser:
    def __init__(self, profile=None, cancel=None, connection_file=None, transport='fetch'):
        if transport not in {'fetch', 'observe'}:
            raise ValueError('Browser transport must be fetch or observe.')
        # fetch issues allowlisted API requests from the signed-in page; observe is the
        # navigate-and-eavesdrop fallback kept for the three original routes.
        self.transport = transport
        default_connection, default_profile = default_paths()
        self.profile = Path(profile).expanduser().resolve() if profile else default_profile
        self.cancel = cancel or threading.Event()
        self.connection_file = (
            Path(connection_file).expanduser().resolve() if connection_file else default_connection
        )

    def fetch(self, path, *, timeout=40, body=None):
        if self.cancel.is_set():
            raise ToolError('CANCELLED', 'Browser research was cancelled.')
        self.profile.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = self.profile.with_suffix('.lock')
        with lock_path.open('a') as lock:
            os.chmod(lock_path, 0o600)
            if not try_lock(lock):
                raise ToolError('UPSTREAM_ERROR', 'The research browser profile is busy.')
            return self._run(path, timeout, body)

    def _run(self, path, timeout, body=None):
        paths = [path] if isinstance(path, str) else list(path or [])
        if not paths:
            raise ToolError('UNSUPPORTED_INPUT', 'A research route is required.')
        env = {k: v for k, v in os.environ.items() if k.upper() in ENVIRONMENT}
        args = [
            sys.executable,
            '-m',
            'sohib.stockbit.playwright_worker',
            '--timeout',
            str(timeout),
            '--connection-file',
            str(self.connection_file),
        ]
        for item in paths:
            args += ['--path', item]
        if self.transport == 'fetch':
            args.append('--fetch')
        if body is not None:
            args += ['--body', json.dumps(body)]
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, **isolation()
        )
        deadline = time.monotonic() + timeout + 5
        output = bytearray()
        reader = Reader(process.stdout)
        try:
            for chunk in reader:
                if self.cancel.is_set():
                    raise ToolError('CANCELLED', 'Browser research was cancelled.')
                if time.monotonic() >= deadline:
                    raise ToolError('TIMEOUT', 'Browser worker exceeded its time budget.')
                output.extend(chunk)
                if len(output) > 4_000_000:
                    raise ToolError(
                        'SCHEMA_CHANGED', 'Browser response exceeds the capture budget.'
                    )
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
            result = json.loads(output)
            if not isinstance(result, dict):
                raise ValueError
            if result.get('error'):
                error = result['error']
                raise ToolError(error['code'], error['message'])
            if process.returncode or not isinstance(result.get('payload'), dict):
                raise ValueError
            if 'payloads' in result and not (
                isinstance(result['payloads'], list)
                and all(isinstance(item, dict) for item in result['payloads'])
            ):
                raise ValueError
            return result
        except KeyboardInterrupt:
            raise ToolError('CANCELLED', 'Browser research was cancelled.') from None
        except subprocess.TimeoutExpired:
            raise ToolError('TIMEOUT', 'Browser worker exceeded its time budget.') from None
        except (ValueError, KeyError, TypeError):
            raise ToolError('SCHEMA_CHANGED', 'Unexpected browser worker response.') from None
        finally:
            terminate(process)
            reader.thread.join(timeout=1)
            process.stdout.close()


class BrowserSession:
    def __init__(self, client=None, timeout=40):
        self.client = client or PlaywrightBrowser()
        self.timeout = timeout
        self.state = 'UNVERIFIED'
        self.source_url = None

    def status(self):
        return {
            'state': self.state,
            'transport': 'playwright',
            'retrieval': 'in-page fetch of allowlisted API routes',
            'browser': 'headed Google Chrome',
            'session_policy': 'attach existing browser only; no login fallback',
            'verification': 'last operation only',
        }

    def get(self, path):
        return self.get_many([path])[0]

    def get_many(self, paths):
        """Fetch several allowlisted routes through one browser attachment."""
        paths = list(paths)
        for path in paths:
            validate_api_path(path)
        result = self._call(paths)
        payloads = result.get('payloads') or [result['payload']]
        if len(payloads) != len(paths):
            raise ToolError('SCHEMA_CHANGED', 'Unexpected browser worker response.')
        return payloads

    def post(self, path, body):
        validate_body(path, body)
        return self._call([path], body)['payload']

    def _call(self, paths, body=None):
        try:
            result = self.client.fetch(paths, timeout=self.timeout, body=body)
            self.source_url = result['source_url']
            self.state = 'READY'
            return result
        except ToolError as error:
            if error.code == 'AUTH_REQUIRED' and self.state == 'READY':
                error = ToolError('AUTH_EXPIRED', 'The browser session expired; sign in again.')
            self.state = error.code
            raise error
