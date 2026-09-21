import copy
import json
import os
import re
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from sohib.stockbit.api_routes import SCREEN_NAME, citation, screen_body, validate_screen_body
from sohib.stockbit.browser import BrowserSession
from sohib.stockbit.contracts import BASE_TOOLS, BROWSER_TOOLS, Request, ToolError, definitions
from sohib.stockbit.financials import financial_statements
from sohib.stockbit.normalize import SchemaChanged
from sohib.stockbit.provider import FIXTURES, StockbitTools
from sohib.tools.catalogue import OUTPUT_SCHEMA, catalogue
from sohib.tools.config import ToolSettings
from sohib.tools.service import ToolService

ROOT = Path(__file__).resolve().parents[1]
# Captured Stockbit responses are not distributed; see tests/evidence/README.md.
EVIDENCE = Path(os.environ.get('SOHIB_EVIDENCE_DIR') or ROOT / 'tests/evidence')
VALIDATOR = Draft202012Validator(OUTPUT_SCHEMA)
SECRETS = re.compile(
    r'Bearer |credentialStorage|eyJ[A-Za-z0-9_-]{20,}|set-cookie|authorization', re.I
)
PAGE = {'query': '', 'page': 1}


def evidence(name):
    path = EVIDENCE / name
    if not path.is_file():
        raise unittest.SkipTest(f'captured response {name} is not available in {EVIDENCE}')
    return json.loads(path.read_text())


class BrowserDouble:
    """Stands in for PlaywrightBrowser; payload may be one dict or a per-path list."""

    def __init__(self, payload):
        # A list is consumed in order across calls; a dict answers every path.
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
        if isinstance(self.payload, list):
            payloads, self.payload = self.payload[: len(paths)], self.payload[len(paths) :]
        else:
            payloads = [self.payload] * len(paths)
        return {'payload': payloads[0], 'payloads': payloads, 'source_url': citation(paths[0])}


