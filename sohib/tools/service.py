import threading

import anyio
from jsonschema import Draft202012Validator

from ..stockbit.browser import BrowserSession, PlaywrightBrowser
from ..stockbit.contracts import ToolError, envelope
from ..stockbit.provider import StockbitTools
from .catalogue import OUTPUT_SCHEMA, catalogue
from .config import ToolSettings


class ToolService:
    def __init__(self, settings=None):
        self.settings = settings or ToolSettings.load()
        self.catalogue = catalogue(self.settings.mode)
        self.inputs = {
            t['name']: Draft202012Validator(t['inputSchema']) for t in self.catalogue['tools']
        }
        self.output = Draft202012Validator(OUTPUT_SCHEMA)
        self.lock = threading.Lock()

    def call(self, name, arguments, cancel=None):
        cancel = cancel or threading.Event()
        validator = self.inputs.get(name)
        if validator is None or not validator.is_valid(arguments):
            return envelope(
                error=ToolError(
                    'UNSUPPORTED_INPUT', 'Unknown tool or arguments do not match its schema.'
                )
            )
        # Bound contention explicitly; never queue competing navigation indefinitely.
        if not self.lock.acquire(blocking=False):
            return envelope(error=ToolError('UPSTREAM_ERROR', 'Research service is busy.'))
        try:
            if cancel.is_set():
                return envelope(error=ToolError('CANCELLED', 'Research was cancelled.'))
            session = None
            if self.settings.mode == 'browser':
                session = BrowserSession(
                    PlaywrightBrowser(
                        profile=self.settings.profile,
                        connection_file=self.settings.connection_file,
                        cancel=cancel,
                    )
                )
            result = StockbitTools(mode=self.settings.mode, session=session).call(name, arguments)
            if not self.output.is_valid(result):
                return envelope(error=ToolError('SCHEMA_CHANGED', 'Invalid normalized evidence.'))
            return result
        except Exception:
            # Exception text may contain provider/session data; never return it to a harness.
            return envelope(error=ToolError('UPSTREAM_ERROR', 'Research operation failed.'))
        finally:
            self.lock.release()

    async def call_async(self, name, arguments):
        cancel = threading.Event()

        async def watch_cancel():
            try:
                await anyio.sleep_forever()
            finally:
                cancel.set()

        async with anyio.create_task_group() as group:
            group.start_soon(watch_cancel)
            try:
                # Shield thread completion, not the watcher: cancellation stops the worker
                # and waits for its cleanup before acknowledging request termination.
                result = await anyio.to_thread.run_sync(self.call, name, arguments, cancel)
            finally:
                group.cancel_scope.cancel()
        return result
