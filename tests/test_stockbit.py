import copy
import json
import tempfile
import unittest
from pathlib import Path

from sohib.stockbit.contracts import Request, definitions
from sohib.stockbit.normalize import SchemaChanged, display_number, key_statistics
from sohib.stockbit.provider import FIXTURES, StockbitTools


class StockbitTests(unittest.TestCase):
    def setUp(self):
        self.tools = StockbitTools('fixture')

    def test_disabled_mode_and_invalid_mode(self):
        result = StockbitTools().call('get_key_statistics', {'symbol': 'MAPI'})
        self.assertEqual(result['error']['code'], 'AUTH_REQUIRED')
        self.assertEqual(result['records'], [])
        with self.assertRaises(ValueError):
            StockbitTools('invalid')

    def test_unknown_symbol_never_substitutes_fixture(self):
        result = self.tools.call('get_key_statistics', {'symbol': 'BBCA'})
        self.assertEqual(result['error']['code'], 'NO_DATA')
        self.assertEqual(result['records'], [])

    def test_symbol_not_limited_to_four_characters(self):
        self.assertEqual(
            Request.parse('get_key_statistics', {'symbol': 'abcde-r'}).symbol, 'ABCDE-R'
        )

    def test_invalid_arguments(self):
        for args in [
            None,
            {'symbol': '../MAPI'},
            {'symbol': 'MAPI', 'token': 'private'},
            {'symbol': 'MAPI', 'page': True},
            {'symbol': 'MAPI', 'page': 0},
            {'symbol': 'MAPI', 'query': 'a' * 101},
        ]:
            with self.subTest(args=args):
                result = self.tools.call('get_key_statistics', args)
                self.assertEqual(result['error']['code'], 'UNSUPPORTED_INPUT')
                self.assertNotIn('private', json.dumps(result))

    def test_namespace_semantics(self):
        result = self.tools.call('list_metrics', {'namespace': 'keystats'})
        self.assertEqual(result['error']['code'], 'UNSUPPORTED_INPUT')
        result = self.tools.call('list_metrics', {'namespace': 'financials', 'symbol': 'MAPI'})
        self.assertEqual(result['error']['code'], 'UNSUPPORTED_INPUT')

    def test_percentage_points_and_missing(self):
        self.assertEqual(display_number('10.85%')[:3], (10.85, 'percent', None))
        for value in [None, '', '-', '—', '&nbsp;']:
            self.assertEqual(display_number(value)[:3], (None, None, 'provider_missing'))
        self.assertEqual(display_number('0')[0], 0)

    def test_negative_billions_and_grouping(self):
        value, unit, missing, attrs = display_number('(56 B)')
        self.assertEqual(value, -56000000000)
        self.assertEqual(unit, 'base_units')
        self.assertIsNone(missing)
        self.assertEqual(attrs['scale'], 10**9)
        self.assertEqual(display_number('2,872.15')[0], 2872.15)
        self.assertEqual(display_number('1,2')[0], '1,2')
        self.assertEqual(display_number('03 Jul 26')[0], '03 Jul 26')

    def test_key_statistics_known_values(self):
        result = self.tools.call('get_key_statistics', {'symbol': 'mapi', 'query': '2891'})
        self.assertEqual(result['records'][0]['key'], 'keystats:2891')
        self.assertEqual(result['records'][0]['value'], 12.5)
        self.assertIsNone(result['records'][0]['currency'])
        self.assertIsNone(result['provenance']['data_as_of'])
        self.assertIsNone(result['records'][0]['attributes']['source_observed_at'])
        self.assertEqual(result['records'][0]['attributes']['fixture_kind'], 'synthetic')
        self.assertIn('SYNTHETIC FIXTURE', result['warnings'][0])

    def test_pagination_recovers_full_capture(self):
        rows, page = [], 1
        while page:
            result = self.tools.call('list_metrics', {'namespace': 'screener', 'page': page})
            self.assertLessEqual(len(result['records']), 20)
            self.assertLessEqual(len(json.dumps(result).encode()), 24000)
            rows.extend(result['records'])
            page = result['pagination']['next_page']
        self.assertEqual(len(rows), 26)
        self.assertEqual(len({r['key'] for r in rows}), 25)
        self.assertTrue(result['pagination']['complete'])
        self.assertTrue(all(r['value'] is None for r in rows))

    def test_catalog_keystats_has_no_values(self):
        result = self.tools.call(
            'list_metrics', {'namespace': 'keystats', 'symbol': 'MAPI', 'query': '2891'}
        )
        row = result['records'][0]
        self.assertIsNone(row['value'])
        self.assertNotIn('decimal_value', row['attributes'])

    def test_shape_change_returns_no_partial_records(self):
        payload = json.loads((FIXTURES / 'mapi-keystats.json').read_text())
        changed = copy.deepcopy(payload)
        del changed['data']['closure_fin_items_results'][1]['fin_name_results']
        with self.assertRaises(SchemaChanged):
            key_statistics(changed, 'MAPI')
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'mapi-keystats.json').write_text(json.dumps(changed))
            result = StockbitTools('fixture', tmp).call('get_key_statistics', {'symbol': 'MAPI'})
            self.assertEqual(result['error']['code'], 'SCHEMA_CHANGED')
            self.assertEqual(result['records'], [])

    def test_private_flags_never_escape(self):
        text = json.dumps(self.tools.call('get_key_statistics', {'symbol': 'MAPI'}))
        self.assertNotIn('hidden_graph_ico', text)
        self.assertNotIn('financial_year_parent', text)
        self.assertNotIn('is_new_update', text)

    def test_empty_and_out_of_range(self):
        for args in [
            {'symbol': 'MAPI', 'query': 'no such metric'},
            {'symbol': 'MAPI', 'page': 100},
        ]:
            result = self.tools.call('get_key_statistics', args)
            self.assertEqual(result['records'], [])
            self.assertIsNone(result['error'])
            self.assertIsNone(result['pagination']['next_page'])

    def test_model_schema_has_no_credentials_or_urls(self):
        for definition in definitions():
            schema = definition['parameters']
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(set(schema['required']), set(schema['properties']))
            self.assertFalse({'token', 'url', 'headers', 'cookie'} & set(schema['properties']))

    def test_read_only_registry(self):
        for name in ['screen_equities', 'place_order', 'login', 'save_screener']:
            self.assertEqual(self.tools.call(name, {})['error']['code'], 'UNSUPPORTED_INPUT')

    def test_output_schema(self):
        from jsonschema import Draft202012Validator, FormatChecker

        schema = json.loads((FIXTURES / 'output.schema.json').read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for tool, args in [
            ('list_metrics', {'namespace': 'screener'}),
            ('get_key_statistics', {'symbol': 'MAPI'}),
            ('get_key_statistics', {'symbol': 'BBCA'}),
            ('get_key_statistics', {'symbol': '../'}),
        ]:
            result = self.tools.call(tool, args)
            validator.validate(result)
            self.assertEqual(result['error'] is not None, result['status'] == 'error')
