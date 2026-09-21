import math
from dataclasses import dataclass
from datetime import UTC, datetime

# Verified in the signed-in browser on 2026-09-19; unknown values silently fall back upstream.
FUNDACHART_TIMEFRAMES = ('1y', '3y', '5y', '10y')
CHART_TIMEFRAMES = ('today', '1d', '1w', '1m', '3m', '6m', 'ytd', '1y', '3y', '5y')
SCREEN_OPERATORS = ('>', '<', '<=', '=', '>=')
REPORT_TYPES = {'income_statement': '1', 'balance_sheet': '2', 'cash_flow': '3'}
PERIOD_MODES = {'quarterly': '1', 'annual': '2', 'ttm': '3'}
NAMESPACES = ('screener', 'keystats', 'financials', 'fundachart', 'comparison')
MARKET_WIDE = frozenset({'screener', 'fundachart', 'comparison'})
BASE_TOOLS = ('list_metrics', 'get_key_statistics', 'search_companies')
BROWSER_TOOLS = (
    *BASE_TOOLS,
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
)
ARGUMENTS = {
    'search_companies': frozenset({'query'}),
    'get_key_statistics': frozenset({'symbol', 'query', 'page'}),
    'list_metrics': frozenset({'namespace', 'symbol', 'query', 'page'}),
    'get_company_summary': frozenset({'symbol'}),
    'get_financial_statements': frozenset(
        {'symbol', 'report_type', 'period_mode', 'periods', 'query', 'page'}
    ),
    'get_fundamental_history': frozenset({'symbol', 'metric_id', 'timeframe', 'page'}),
    'get_price_series': frozenset({'symbol', 'timeframe', 'page'}),
    'get_price_performance': frozenset({'symbol'}),
    'get_analyst_consensus': frozenset({'symbol', 'query', 'page'}),
    'get_peer_comparison': frozenset({'symbol', 'query', 'page'}),
    'get_corporate_actions': frozenset({'symbol', 'query', 'page'}),
    'get_dividend_calendar': frozenset({'query', 'page'}),
    'screen_equities': frozenset({'rules', 'page', 'sort_direction'}),
}
TOOL_NAMESPACES = {
    'get_key_statistics': 'keystats',
    'get_company_summary': 'company',
    'get_financial_statements': 'financials',
    'get_fundamental_history': 'fundachart',
    'get_price_series': 'price',
    'get_price_performance': 'price_performance',
    'get_analyst_consensus': 'analyst',
    'get_peer_comparison': 'comparison',
    'get_corporate_actions': 'corpaction',
    'get_dividend_calendar': 'calendar',
    'screen_equities': 'screener',
}


class ToolError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def invalid(message):
    raise ToolError('UNSUPPORTED_INPUT', message)


def parse_symbol(symbol):
    if (
        not isinstance(symbol, str)
        or not 1 <= len(symbol) <= 32
        or not symbol.isascii()
        or not all(c.isalnum() or c in '.-' for c in symbol)
    ):
        invalid('Invalid symbol; use provider metadata, not a URL or path.')
    return symbol.upper()


def parse_choice(args, name, choices):
    value = args.get(name)
    if value not in choices:
        invalid(f'{name} must be one of: {", ".join(choices)}.')
    return value


def parse_int(args, name, low, high, default=None):
    value = args.get(name, default)
    if type(value) is not int or not low <= value <= high:
        invalid(f'{name} must be an integer between {low} and {high}.')
    return value


def parse_rules(rules):
    if not isinstance(rules, list) or not 1 <= len(rules) <= 20:
        invalid('Provide between 1 and 20 screen rules.')
    parsed = []
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {'metric_id', 'operator', 'value'}:
            invalid('Each rule needs metric_id, operator and value only.')
        value = rule['value']
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or abs(value) >= 1e18
        ):
            invalid('Rule value must be a finite number.')
        parsed.append(
            {
                'metric_id': parse_int(rule, 'metric_id', 1, 99_999_999),
                'operator': parse_choice(rule, 'operator', SCREEN_OPERATORS),
                'value': (f'{value:.6f}'.rstrip('0').rstrip('.'))
                if value != int(value)
                else str(int(value)),
            }
        )
    return tuple(parsed)