class ResearchToolTests(unittest.TestCase):
    def call(self, name, args, *payloads, error=None):
        client = BrowserDouble(list(payloads) if len(payloads) > 1 else payloads[0])
        client.error = error
        tools = StockbitTools('browser', session=BrowserSession(client))
        result = tools.call(name, args)
        VALIDATOR.validate(result)
        blob = json.dumps(result)
        self.assertLessEqual(len(blob.encode()), 24000)
        self.assertIsNone(SECRETS.search(blob), 'secret-like text reached the envelope')
        self.assertEqual(result['error'] is not None, result['status'] == 'error')
        return result, client

    def test_company_summary(self):
        payload = evidence('response-001.json')
        payload['data']['followers'] = 42
        payload['data']['is_following'] = True
        result, client = self.call('get_company_summary', {'symbol': 'mapi'}, payload)
        self.assertEqual(client.paths, ['/emitten/MAPI/info?with_sub_industry=true'])
        keys = [r['key'] for r in result['records']]
        self.assertEqual(keys[:2], ['company:profile', 'company:price'])
        price = result['records'][1]
        self.assertEqual((price['value'], price['display_value']), (1380.0, '1,380'))
        self.assertEqual(price['timestamp'], '2026-09-16T08:00:11+07:00')
        self.assertEqual(result['provenance']['data_as_of'], price['timestamp'])
        self.assertIsNone(price['currency'])
        self.assertEqual(
            result['records'][0]['attributes']['sub_industry'], 'Ritel Pakaian & Tekstil'
        )
        self.assertEqual(price['attributes']['source_url'], 'https://stockbit.com/symbol/MAPI')
        blob = json.dumps(result)
        for private in ('followers', 'is_following', 'sentiment', 'tabs'):
            self.assertNotIn(private, blob)
        payload['data']['symbol'] = 'OTHER'
        self.assertEqual(
            self.call('get_company_summary', {'symbol': 'MAPI'}, payload)[0]['error']['code'],
            'SCHEMA_CHANGED',
        )
        result, _ = self.call('get_company_summary', {'symbol': 'ZZZZ9'}, {}, error='NO_DATA')
        self.assertEqual(result['error']['code'], 'NO_DATA')
        self.assertEqual(
            result['provenance']['endpoint_template'],
            '/emitten/{symbol}/info?with_sub_industry=true',
        )

    def test_financial_statements(self):
        args = {
            'symbol': 'MAPI',
            'report_type': 'income_statement',
            'period_mode': 'quarterly',
            'periods': 2,
            'query': 'total revenue',
            'page': 1,
        }
        result, client = self.call('get_financial_statements', args, evidence('response-007.json'))
        self.assertEqual(
            client.paths,
            [
                '/findata-view/company/financial?symbol=MAPI&data_type=1&report_type=1&statement_type=1'
            ],
        )
        first = result['records'][0]
        self.assertEqual(first['key'], 'financials:income_statement:account:1:Q226')
        self.assertEqual((first['period'], first['value']), ('Q2 2026', 11864170000000.0))
        self.assertEqual((first['unit'], first['currency']), ('base_units', 'IDR'))
        self.assertEqual(first['attributes']['period_mode'], 'quarterly')
        self.assertEqual(result['records'][1]['period'], 'Q1 2026')
        self.assertEqual({r['label'] for r in result['records']}, {'Total Revenue'})
        args.update(query='', periods=4, page=1)
        result, _ = self.call('get_financial_statements', args, evidence('response-007.json'))
        self.assertEqual(result['pagination']['total'], 188)
        self.assertEqual(result['pagination']['next_page'], 2)
        missing = [r for r in result['records'] if r['value'] is None]
        self.assertTrue(all(r['missing_reason'] == 'provider_missing' for r in missing))
        for args_bad in (
            {**args, 'report_type': 'balance_sheet', 'period_mode': 'ttm'},
            {**args, 'periods': 0},
            {**args, 'period_mode': 'monthly'},
            {**args, 'token': 'x'},
        ):
            self.assertEqual(
                self.call('get_financial_statements', args_bad, {})[0]['error']['code'],
                'UNSUPPORTED_INPUT',
            )
        broken = evidence('response-010.json')
        broken['data']['data_tables']['accounts'] = [{'unexpected': True}]
        args.update(report_type='cash_flow', period_mode='annual')
        self.assertEqual(
            self.call('get_financial_statements', args, broken)[0]['error']['code'],
            'SCHEMA_CHANGED',
        )

    def test_financial_html_parser(self):
        html = """<div><input type="hidden" name="selected_currency" value="usd">
        <table class="fin-table"><thead><tr><th class="info">In Million</th>
        <th class="periods-list" data-label="Q125">Q1 2025</th>
        <th class="periods-list" data-label="Q225">Q2 2025</th></tr></thead><tbody>
        <tr class="dtr r_head row1" data-left="1" data-right="4"><td><span class="acc-name"
        data-lang-1-full="Total Revenue" data-lang-0-full="Total Pendapatan">x</span>
        <i class="acc-chart" data-acc-number="1"></i></td>
        <td class="rowval" data-raw="10.5" data-value-idr="10.5" data-value-usd="1" data-percentage="oops">10.5</td>
        <td class="rowval" data-raw="-" data-value-idr="0" data-value-usd="0" data-percentage="0">-</td></tr>
        <tr class="dtr other row4 hides" data-left="4" data-right="4"><td>&nbsp&nbspOthers<em class="acc-chart"
        data-acc-number="4"></em></td><td data-raw="n/a">n/a</td><td data-raw="2">2</td></tr>
        <tr class='4 dtr total row4 bold hides' data-left='4' data-right='4'><td class=''>Total <span class='acc-name'
        data-lang-1-full=' Revenue' data-lang-0-full=' Pendapatan'>x</span><i class='acc-chart' data-acc-number='4'></i></td>
        <td data-raw="12.5">12.5</td><td data-raw="2">2</td></tr></tbody></table>
        <table class="fin-table ratio-table_keyratio"><thead><tr><th class="info">x</th>
        <th class="periods-list" data-label="Q125">Q1 2025</th><th class="periods-list" data-label="Q225">Q2 2025</th></tr></thead>
        <tbody><tr class="dtr"><td><span class="acc-name" data-lang-1-full="Margin">Margin</span>
        <em class="acc-chart" data-acc-number="900"></em></td><td class="row-ratio-val" data-raw="3.15">3.15%</td>
        <td class="row-ratio-val" data-raw="4">4.00%</td></tr></tbody></table></div>"""
        payload = {
            'data': {
                'html_report': html,
                'default_currency': 'IDR',
                'data_tables': {'periods': [], 'accounts': []},
            }
        }
        rows, notes = financial_statements(payload, 'TEST', '1', 2)
        by_key = {row['key']: row for row in rows}
        head = by_key['financials:income_statement:account:1:Q125']
        self.assertEqual(
            (head['value'], head['currency'], head['unit']), (10.5, 'USD', 'base_units')
        )
        self.assertIsNone(head['attributes']['common_size_percent'])
        self.assertEqual(head['attributes']['name_id'], 'Total Pendapatan')
        empty = by_key['financials:income_statement:account:1:Q225']
        self.assertEqual(
            (empty['value'], empty['missing_reason'], empty['display_value']),
            (None, 'provider_missing', '-'),
        )
        self.assertIsNone(empty['attributes']['value_idr'])
        others = by_key['financials:income_statement:others:4:Q125']
        self.assertEqual(
            (others['label'], others['missing_reason'], others['display_value']),
            ('Others', 'provider_unparsed', 'n/a'),
        )
        self.assertEqual(others['attributes']['parent_account'], '1')
        total = by_key['financials:income_statement:total:4:Q125']
        self.assertEqual((total['label'], total['value']), ('Total Revenue', 12.5))
        self.assertTrue(total['attributes']['collapsed_by_default'])
        ratio = by_key['financials:income_statement:formula:900:Q125']
        self.assertEqual(
            (ratio['value'], ratio['unit'], ratio['currency'], ratio['display_value']),
            (3.15, 'percent', None, '3.15%'),
        )
        self.assertEqual([r['period'] for r in rows[:2]], ['Q2 2025', 'Q1 2025'])
        self.assertTrue(any('In Million' in note for note in notes))
        payload['data']['html_report'] = ''
        with self.assertRaises(SchemaChanged):
            financial_statements(payload, 'TEST', '1', 2)

    def test_list_metrics_new_namespaces(self):
        result, client = self.call(
            'list_metrics',
            {'namespace': 'fundachart', 'symbol': None, **PAGE},
            evidence('response-019.json'),
        )
        self.assertEqual(client.paths, ['/fundachart/metrics?metric_name=fundachart'])
        self.assertEqual(result['pagination']['total'], 365)
        self.assertTrue(all(r['key'].startswith('fundachart:') for r in result['records']))
        self.assertTrue(all(r['missing_reason'] == 'metadata_only' for r in result['records']))
        result, client = self.call(
            'list_metrics',
            {'namespace': 'comparison', 'symbol': None, 'query': 'return on', 'page': 1},
            evidence('response-039.json'),
        )
        self.assertEqual(client.paths, ['/comparison/metrics'])
        self.assertTrue(result['records'])
        self.assertTrue(all('Return' in r['label'] for r in result['records']))
        result, client = self.call(
            'list_metrics',
            {'namespace': 'financials', 'symbol': 'MAPI', 'query': 'revenue', 'page': 1},
            evidence('response-007.json'),
            evidence('response-008.json'),
            evidence('response-009.json'),
        )
        self.assertEqual(len(client.paths), 3)
        self.assertEqual(client.paths[0].split('report_type=')[1][0], '1')
        self.assertTrue(all(r['key'].startswith('financials:') for r in result['records']))
        self.assertTrue(all(r['value'] is None for r in result['records']))
        self.assertEqual(
            result['records'][0]['attributes']['source_url'],
            'https://stockbit.com/symbol/MAPI/financials',
        )
        for args in (
            {'namespace': 'fundachart', 'symbol': 'MAPI', **PAGE},
            {'namespace': 'financials', 'symbol': None, **PAGE},
        ):
            self.assertEqual(
                self.call('list_metrics', args, {})[0]['error']['code'], 'UNSUPPORTED_INPUT'
            )

    def test_fundamental_history(self):
        args = {'symbol': 'MAPI', 'metric_id': 2891, 'timeframe': '1y', 'page': 1}
        result, client = self.call('get_fundamental_history', args, evidence('response-025.json'))
        self.assertEqual(client.paths, ['/fundachart?item=2891&companies=MAPI&timeframe=1y'])
        self.assertEqual(len(result['records']), 40)
        self.assertEqual(
            (result['pagination']['total'], result['pagination']['next_page']), (240, 2)
        )
        first = result['records'][0]
        self.assertEqual(
            (first['label'], first['timestamp'], first['value']),
            ('Current PE Ratio (TTM)', '2026-09-17', 9.22),
        )
        self.assertGreater(first['timestamp'], result['records'][1]['timestamp'])
        result, _ = self.call(
            'get_fundamental_history', {**args, 'metric_id': 1}, evidence('response-025.json')
        )
        self.assertEqual(result['records'], [])
        self.assertTrue(any('no series' in w for w in result['warnings']))
        self.assertEqual(
            self.call('get_fundamental_history', {**args, 'timeframe': 'all'}, {})[0]['error'][
                'code'
            ],
            'UNSUPPORTED_INPUT',
        )

    def test_price_series(self):
        args = {'symbol': 'MAPI', 'timeframe': '5y', 'page': 1}
        result, client = self.call('get_price_series', args, evidence('response-026.json'))
        self.assertEqual(client.paths, ['/charts/MAPI/daily?timeframe=5y'])
        summary, newest = result['records'][:2]
        self.assertEqual(
            (summary['key'], summary['value'], summary['unit']),
            ('price:5y:summary', 79.22, 'percent'),
        )
        self.assertEqual(summary['attributes']['points'], 1199)
        self.assertEqual((newest['timestamp'], newest['value']), ('2026-09-16', 1380.0))
        self.assertEqual(result['pagination']['total'], 1200)
        blob = json.dumps(result)
        for field in ('"open"', '"high"', '"low"', '"volume"'):
            self.assertNotIn(field, blob)
        self.assertTrue(any('not OHLCV' in w for w in result['warnings']))
        candles = evidence('response-026.json')
        candles['data']['chart_type'] = 'PRICE_CHART_TYPE_CANDLE'
        self.assertEqual(
            self.call('get_price_series', args, candles)[0]['error']['code'], 'SCHEMA_CHANGED'
        )
        intraday = evidence('response-002.json')
        result, _ = self.call('get_price_series', {**args, 'timeframe': 'today'}, intraday)
        self.assertIsNone(result['records'][1]['attributes']['source_date_ms'])
        self.assertIn(' ', result['records'][1]['timestamp'])

    def test_price_performance(self):
        result, client = self.call(
            'get_price_performance', {'symbol': 'MAPI'}, evidence('response-003.json')
        )
        self.assertEqual(client.paths, ['/company-price-feed/price-performance/MAPI'])
        self.assertEqual(len(result['records']), 10)
        day = result['records'][0]
        self.assertEqual(
            (day['period'], day['unit'], day['display_value']), ('1D', 'percent', '(-0.36%)')
        )
        self.assertAlmostEqual(day['value'], -0.36101082)
        self.assertEqual(
            (day['attributes']['high'], day['attributes']['low_display']), (1410, '1,350')
        )

    def test_analyst_consensus(self):
        ratings, consensus = evidence('response-035.json'), evidence('response-036.json')
        ratings['data']['price_target']['best_low_target'] = 0
        result, client = self.call(
            'get_analyst_consensus', {'symbol': 'MAPI', **PAGE}, ratings, consensus
        )
        self.assertEqual(client.paths, ['/analyst-ratings/MAPI', '/analyst-ratings/MAPI/consensus'])
        self.assertEqual(result['pagination']['total'], 17)
        by_key = {r['key']: r for r in result['records']}
        self.assertEqual(by_key['analyst:recommendation']['value'], 'Buy')
        self.assertEqual(by_key['analyst:recommendation']['attributes']['buy'], 18)
        self.assertEqual(by_key['analyst:best_target']['value'], 1666)
        self.assertEqual(
            (
                by_key['analyst:best_low_target']['value'],
                by_key['analyst:best_low_target']['missing_reason'],
            ),
            (None, 'provider_missing'),
        )
        revenue = by_key['analyst:consensus:revenue:2026']
        self.assertEqual(
            (revenue['value'], revenue['unit'], revenue['period']), (47762e9, 'base_units', '2026')
        )
        self.assertTrue(revenue['attributes']['is_estimate'])
        self.assertIsNone(revenue['currency'])
        self.assertEqual(
            result['records'][0]['attributes']['source_url'],
            'https://stockbit.com/symbol/MAPI/analysis',
        )

    def test_peer_comparison(self):
        payloads = (
            evidence('response-042.json'),
            evidence('response-041.json'),
            evidence('response-039.json'),
        )
        result, client = self.call(
            'get_peer_comparison',
            {'symbol': 'MAPI', 'query': 'pe ratio (ttm)', 'page': 1},
            *payloads,
        )
        self.assertEqual(
            client.paths,
            ['/comparison/MAPI/ratios', '/comparison/MAPI/industries', '/comparison/metrics'],
        )
        scopes = {(r['attributes']['scope'], r['symbol'], r['value']) for r in result['records']}
        self.assertIn(('company', 'MAPI', 9.22), scopes)
        self.assertIn(('industry', None, 10.29), scopes)
        self.assertEqual({s[0] for s in scopes}, {'company', 'industry', 'sector'})
        self.assertTrue(
            all(r['label'].startswith('Current PE Ratio (TTM)') for r in result['records'])
        )
        result, _ = self.call(
            'get_peer_comparison', {'symbol': 'MAPI', 'query': 'peer', 'page': 1}, *payloads
        )
        self.assertEqual([r['symbol'] for r in result['records']], ['MAPI', 'ERAA', 'IMAS', 'TURI'])
        result, _ = self.call('get_peer_comparison', {'symbol': 'MAPI', **PAGE}, *payloads)
        self.assertEqual(result['pagination']['total'], 202)
        unknown = [
            r for r in result['records'] if r['attributes']['label_source'] == 'unknown_metric'
        ]
        self.assertEqual(unknown, [])
        wrong = copy.deepcopy(payloads[0])
        wrong['data']['symbol'] = 'ERAA'
        self.assertEqual(
            self.call('get_peer_comparison', {'symbol': 'MAPI', **PAGE}, wrong, *payloads[1:])[0][
                'error'
            ]['code'],
            'SCHEMA_CHANGED',
        )

    def test_corporate_actions(self):
        actions, conversions = evidence('response-014.json'), evidence('response-013.json')
        actions['data'].append(
            {
                'action_type': 'mystery',
                'action_info': {
                    'mystery': {
                        'mystery_id': '9',
                        'company_symbol': 'MAPI',
                        'mystery_datahash': 'h',
                        'mystery_date': '2026-01-01',
                    }
                },
            }
        )
        result, client = self.call(
            'get_corporate_actions', {'symbol': 'MAPI', **PAGE}, actions, conversions
        )
        self.assertEqual(
            client.paths,
            ['/corpaction/MAPI?limit=30', '/corpaction/MAPI/stock_conversion?page=1&limit=50'],
        )
        self.assertEqual(result['pagination']['total'], 21)
        self.assertIsNone(result['pagination']['complete'])
        dividend = result['records'][0]
        self.assertEqual(
            (dividend['label'], dividend['value'], dividend['currency']),
            ('Cash dividend Rp 10', 10.0, 'IDR'),
        )
        self.assertEqual(
            [
                dividend['attributes'][k]
                for k in ('cum_date', 'ex_date', 'record_date', 'payment_date')
            ],
            ['2026-07-02', '2026-07-03', '2026-07-06', '2026-07-24'],
        )
        self.assertIsNone(dividend['timestamp'])
        blob = json.dumps(result)
        for private in ('datahash', 'dividend_lock', 'iqp', 'icon_url'):
            self.assertNotIn(private, blob)
        self.assertTrue(any('Unverified event type "mystery"' in w for w in result['warnings']))
        result, _ = self.call(
            'get_corporate_actions',
            {'symbol': 'MAPI', 'query': 'split', 'page': 1},
            actions,
            conversions,
        )
        self.assertEqual(result['records'][0]['label'], 'Stock split 1:10')
        self.assertEqual(result['records'][0]['value'], 10.0)
        actions['data'][0]['action_info']['dividend']['company_symbol'] = 'OTHER'
        self.assertEqual(
            self.call('get_corporate_actions', {'symbol': 'MAPI', **PAGE}, actions, conversions)[0][
                'error'
            ]['code'],
            'SCHEMA_CHANGED',
        )

    def test_dividend_calendar(self):
        result, client = self.call(
            'get_dividend_calendar',
            PAGE,
            evidence('response-049.json'),
            evidence('response-047.json'),
        )
        self.assertEqual(client.paths, ['/corpaction/dividend', '/corpaction'])
        self.assertEqual(result['pagination']['total'], 472)
        self.assertEqual(result['provenance']['data_as_of'], '2026-09-17')
        first = result['records'][0]
        self.assertEqual(
            (first['symbol'], first['value'], first['attributes']['ex_date']),
            ('PSAB', 30.0, '2026-09-16'),
        )
        self.assertEqual(
            first['attributes']['source_url'], 'https://stockbit.com/calendar/dividend'
        )
        result, _ = self.call(
            'get_dividend_calendar',
            {'query': 'bbca', 'page': 1},
            evidence('response-049.json'),
            evidence('response-047.json'),
        )
        self.assertTrue(result['records'])
        self.assertTrue(all(r['symbol'] == 'BBCA' for r in result['records']))
        result, _ = self.call(
            'get_dividend_calendar',
            {'query': 'public expose', 'page': 1},
            evidence('response-049.json'),
            evidence('response-047.json'),
        )
        self.assertEqual([r['symbol'] for r in result['records']], ['AIMS', 'HEXA'])

    def test_screen_equities(self):
        taxonomy = json.loads((FIXTURES / 'screener-metrics.json').read_text())
        screen = evidence('create-screener-response.json')
        args = {
            'rules': [
                {'metric_id': 2891, 'operator': '>', 'value': 0},
                {'metric_id': 12464, 'operator': '>', 'value': 500000},
            ],
            'page': 1,
            'sort_direction': 'ascending',
        }
        result, client = self.call('screen_equities', args, taxonomy, screen)
        self.assertEqual(client.paths, ['/screener/metric', '/screener/templates'])
        body = client.bodies[1]
        self.assertEqual(
            {
                k: body[k]
                for k in ('save', 'screenerid', 'type', 'ordertype', 'ordercol', 'page', 'name')
            },
            {
                'save': '0',
                'screenerid': '0',
                'type': 'TEMPLATE_TYPE_CUSTOM',
                'ordertype': 'asc',
                'ordercol': 2,
                'page': 1,
                'name': SCREEN_NAME,
            },
        )
        self.assertEqual(json.loads(body['universe']), {'scope': 'IHSG', 'scopeID': '', 'name': ''})
        filters = json.loads(body['filters'])
        self.assertEqual(
            [f['item1name'] for f in filters], ['Current PE Ratio (TTM)', 'Volume MA 20']
        )
        self.assertEqual([f['item2'] for f in filters], ['0', '500000'])
        self.assertEqual(body['sequence'], '2891,12464')
        self.assertEqual(len(result['records']), 25)
        self.assertEqual(
            (
                result['pagination']['page'],
                result['pagination']['total'],
                result['pagination']['next_page'],
            ),
            (1, 440, 2),
        )
        first = result['records'][0]
        self.assertEqual((first['symbol'], first['label']), ('VIVA', 'Visi Media Asia Tbk.'))
        self.assertEqual(first['attributes']['metrics'][0]['value'], 0.5)
        self.assertNotIn('icon_url', json.dumps(result))
        self.assertEqual(first['attributes']['source_url'], 'https://stockbit.com/screener')
        result, client = self.call(
            'screen_equities',
            {**args, 'rules': [{'metric_id': 1, 'operator': '>', 'value': 0}]},
            taxonomy,
            screen,
        )
        self.assertEqual(result['error']['code'], 'UNSUPPORTED_INPUT')
        self.assertEqual(client.paths, ['/screener/metric'])
        for bad in (
            {**args, 'rules': []},
            {**args, 'rules': [{'metric_id': 2891, 'operator': '!=', 'value': 0}]},
            {**args, 'rules': [{'metric_id': 2891, 'operator': '>', 'value': float('nan')}]},
            {**args, 'rules': [{'metric_id': 2891, 'operator': '>', 'value': 0, 'save': '1'}]},
            {**args, 'sort_direction': 'asc'},
            {**args, 'page': 0},
        ):
            self.assertEqual(
                self.call('screen_equities', bad, taxonomy, screen)[0]['error']['code'],
                'UNSUPPORTED_INPUT',
            )

    def test_screen_body_constants_are_enforced(self):
        rules = [{'metric_id': 2891, 'operator': '>', 'value': '0.5', 'label': 'PE'}]
        body = screen_body(rules, 3, 'desc')
        self.assertEqual(validate_screen_body(body), body)
        for mutate in (
            lambda b: b.update(save='1'),
            lambda b: b.update(screenerid='12'),
            lambda b: b.update(type='TEMPLATE_TYPE_GURU'),
            lambda b: b.update(universe='{"scope":"LQ45","scopeID":"","name":""}'),
            lambda b: b.update(favourite='1'),
            lambda b: b.update(ordercol=3),
            lambda b: b.update(sequence='1'),
            lambda b: b.update(
                filters=json.dumps(
                    [
                        {
                            'type': 'compare',
                            'item1': 2891,
                            'item1name': 'PE',
                            'operator': '<',
                            'item2': '12634',
                            'multiplier': '1',
                        }
                    ]
                )
            ),
            lambda b: b.update(
                filters=json.dumps(
                    [
                        {
                            'type': 'basic',
                            'item1': 2891,
                            'item1name': 'PE',
                            'operator': '>',
                            'item2': '1e5',
                            'multiplier': '',
                        }
                    ]
                )
            ),
            lambda b: b.update(
                filters=json.dumps(
                    [
                        {
                            'type': 'basic',
                            'item1': 2891,
                            'item1name': 'PE',
                            'operator': '>',
                            'item2': '1',
                            'multiplier': '',
                        }
                    ]
                    * 21
                )
            ),
        ):
            broken = copy.deepcopy(body)
            mutate(broken)
            with self.assertRaises(ToolError) as caught:
                validate_screen_body(broken)
            self.assertEqual(caught.exception.code, 'UNSUPPORTED_INPUT')
        with self.assertRaises(ToolError):
            BrowserSession(BrowserDouble({})).post('/screener/templates', {'save': '0'})
        with self.assertRaises(ToolError):
            BrowserSession(BrowserDouble({})).post('/screener/metric', body)

    def test_errors_keep_endpoint_and_stay_secret_free(self):
        for name, args in (
            ('get_company_summary', {'symbol': 'MAPI'}),
            ('get_dividend_calendar', PAGE),
            (
                'get_fundamental_history',
                {'symbol': 'MAPI', 'metric_id': 2891, 'timeframe': '1y', 'page': 1},
            ),
        ):
            for code in ('AUTH_EXPIRED', 'AUTH_CHALLENGE', 'FORBIDDEN', 'RATE_LIMITED', 'TIMEOUT'):
                result, _ = self.call(name, args, {}, error=code)
                self.assertEqual(result['error']['code'], code)
                self.assertTrue(result['provenance']['endpoint_template'])
                self.assertEqual(result['records'], [])

    def test_get_many_length_mismatch(self):
        client = BrowserDouble([{'a': 1}])
        client.payload = [{'a': 1}]
        with self.assertRaises(ToolError) as caught:
            BrowserSession(client).get_many(
                ['/analyst-ratings/MAPI', '/analyst-ratings/MAPI/consensus']
            )
        self.assertEqual(caught.exception.code, 'SCHEMA_CHANGED')


