import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from jsonschema import validate

from sohib.stockbit.api_routes import citation, validate_api_path
from sohib.stockbit.browser import BrowserSession, PlaywrightBrowser
from sohib.stockbit.contracts import ToolError
from sohib.stockbit.playwright_worker import (
    FETCH_JSON,
    check_page,
    classify,
    fetch_json,
    matches,
    retrieve,
)
from sohib.stockbit.provider import FIXTURES, StockbitTools
from sohib.stockbit.search import search_path


class BrowserDouble:
    """Stands in for PlaywrightBrowser; payload may be one dict or a per-path list."""

    def __init__(self, payload):
        self.payload = payload
        self.error = None
        self.paths = []
        self.bodies = []

    def fetch(self, path, body=None, **kwargs):
        paths = [path] if isinstance(path, str) else list(path)
        self.paths.extend(paths)
        self.bodies.append(body)
        if self.error:
            raise ToolError(self.error, 'Browser test error.')
        payloads = self.payload if isinstance(self.payload, list) else [self.payload] * len(paths)
        return {'payload': payloads[0], 'payloads': payloads, 'source_url': citation(paths[0])}


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.examples = json.loads((FIXTURES / 'company-search.json').read_text())['examples']
        self.client = BrowserDouble(self.examples[0]['response'])
        self.session = BrowserSession(self.client)
        self.tools = StockbitTools('browser', session=self.session)

    def search(self, query='AKRA'):
        result = self.tools.call('search_companies', {'query': query})
        validate(result, json.loads((FIXTURES / 'output.schema.json').read_text()))
        return result

    def test_symbol_and_warrants(self):
        result = self.search()
        self.assertEqual([r['symbol'] for r in result['records']], ['AKRA'])
        self.assertEqual(result['records'][0]['attributes']['retrieval_mode'], 'browser')
        self.assertIsNone(result['provenance']['fixture_ref'])
        self.assertEqual(self.client.paths, [search_path('AKRA')])

    def test_company_name_ambiguity(self):
        example = self.examples[1]
        self.client.payload = example['response']
        result = self.search(example['query'])
        self.assertGreater(len(result['records']), 1)
        self.assertTrue(any('Multiple equity' in w for w in result['warnings']))

    def test_empty_and_changed_schema(self):
        self.client.payload = {'data': {'company': []}}
        self.assertEqual(self.search()['records'], [])
        self.client.payload = {'unexpected': []}
        self.assertEqual(self.search()['error']['code'], 'SCHEMA_CHANGED')

    def test_errors_and_session_expiry(self):
        for code in (
            'AUTH_REQUIRED',
            'AUTH_CHALLENGE',
            'TIMEOUT',
            'CANCELLED',
            'FORBIDDEN',
            'AUTH_EXPIRED',
        ):
            self.client.error = code
            self.session.state = 'UNVERIFIED'
            self.assertEqual(self.search()['error']['code'], code)
        self.session.state = 'READY'
        self.client.error = 'AUTH_REQUIRED'
        self.assertEqual(self.search()['error']['code'], 'AUTH_EXPIRED')

    def test_statistics_and_metrics(self):
        self.client.payload = json.loads((FIXTURES / 'mapi-keystats.json').read_text())
        for name in ('get_key_statistics', 'list_metrics'):
            args = {'symbol': 'MAPI', 'query': '', 'page': 1}
            if name == 'list_metrics':
                args['namespace'] = 'keystats'
            result = self.tools.call(name, args)
            self.assertTrue(result['records'])
            if name == 'list_metrics':
                self.assertTrue(all(r['value'] is None for r in result['records']))
        self.client.payload = json.loads((FIXTURES / 'screener-metrics.json').read_text())
        self.assertTrue(
            self.tools.call(
                'list_metrics', {'namespace': 'screener', 'symbol': None, 'query': '', 'page': 1}
            )['records']
        )

    def test_cancel_before_launch(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(ToolError) as caught:
            PlaywrightBrowser(cancel=event).fetch(search_path('AKRA'))
        self.assertEqual(caught.exception.code, 'CANCELLED')

    def test_cancel_running_worker(self):
        actual_popen = subprocess.Popen
        processes = []

        def launch(args, **kwargs):
            process = actual_popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
            processes.append(process)
            return process

        with tempfile.TemporaryDirectory() as directory:
            event = threading.Event()
            timer = threading.Timer(0.15, event.set)
            timer.start()
            try:
                with patch('sohib.stockbit.browser.subprocess.Popen', side_effect=launch):
                    with self.assertRaises(ToolError) as caught:
                        PlaywrightBrowser(profile=directory, cancel=event).fetch(
                            search_path('AKRA')
                        )
                self.assertEqual(caught.exception.code, 'CANCELLED')
                self.assertIsNotNone(processes[0].poll())
            finally:
                timer.join()

    def test_unsupported_url(self):
        for path in ('https://evil.invalid/search?keyword=AKRA', '/login', '//evil.invalid/search'):
            with self.assertRaises(ToolError):
                self.session.get(path)
        self.assertEqual(self.client.paths, [])

    def test_default_paths_follow_sohib_home(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'SOHIB_HOME': directory}):
                browser = PlaywrightBrowser()
                self.assertEqual(browser.profile, Path(directory).resolve() / 'chrome')
                self.assertEqual(
                    browser.connection_file, Path(directory).resolve() / 'browser.json'
                )
        self.assertTrue(PlaywrightBrowser('relative-profile').profile.is_absolute())
        with self.assertRaises(ValueError):
            PlaywrightBrowser(transport='navigate')


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_statistics_reload_produces_fresh_response(self):
        callbacks = []
        path = '/keystats/ratio/v1/SIDO?year_limit=10'
        response = SimpleNamespace(
            url='https://exodus.stockbit.com' + path,
            request=SimpleNamespace(method='GET'),
            status=200,
            body=AsyncMock(return_value=b'{"data":{}}'),
        )

        async def reload(**kwargs):
            callbacks[0](response)

        page = SimpleNamespace(
            url='https://stockbit.com/symbol/SIDO/keystats',
            reload=AsyncMock(side_effect=reload),
            wait_for_function=AsyncMock(),
            goto=AsyncMock(),
            on=lambda event, cb: callbacks.append(cb),
            remove_listener=lambda event, cb: callbacks.remove(cb),
        )
        with patch('sohib.stockbit.playwright_worker.check_page', new_callable=AsyncMock):
            for _ in range(2):
                self.assertEqual((await retrieve(page, path))['payload'], {'data': {}})
        self.assertEqual(page.reload.await_count, 2)
        page.goto.assert_not_awaited()
        self.assertEqual(callbacks, [])

    async def test_verification_and_login(self):
        for challenge, login, expected in (
            (True, False, 'AUTH_CHALLENGE'),
            (False, True, 'AUTH_REQUIRED'),
        ):
            page = SimpleNamespace(
                evaluate=AsyncMock(
                    return_value={
                        'challenge': challenge,
                        'login': login,
                        'url': 'https://stockbit.com/trusted-device/prompt',
                    }
                )
            )
            with self.assertRaises(ToolError) as caught:
                await check_page(page)
            self.assertEqual(caught.exception.code, expected)

    def test_matching_query_and_origin(self):
        for url, expected in (
            ('https://exodus.stockbit.com' + search_path('AKRA'), True),
            ('https://exodus.stockbit.com' + search_path('MAPI'), False),
            ('https://evil.invalid' + search_path('AKRA'), False),
        ):
            response = SimpleNamespace(url=url, request=SimpleNamespace(method='GET'))
            self.assertEqual(matches(response, search_path('AKRA')), expected)

    async def test_ui_response_and_listener_cleanup(self):
        callbacks = []
        response = SimpleNamespace(
            url='https://exodus.stockbit.com' + search_path('AKRA'),
            request=SimpleNamespace(method='GET'),
            status=200,
            body=AsyncMock(return_value=b'{"data":{"company":[]}}'),
        )

        async def fill(query):
            callbacks[0](response)

        locator = SimpleNamespace(count=AsyncMock(return_value=1), fill=fill)
        page = SimpleNamespace(
            on=lambda event, cb: callbacks.append(cb),
            remove_listener=lambda event, cb: callbacks.remove(cb),
            goto=AsyncMock(),
            evaluate=AsyncMock(
                return_value={
                    'challenge': False,
                    'login': False,
                    'url': 'https://stockbit.com/stream',
                }
            ),
            wait_for_function=AsyncMock(),
            get_by_placeholder=lambda *a, **k: locator,
        )
        result = await retrieve(page, search_path('AKRA'))
        self.assertEqual(result['payload'], {'data': {'company': []}})
        self.assertEqual(callbacks, [])
        locator.fill = AsyncMock()
        with self.assertRaises(TimeoutError):
            async with asyncio.timeout(0.05):
                await retrieve(page, search_path('AKRA'))
        self.assertEqual(callbacks, [])

    async def test_research_attaches_without_launching_or_closing_browser(self):
        from sohib.stockbit.playwright_worker import run

        page = SimpleNamespace(url='https://stockbit.com/stream')
        browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[page])], close=AsyncMock())
        chromium = SimpleNamespace(
            connect_over_cdp=AsyncMock(return_value=browser), launch_persistent_context=AsyncMock()
        )
        manager = AsyncMock()
        manager.__aenter__.return_value = SimpleNamespace(chromium=chromium)
        paths = [search_path('SIDO'), '/keystats/ratio/v1/SIDO?year_limit=10']
        args = SimpleNamespace(login=False, connection_file='private', path=paths, fetch=True)
        args.body = None
        with (
            patch('playwright.async_api.async_playwright', return_value=manager),
            patch(
                'sohib.stockbit.playwright_worker.connection_endpoint',
                return_value='http://127.0.0.1:9222',
            ),
            patch('sohib.stockbit.playwright_worker.check_page', new_callable=AsyncMock),
            patch(
                'sohib.stockbit.playwright_worker.fetch_json',
                new_callable=AsyncMock,
                side_effect=[{'data': 1}, {'data': 2}],
            ) as fetch_mock,
            patch(
                'sohib.stockbit.playwright_worker.retrieve', new_callable=AsyncMock
            ) as retrieve_mock,
        ):
            result = await run(args)
        self.assertEqual(
            [c.args for c in fetch_mock.await_args_list], [(page, p, None) for p in paths]
        )
        self.assertEqual(
            result,
            {
                'payload': {'data': 1},
                'payloads': [{'data': 1}, {'data': 2}],
                'source_url': 'https://stockbit.com/stream',
            },
        )
        retrieve_mock.assert_not_awaited()
        chromium.launch_persistent_context.assert_not_awaited()
        browser.close.assert_not_awaited()
        # Rollback path: without --fetch the worker still navigates and observes.
        args.fetch = False
        with (
            patch('playwright.async_api.async_playwright', return_value=manager),
            patch(
                'sohib.stockbit.playwright_worker.connection_endpoint',
                return_value='http://127.0.0.1:9222',
            ),
            patch('sohib.stockbit.playwright_worker.check_page', new_callable=AsyncMock),
            patch(
                'sohib.stockbit.playwright_worker.retrieve', new_callable=AsyncMock
            ) as retrieve_mock,
        ):
            await run(args)
        retrieve_mock.assert_awaited_once_with(page, search_path('SIDO'))

    async def test_missing_connection_never_launches(self):
        from sohib.stockbit.playwright_worker import run

        args = SimpleNamespace(
            login=False,
            connection_file='/nonexistent/connection.json',
            path=[search_path('SIDO')],
            fetch=True,
            body=None,
        )
        with patch('playwright.async_api.async_playwright') as factory:
            with self.assertRaises(ToolError):
                await run(args)
        factory.assert_not_called()