@dataclass(frozen=True)
class Request:
    symbol: str | None = None
    namespace: str = 'keystats'
    query: str = ''
    page: int = 1
    report_type: str | None = None
    period_mode: str | None = None
    periods: int | None = None
    metric_id: int | None = None
    timeframe: str | None = None
    rules: tuple = ()
    sort_direction: str | None = None

    @classmethod
    def parse(cls, name, args):
        if not isinstance(args, dict):
            invalid('Arguments must be an object.')
        allowed = ARGUMENTS.get(name)
        if allowed is None:
            invalid('Unknown research tool.')
        if name == 'search_companies':
            query = args.get('query')
            if (
                set(args) != {'query'}
                or not isinstance(query, str)
                or not query.strip()
                or len(query) > 100
            ):
                invalid('Provide a nonblank query of at most 100 characters.')
            return cls(namespace='company', query=query.strip(), page=0)
        if set(args) - allowed:
            invalid('Unexpected argument; credentials and URLs are not tool inputs.')
        if name == 'list_metrics':
            namespace = args.get('namespace')
            if namespace not in NAMESPACES:
                invalid('Choose screener, keystats, financials, fundachart, or comparison.')
        else:
            namespace = TOOL_NAMESPACES.get(name, 'keystats')
        symbol = args.get('symbol')
        if symbol is not None:
            symbol = parse_symbol(symbol)
        if 'symbol' in allowed and name != 'list_metrics' and symbol is None:
            invalid('This tool requires a symbol.')
        if name == 'list_metrics':
            if namespace in MARKET_WIDE and symbol is not None:
                invalid(f'{namespace} taxonomy is market-wide; pass symbol=null.')
            if namespace not in MARKET_WIDE and symbol is None:
                invalid('This namespace requires a symbol.')
        query, page = args.get('query', ''), 1
        if 'page' in allowed:
            page = parse_int(args, 'page', 1, 10000, 1)
        if not isinstance(query, str) or len(query) > 100:
            invalid('Query must be at most 100 characters and page a positive integer.')
        fields = {}
        if name == 'get_financial_statements':
            fields['report_type'] = parse_choice(args, 'report_type', tuple(REPORT_TYPES))
            fields['period_mode'] = parse_choice(args, 'period_mode', tuple(PERIOD_MODES))
            if fields['report_type'] == 'balance_sheet' and fields['period_mode'] == 'ttm':
                invalid('Balance sheets have no trailing-twelve-month view.')
            fields['periods'] = parse_int(args, 'periods', 1, 12, 4)
        if name == 'get_fundamental_history':
            fields['metric_id'] = parse_int(args, 'metric_id', 1, 99_999_999)
            fields['timeframe'] = parse_choice(args, 'timeframe', FUNDACHART_TIMEFRAMES)
        if name == 'get_price_series':
            fields['timeframe'] = parse_choice(args, 'timeframe', CHART_TIMEFRAMES)
        if name == 'screen_equities':
            fields['rules'] = parse_rules(args.get('rules'))
            fields['sort_direction'] = parse_choice(
                args, 'sort_direction', ('ascending', 'descending')
            )
        return cls(symbol, namespace, query.casefold().strip(), page, **fields)


