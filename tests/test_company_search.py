import copy
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from sohib.stockbit.contracts import ToolError
from sohib.stockbit.provider import FIXTURES, StockbitTools
from sohib.stockbit.search import companies, search_path


class CompanySearchTests(unittest.TestCase):
    def setUp(self):
        self.tools = StockbitTools('fixture')
        self.payload = json.loads((FIXTURES / 'company-search.json').read_text())

    def test_symbol_excludes_warrants(self):
        result = self.tools.call('search_companies', {'query': ' akra '})
        self.assertEqual([r['symbol'] for r in result['records']], ['AKRA'])
        self.assertIsNone(result['pagination']['complete'])
        self.assertIsNone(result['pagination']['total'])
        self.assertEqual(result['pagination']['page'], 0)
        self.assertTrue(any('Excluded' in w for w in result['warnings']))

    def test_name_preserves_ambiguity_and_nontradeable(self):
        result = self.tools.call('search_companies', {'query': 'Mitra Adiperkasa'})
        self.assertGreater(len(result['records']), 1)
        self.assertEqual(result['records'][0]['symbol'], 'MAPI')
        self.assertTrue(any(not r['attributes']['is_tradeable'] for r in result['records']))

    def test_validation_auth_and_missing_capture(self):
        for args in (
            {'query': '  '},
            {'query': 'x' * 101},
            {},
            {'query': 'AKRA', 'url': 'x'},
            {'query': None},
        ):
            self.assertEqual(
                self.tools.call('search_companies', args)['error']['code'], 'UNSUPPORTED_INPUT'
            )
        self.assertEqual(
            StockbitTools().call('search_companies', {'query': 'AKRA'})['error']['code'],
            'AUTH_REQUIRED',
        )
        self.assertEqual(
            self.tools.call('search_companies', {'query': 'BBCA'})['error']['code'], 'NO_DATA'
        )

    def test_encoding(self):
        query = '企業 & Mitra/Adiperkasa?'
        params = parse_qs(urlsplit(search_path(query)).query)
        self.assertEqual(params['keyword'], [query])
        self.assertEqual(params['page'], ['0'])
        self.assertEqual(len(params['catalog_types']), 2)

    def test_private_groups_unknown_types_and_invalid_paths(self):
        payload = copy.deepcopy(self.payload['examples'][0]['response'])
        payload['data']['people'] = [{'secret': 'private-person'}]
        payload['data']['company'][0]['is_following'] = True
        records, _ = companies(payload)
        self.assertNotIn('private-person', json.dumps(records))
        self.assertNotIn('is_following', json.dumps(records))
        payload['data']['company'][0]['type'] = 'Unknown'
        self.assertEqual(companies(payload)[0], [])
        payload['data']['company'][0]['type'] = 'Saham'
        payload['data']['company'][0]['url'] = 'https://untrusted.example/symbol/AKRA'
        with self.assertRaises(ToolError):
            companies(payload)

    def test_empty_and_malformed_envelopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture = {'examples': [{'query': 'empty', 'response': {'data': {'company': []}}}]}
            path = Path(tmp) / 'company-search.json'
            path.write_text(json.dumps(capture))
            tools = StockbitTools('fixture', tmp)
            result = tools.call('search_companies', {'query': 'empty'})
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['records'], [])
            path.write_text('{}')
            self.assertEqual(
                tools.call('search_companies', {'query': 'empty'})['error']['code'],
                'SCHEMA_CHANGED',
            )

    def test_output_schema(self):
        from jsonschema import Draft202012Validator

        schema = json.loads((FIXTURES / 'output.schema.json').read_text())
        for query in ('AKRA', 'Mitra Adiperkasa', 'unknown'):
            Draft202012Validator(schema).validate(
                self.tools.call('search_companies', {'query': query})
            )