def response(status=200, body='{"data": {}}', content_type='application/json', **extra):
    return {
        'status': status,
        'contentType': content_type,
        'redirected': False,
        'host': 'exodus.stockbit.com',
        'body': body,
        **extra,
    }


class FetchTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_static_function_with_path_as_data(self):
        page = SimpleNamespace(evaluate=AsyncMock(return_value=response()))
        paths = [search_path('AKRA'), '/keystats/ratio/v1/SIDO?year_limit=10', '/screener/metric']
        for path in paths:
            self.assertEqual(await fetch_json(page, path), {'data': {}})
        scripts = {call.args[0] for call in page.evaluate.await_args_list}
        self.assertEqual(scripts, {FETCH_JSON})
        for call, path in zip(page.evaluate.await_args_list, paths, strict=True):
            base, sent, method, body, cookie, token_path = call.args[1]
            self.assertEqual(
                (base, sent, method, body), ('https://exodus.stockbit.com', path, 'GET', None)
            )
            self.assertEqual(
                (cookie, token_path), ('credentialStorage', ['state', 'access', 'token'])
            )
        self.assertNotIn(path, FETCH_JSON)
        self.assertNotIn('Bearer ', json.dumps(page.evaluate.await_args_list[0].args[1]))

    async def test_rejects_before_evaluate(self):
        page = SimpleNamespace(evaluate=AsyncMock())
        for path in (
            'https://exodus.stockbit.com/search?keyword=AKRA',
            '//evil.invalid/search?keyword=AKRA',
            '/search?keyword=AKRA#frag',
            '/keystats/ratio/v1/../MAPI?year_limit=10',
            '/portfolio',
            '/screener/templates',
            '/search?keyword=AKRA&extra=1',
        ):
            with self.assertRaises(ToolError) as caught:
                await fetch_json(page, path)
            self.assertEqual(caught.exception.code, 'UNSUPPORTED_INPUT')
        with self.assertRaises(ToolError):
            await fetch_json(page, '/search?keyword=AKRA', body={'save': '1'})
        page.evaluate.assert_not_awaited()

    async def test_network_failure_is_sanitized(self):
        from playwright.async_api import Error as BrowserError

        page = SimpleNamespace(
            evaluate=AsyncMock(side_effect=BrowserError('Failed to fetch secret'))
        )
        with self.assertRaises(ToolError) as caught:
            await fetch_json(page, '/screener/metric')
        self.assertEqual(caught.exception.code, 'UPSTREAM_ERROR')
        self.assertNotIn('secret', str(caught.exception))

    def test_status_mapping(self):
        cloudflare = json.dumps(
            {
                'status': 403,
                'error_code': 1010,
                'error_name': 'browser_signature_banned',
                'detail': 'private detail',
                'cloudflare_error': True,
            }
        )
        cases = [
            (response(401, '{"error_type":"x","message":"secret"}'), 'AUTH_EXPIRED', ''),
            (response(403, cloudflare), 'FORBIDDEN', 'Cloudflare 1010'),
            (response(403, '{"message":"secret"}'), 'FORBIDDEN', ''),
            (response(403, '<html>challenge secret</html>', 'text/html'), 'AUTH_CHALLENGE', ''),
            (response(429, '{}'), 'RATE_LIMITED', ''),
            (response(404, '{"message":"Perusahaan tidak ditemukan"}'), 'NO_DATA', ''),
            (response(400, '{"message":"secret"}'), 'NO_DATA', ''),
            (response(500, 'secret'), 'UPSTREAM_ERROR', ''),
            (response(200, '<html>login secret</html>', 'text/html'), 'AUTH_EXPIRED', ''),
            (response(200, None), 'SCHEMA_CHANGED', ''),
            (response(200, '[1, 2]'), 'SCHEMA_CHANGED', ''),
            (response(200, redirected=True, host='stockbit.com'), 'AUTH_EXPIRED', ''),
        ]
        for result, code, marker in cases:
            with self.subTest(status=result['status'], code=code):
                with self.assertRaises(ToolError) as caught:
                    classify(result)
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn('secret', str(caught.exception))
                self.assertIn(marker, str(caught.exception))
        self.assertEqual(classify(response(200, redirected=True)), {'data': {}})
        cloudflare_html = response(403, '<html>Just a moment</html>', 'text/html')
        self.assertEqual(classify(response(200, '{"a": 1}')), {'a': 1})
        with self.assertRaises(ToolError) as caught:
            classify(cloudflare_html)
        self.assertEqual(caught.exception.code, 'AUTH_CHALLENGE')