def envelope(
    records=None,
    *,
    fixture=None,
    endpoint='',
    error=None,
    total=0,
    page=1,
    next_page=None,
    warnings=None,
):
    warnings = list(warnings or [])
    if fixture:
        warnings.insert(
            0,
            'SYNTHETIC FIXTURE: invented test data, not market observations; not suitable for investment research or backtests.',
        )
        warnings.append(
            'fetched_at is fixture-read time; there is no original market observation date.',
        )
    return {
        'status': 'error' if error else ('partial' if next_page or warnings else 'ok'),
        'records': [] if error else (records or []),
        'provenance': {
            'provider': 'stockbit',
            'fetched_at': datetime.now(UTC).isoformat(),
            'data_as_of': None,
            'published_at': None,
            'endpoint_template': endpoint,
            'fixture_ref': fixture,
            'adjustment': 'unknown',
        },
        'pagination': {
            'page': page,
            'total': total,
            'next_page': next_page,
            'complete': None if error else next_page is None,
        },
        'warnings': warnings,
        'error': None
        if not error
        else {'code': error.code, 'retryable': False, 'message': str(error)},
    }


def record(key, label, namespace, symbol=None, **fields):
    return {
        'key': key,
        'label': label,
        'symbol': symbol,
        'namespace': namespace,
        'value': None,
        'display_value': None,
        'unit': None,
        'currency': None,
        'period': None,
        'timestamp': None,
        'missing_reason': None,
        'attributes': {},
        **fields,
    }


SYMBOL_PROPERTY = {
    'type': 'string',
    'minLength': 1,
    'maxLength': 32,
    'description': 'IDX symbol confirmed through search_companies; never a URL or path.',
}
QUERY_PROPERTY = {
    'type': 'string',
    'maxLength': 100,
    'description': 'Case-insensitive label/ID filter; empty for all.',
}
PAGE_PROPERTY = {'type': 'integer', 'minimum': 1, 'maximum': 10000}
BROWSER_DEFINITIONS = [
    (
        'get_company_summary',
        'Company identity, sector classification and last quote for a confirmed symbol. '
        'Quote time is the provider timestamp; account flags are never returned.',
        {'symbol': SYMBOL_PROPERTY},
    ),
    (
        'get_financial_statements',
        'Statement cells (account x period) for a confirmed symbol. report_type selects the '
        'statement; period_mode quarterly, annual or ttm (not for balance_sheet); periods is '
        'how many most-recent columns to include (1-12). Values are provider raw base-currency '
        'units; pages hold 20 cells, filter accounts with query.',
        {
            'symbol': SYMBOL_PROPERTY,
            'report_type': {'type': 'string', 'enum': list(REPORT_TYPES)},
            'period_mode': {'type': 'string', 'enum': list(PERIOD_MODES)},
            'periods': {'type': 'integer', 'minimum': 1, 'maximum': 12},
            'query': QUERY_PROPERTY,
            'page': PAGE_PROPERTY,
        },
    ),
    (
        'get_fundamental_history',
        'Historical series for one FundaChart metric_id (discover IDs with list_metrics '
        'namespace=fundachart). Points are newest first, 40 per page.',
        {
            'symbol': SYMBOL_PROPERTY,
            'metric_id': {'type': 'integer', 'minimum': 1},
            'timeframe': {'type': 'string', 'enum': list(FUNDACHART_TIMEFRAMES)},
            'page': PAGE_PROPERTY,
        },
    ),
    (
        'get_price_series',
        'Verified LINE price points only (no OHLCV, timezone unverified). Newest first, '
        '40 per page; the first page starts with a period summary record.',
        {
            'symbol': SYMBOL_PROPERTY,
            'timeframe': {'type': 'string', 'enum': list(CHART_TIMEFRAMES)},
            'page': PAGE_PROPERTY,
        },
    ),
    (
        'get_price_performance',
        'Price change, high and low per provider timeframe (1D to 10Y) for a confirmed symbol.',
        {'symbol': SYMBOL_PROPERTY},
    ),
    (
        'get_analyst_consensus',
        'Analyst recommendation summary, price targets and consensus estimates by year. '
        'Estimates are flagged; currency is not stated by the provider.',
        {'symbol': SYMBOL_PROPERTY, 'query': QUERY_PROPERTY, 'page': PAGE_PROPERTY},
    ),
    (
        'get_peer_comparison',
        'Comparison ratios for the symbol beside industry and sector aggregates, plus peer '
        'symbols. Metric labels come from the comparison taxonomy.',
        {'symbol': SYMBOL_PROPERTY, 'query': QUERY_PROPERTY, 'page': PAGE_PROPERTY},
    ),
    (
        'get_corporate_actions',
        'Company corporate actions (dividends, meetings, splits, tender offers) with cum, ex, '
        'record and payment dates kept separate. Bounded provider history; completeness unknown.',
        {'symbol': SYMBOL_PROPERTY, 'query': QUERY_PROPERTY, 'page': PAGE_PROPERTY},
    ),
    (
        'get_dividend_calendar',
        "Market-wide dividend calendar plus today's other scheduled events. Filter by symbol "
        'or event type with query; 20 records per page.',
        {'query': QUERY_PROPERTY, 'page': PAGE_PROPERTY},
    ),
    (
        'screen_equities',
        'Run an unsaved IHSG screen with basic numeric rules on screener metric_ids (discover '
        'with list_metrics namespace=screener). Results sort by the first rule metric; one '
        'provider page (25 companies) per call. Nothing is saved.',
        {
            'rules': {
                'type': 'array',
                'minItems': 1,
                'maxItems': 20,
                'items': {
                    'type': 'object',
                    'properties': {
                        'metric_id': {'type': 'integer', 'minimum': 1},
                        'operator': {'type': 'string', 'enum': list(SCREEN_OPERATORS)},
                        'value': {'type': 'number'},
                    },
                    'required': ['metric_id', 'operator', 'value'],
                    'additionalProperties': False,
                },
            },
            'page': PAGE_PROPERTY,
            'sort_direction': {'type': 'string', 'enum': ['ascending', 'descending']},
        },
    ),
]