class RegistrationTests(unittest.TestCase):
    def test_browser_definitions_are_strict_and_credential_free(self):
        browser = definitions('browser')
        self.assertEqual({d['name'] for d in browser}, set(BROWSER_TOOLS))
        self.assertEqual({d['name'] for d in definitions('fixture')}, set(BASE_TOOLS))
        for definition in browser:
            schema = definition['parameters']
            self.assertTrue(definition['strict'])
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(set(schema['required']), set(schema['properties']))
            self.assertFalse(
                {'token', 'url', 'headers', 'cookie', 'path'} & set(schema['properties'])
            )
            self.assertIn('source_url', definition['description'])
        namespaces = next(d for d in browser if d['name'] == 'list_metrics')['parameters'][
            'properties'
        ]['namespace']['enum']
        self.assertEqual(
            set(namespaces), {'screener', 'keystats', 'financials', 'fundachart', 'comparison'}
        )

    def test_catalogue_registers_new_tools_only_in_browser_mode(self):
        browser = catalogue('browser')
        self.assertEqual({t['name'] for t in browser['tools']}, set(BROWSER_TOOLS))
        for tool in browser['tools']:
            self.assertIn('Mode: browser', tool['description'])
            self.assertTrue(tool['annotations']['readOnlyHint'])
            Draft202012Validator.check_schema(tool['inputSchema'])
        fixture = catalogue('fixture')
        self.assertEqual({t['name'] for t in fixture['tools']}, set(BASE_TOOLS))
        enum = next(t for t in fixture['tools'] if t['name'] == 'list_metrics')['inputSchema'][
            'properties'
        ]['namespace']['enum']
        self.assertEqual(enum, ['keystats', 'screener'])
        service = ToolService(
            ToolSettings('browser', '/nonexistent/connection.json', '/tmp/sohib-test-profile')
        )
        self.assertEqual(set(service.inputs), set(BROWSER_TOOLS))
        self.assertEqual(
            service.call(
                'screen_equities',
                {
                    'rules': [{'metric_id': 2891, 'operator': '>', 'value': 0}],
                    'page': 1,
                    'sort_direction': 'ascending',
                    'save': '1',
                },
            )['error']['code'],
            'UNSUPPORTED_INPUT',
        )

    def test_new_tools_stay_unavailable_outside_browser_mode(self):
        for mode in ('disabled', 'fixture'):
            tools = StockbitTools(mode)
            for name in set(BROWSER_TOOLS) - set(BASE_TOOLS):
                self.assertEqual(
                    tools.call(name, {'symbol': 'MAPI'})['error']['code'], 'UNSUPPORTED_INPUT'
                )

    def test_request_parsing(self):
        request = Request.parse(
            'screen_equities',
            {
                'rules': [{'metric_id': 2891, 'operator': '>=', 'value': 0.25}],
                'page': 2,
                'sort_direction': 'descending',
            },
        )
        self.assertEqual(request.rules, ({'metric_id': 2891, 'operator': '>=', 'value': '0.25'},))
        self.assertEqual(
            Request.parse(
                'get_financial_statements',
                {'symbol': 'mapi', 'report_type': 'cash_flow', 'period_mode': 'annual'},
            ).periods,
            4,
        )
        self.assertEqual(Request.parse('get_dividend_calendar', {}).page, 1)
        for name, args in (
            ('get_company_summary', {}),
            ('get_company_summary', {'symbol': 'MAPI', 'query': ''}),
            ('get_price_series', {'symbol': 'MAPI', 'timeframe': 'all', 'page': 1}),
            (
                'get_fundamental_history',
                {'symbol': 'MAPI', 'metric_id': '2891', 'timeframe': '1y', 'page': 1},
            ),
            (
                'get_fundamental_history',
                {'symbol': 'MAPI', 'metric_id': 2891, 'timeframe': '1y', 'page': True},
            ),
            ('get_peer_comparison', {'symbol': '../MAPI', 'query': '', 'page': 1}),
            (
                'screen_equities',
                {
                    'rules': [{'metric_id': 0, 'operator': '>', 'value': 1}],
                    'page': 1,
                    'sort_direction': 'ascending',
                },
            ),
            (
                'screen_equities',
                {
                    'rules': [{'metric_id': 1, 'operator': '>', 'value': True}],
                    'page': 1,
                    'sort_direction': 'ascending',
                },
            ),
            (
                'screen_equities',
                {
                    'rules': [{'metric_id': 1, 'operator': '>', 'value': 1e19}],
                    'page': 1,
                    'sort_direction': 'ascending',
                },
            ),
            ('unknown_tool', {}),
        ):
            with self.subTest(name=name, args=args):
                with self.assertRaises(ToolError) as caught:
                    Request.parse(name, args)
                self.assertEqual(caught.exception.code, 'UNSUPPORTED_INPUT')
