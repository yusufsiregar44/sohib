import json
from copy import deepcopy

from ..stockbit.contracts import definitions
from ..stockbit.provider import FIXTURES

VERSION = '1.1.0'
OUTPUT_SCHEMA = json.loads((FIXTURES / 'output.schema.json').read_text())
DESCRIPTIONS = {
    'search_companies': 'Search IDX equities by symbol or company name. Excludes warrants; '
    'preserves multiple candidates. Confirm the company before fetching statistics.',
    'get_key_statistics': 'Read key statistics for a confirmed symbol, filtered by label/ID. '
    'Pages contain up to 20 records. Preserve missing periods, currency and source dates.',
    'list_metrics': 'Discover metric metadata without numeric values. keystats and financials '
    'require a symbol; screener, fundachart and comparison are market-wide (symbol=null). '
    'IDs are namespaced per service; never merge them.',
    'get_company_summary': 'Company identity, sector classification and the last provider quote '
    'for a confirmed symbol. Quote timestamp is provider time, not a filing date.',
    'get_financial_statements': 'Financial statement cells (account x period) for a confirmed '
    'symbol: income_statement, balance_sheet or cash_flow; quarterly, annual or ttm. Values are '
    'raw base-currency units; choose periods (1-12) and filter accounts with query.',
    'get_fundamental_history': 'Historical FundaChart series for one metric_id (discover with '
    'list_metrics namespace=fundachart). Newest first, 40 points per page.',
    'get_price_series': 'Verified LINE price points only, newest first, 40 per page, preceded '
    'by a period summary. Not OHLCV; timezone and adjustment unverified.',
    'get_price_performance': 'Price change with period high and low across provider windows '
    '(1D to 10Y) for a confirmed symbol.',
    'get_analyst_consensus': 'Analyst recommendation counts, price targets and consensus '
    'estimates by year; estimates are flagged and currency is not stated.',
    'get_peer_comparison': 'Comparison ratios for the symbol next to industry and sector '
    'aggregates plus peer symbols; labels come from the comparison taxonomy.',
    'get_corporate_actions': 'Dividends, shareholder meetings, splits and tender offers with '
    'cum, ex, record and payment dates kept separate. Bounded history; completeness unknown.',
    'get_dividend_calendar': "Market-wide dividend calendar and today's other scheduled events. "
    'Filter by symbol or event type with query.',
    'screen_equities': 'Execute an unsaved IHSG screen from basic numeric rules on screener '
    'metric_ids. Sorted by the first rule metric; one provider page per call; nothing is saved.',
}


def catalogue(mode='disabled'):
    mode_description = {
        'browser': 'Live retrieval through the signed-in browser; not fixture replay. '
        'Retrieval time does not establish the underlying data date.',
        'fixture': 'Synthetic test examples, not observed market data or current signals.',
        'disabled': 'Research is disabled; calls return AUTH_REQUIRED without retrieving data.',
    }[mode]
    tools = []
    for definition in definitions(mode):
        schema = deepcopy(definition['parameters'])
        if definition['name'] == 'list_metrics' and mode != 'browser':
            schema['properties']['namespace']['enum'] = ['keystats', 'screener']
        tools.append(
            {
                'name': definition['name'],
                'description': DESCRIPTIONS[definition['name']]
                + f' Mode: {mode}. {mode_description}',
                'inputSchema': schema,
                'outputSchema': deepcopy(OUTPUT_SCHEMA),
                'annotations': {
                    'readOnlyHint': True,
                    'destructiveHint': False,
                    'idempotentHint': True,
                    'openWorldHint': True,
                },
            }
        )
    return {'version': VERSION, 'mode': mode, 'tools': tools}
