import os
import threading
import unittest
from unittest.mock import patch

import anyio

from sohib.stockbit.contracts import ToolError, envelope
from sohib.tools.catalogue import catalogue
from sohib.tools.config import ToolSettings
from sohib.tools.service import ToolService


class ToolServiceTests(unittest.TestCase):
    def test_tool_descriptions_distinguish_live_retrieval_from_fixture_replay(self):
        # A native MCP host previously labelled live BBCA data as historical because
        # the fixture warning was included in browser-mode tool descriptions.
        for tool in catalogue('browser')['tools']:
            self.assertIn('Live retrieval through the signed-in browser', tool['description'])
            self.assertNotIn('Fixture results are historical examples', tool['description'])
            self.assertNotIn('Historical fixture replay', tool['description'])
        for tool in catalogue('fixture')['tools']:
            self.assertIn('Synthetic test examples, not observed market data', tool['description'])
        for tool in catalogue('disabled')['tools']:
            self.assertIn('without retrieving data', tool['description'])

    def test_configuration_needs_no_model_credentials(self):
        with patch.dict(os.environ, {'STOCKBIT_MODE': 'fixture', 'SOHIB_HOME': '/nonexistent'}):
            service = ToolService()
        self.assertNotEqual(service.call('search_companies', {'query': 'AKRA'})['status'], 'error')

    def test_schema_rejects_unknown_and_malformed_arguments(self):
        service = ToolService(ToolSettings('fixture'))
        for name, args in [
            ('unknown', {}),
            ('search_companies', {'query': ''}),
            ('search_companies', {'query': 'AKRA', 'token': 'secret'}),
            ('get_key_statistics', {'symbol': 'MAPI', 'query': '', 'page': True}),
        ]:
            self.assertEqual(service.call(name, args)['error']['code'], 'UNSUPPORTED_INPUT')

    def test_output_validation_and_exception_redaction(self):
        service = ToolService(ToolSettings('fixture'))
        with patch('sohib.tools.service.StockbitTools.call', return_value={'bad': 'output'}):
            self.assertEqual(
                service.call('search_companies', {'query': 'AKRA'})['error']['code'],
                'SCHEMA_CHANGED',
            )
        with patch('sohib.tools.service.StockbitTools.call', side_effect=RuntimeError('secret')):
            self.assertNotIn('secret', str(service.call('search_companies', {'query': 'AKRA'})))

    def test_busy_and_pre_cancelled(self):
        service = ToolService(ToolSettings('fixture'))
        event = threading.Event()
        event.set()
        self.assertEqual(
            service.call('search_companies', {'query': 'AKRA'}, event)['error']['code'], 'CANCELLED'
        )
        with service.lock:
            self.assertEqual(
                service.call('search_companies', {'query': 'AKRA'})['error']['code'],
                'UPSTREAM_ERROR',
            )

    def test_async_cancellation_waits_for_worker_cleanup(self):
        started, cleaned = threading.Event(), threading.Event()
        service = ToolService(ToolSettings('fixture'))

        def work(name, args, cancel):
            started.set()
            if not cancel.wait(2):
                raise AssertionError('Cancellation never reached worker')
            cleaned.set()
            return envelope(error=ToolError('CANCELLED', 'Cancelled'))

        async def run():
            async with anyio.create_task_group() as group:
                group.start_soon(service.call_async, 'search_companies', {'query': 'AKRA'})
                while not started.is_set():
                    await anyio.sleep(0.01)
                group.cancel_scope.cancel()
            self.assertTrue(cleaned.is_set())

        with patch.object(service, 'call', side_effect=work):
            anyio.run(run)