class RouteAllowlistTests(unittest.TestCase):
    def test_accepts_catalogued_routes(self):
        for path, page in [
            (search_path('Mitra Adiperkasa'), 'https://stockbit.com/stream'),
            ('/keystats/ratio/v1/BBCA?year_limit=10', 'https://stockbit.com/symbol/BBCA/keystats'),
            ('/screener/metric', 'https://stockbit.com/screener'),
            ('/emitten/MAPI/info?with_sub_industry=true', 'https://stockbit.com/symbol/MAPI'),
            (
                '/findata-view/company/financial?symbol=MAPI&data_type=1&report_type=2&statement_type=1',
                'https://stockbit.com/symbol/MAPI/financials',
            ),
            (
                '/fundachart?item=2891&companies=MAPI&timeframe=1y',
                'https://stockbit.com/symbol/MAPI/fundachart',
            ),
            ('/charts/MAPI/daily?timeframe=5y', 'https://stockbit.com/symbol/MAPI'),
            ('/analyst-ratings/MAPI/consensus', 'https://stockbit.com/symbol/MAPI/analysis'),
            ('/comparison/MAPI/ratios', 'https://stockbit.com/symbol/MAPI/comparison'),
            ('/corpaction/MAPI?limit=30', 'https://stockbit.com/symbol/MAPI'),
            ('/corpaction/dividend', 'https://stockbit.com/calendar/dividend'),
            (
                '/fundachart/metrics?metric_name=fundachart',
                'https://exodus.stockbit.com/fundachart/metrics?metric_name=fundachart',
            ),
        ]:
            self.assertEqual(validate_api_path(path), path)
            self.assertEqual(citation(path), page)

    def test_rejects_shape_scheme_host_and_params(self):
        for path in [
            'https://exodus.stockbit.com/screener/metric',
            '//exodus.stockbit.com/screener/metric',
            '/screener/metric#x',
            '/screener//metric',
            '/keystats/ratio/v1/..?year_limit=10',
            '/keystats/ratio/v1/MAPI?year_limit=99',
            '/keystats/ratio/v1/mapi?year_limit=10',
            '/keystats/ratio/v1/%4dAPI?year_limit=10',
            '/search?keyword=AKRA&page=1&type=all',
            '/search?keyword=AKRA&catalog_types=CATALOG_TYPE_PEOPLE',
            '/search?keyword=' + 'a' * 101,
            '/findata-view/company/financial?symbol=MAPI&data_type=2&report_type=1&statement_type=1',
            '/findata-view/company/financial?symbol=MAPI&report_type=1&statement_type=1',
            '/fundachart?item=2891&companies=MAPI&timeframe=all',
            '/charts/MAPI/daily?timeframe=bogus',
            '/corpaction/MAPI?limit=500',
            '/screener/universe',
            '/comparison/MAPI/templates',
            '/fundachart/templates',
            '/screener/templates',
            '/order-trade/broker/top',
            '/search?keyword=AKRA and secret',
            '',
            None,
        ]:
            with self.subTest(path=path):
                with self.assertRaises(ToolError) as caught:
                    validate_api_path(path)
                self.assertEqual(caught.exception.code, 'UNSUPPORTED_INPUT')