def definitions(mode='fixture'):
    result = []
    for name in ('list_metrics', 'get_key_statistics'):
        properties = {
            'symbol': {
                'type': ['string', 'null'],
                'description': 'Stock symbol; null for screener taxonomy. Fixture coverage varies.',
            },
            'query': {
                'type': 'string',
                'description': 'Case-insensitive label/ID filter; empty for all.',
            },
            'page': {'type': 'integer', 'minimum': 1, 'maximum': 10000},
        }
        if name == 'list_metrics':
            properties['namespace'] = {
                'type': 'string',
                'enum': list(NAMESPACES)
                if mode == 'browser'
                else ['screener', 'keystats', 'financials'],
            }
        result.append(
            {
                'type': 'function',
                'name': name,
                'strict': True,
                'description': 'Read synthetic fixture examples only, NOT observed market data. Returns at most 20 records; follow next_page with identical filters.',
                'parameters': {
                    'type': 'object',
                    'properties': properties,
                    'required': list(properties),
                    'additionalProperties': False,
                },
            }
        )
    result.append(
        {
            'type': 'function',
            'name': 'search_companies',
            'strict': True,
            'description': 'Search company names or symbols in synthetic test examples. Returns IDX equity candidates in provider order; do not silently resolve ambiguous names. Not live data.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'minLength': 1, 'maxLength': 100, 'pattern': r'\S'}
                },
                'required': ['query'],
                'additionalProperties': False,
            },
        }
    )
    if mode == 'browser':
        for definition in result:
            definition['description'] = (
                'Read Stockbit research data through the signed-in research browser. '
                'Respect unknown dates and units, preserve ambiguous company candidates, '
                'follow pagination within the tool budget, and cite source_url. '
                'Login and verification require user action.'
            )
    if mode == 'browser':
        for name, description, properties in BROWSER_DEFINITIONS:
            result.append(
                {
                    'type': 'function',
                    'name': name,
                    'strict': True,
                    'description': description
                    + ' Uses the signed-in research browser; cite source_url and keep warnings.',
                    'parameters': {
                        'type': 'object',
                        'properties': properties,
                        'required': list(properties),
                        'additionalProperties': False,
                    },
                }
            )
    return result
