"""Browser-mode tool adapters: allowlisted fetches, normalization, filtering and paging."""

from . import events, financials, normalize
from .api_routes import screen_body
from .contracts import PERIOD_MODES, REPORT_TYPES, ToolError, envelope
from .search import companies, search_path

PAGE, SERIES_PAGE = 20, 40
UNVERIFIED = 'Coverage and data-as-of are unverified; retrieval time is not publication time.'
KEYSTATS = '/keystats/ratio/v1/{symbol}?year_limit=10'
FINANCIAL = (
    '/findata-view/company/financial?symbol={symbol}&data_type=1'
    '&report_type={report_type}&statement_type={statement_type}'
)
TAXONOMY = {
    'screener': '/screener/metric',
    'fundachart': '/fundachart/metrics?metric_name=fundachart',
    'comparison': '/comparison/metrics',
}
ENDPOINTS = {
    'search_companies': '/search',
    'get_key_statistics': KEYSTATS,
    'get_company_summary': '/emitten/{symbol}/info?with_sub_industry=true',
    'get_financial_statements': FINANCIAL,
    'get_fundamental_history': '/fundachart?item={metric_id}&companies={symbol}&timeframe={timeframe}',
    'get_price_series': '/charts/{symbol}/daily?timeframe={timeframe}',
    'get_price_performance': '/company-price-feed/price-performance/{symbol}',
    'get_analyst_consensus': '/analyst-ratings/{symbol}; /analyst-ratings/{symbol}/consensus',
    'get_peer_comparison': (
        '/comparison/{symbol}/ratios; /comparison/{symbol}/industries; /comparison/metrics'
    ),
    'get_corporate_actions': (
        '/corpaction/{symbol}?limit=30; /corpaction/{symbol}/stock_conversion?page=1&limit=50'
    ),
    'get_dividend_calendar': '/corpaction/dividend; /corpaction',
    'screen_equities': 'POST /screener/templates (save=0, screenerid=0, type=TEMPLATE_TYPE_CUSTOM)',
}


def endpoint_for(name, request):
    if name == 'list_metrics':
        if request.namespace == 'keystats':
            return KEYSTATS
        if request.namespace == 'financials':
            return FINANCIAL
        return TAXONOMY.get(request.namespace, '')
    return ENDPOINTS.get(name, '')


def matches(row, query):
    haystack = ' '.join(filter(None, [row['label'], row['key'], row.get('symbol')])).casefold()
    return query in haystack


def paged(rows, request, size=PAGE, warnings=(), endpoint='', data_as_of=None):
    rows = [row for row in rows if not request.query or matches(row, request.query)]
    start = (request.page - 1) * size
    result = envelope(
        rows[start : start + size],
        endpoint=endpoint,
        page=request.page,
        total=len(rows),
        next_page=request.page + 1 if start + size < len(rows) else None,
        warnings=warnings,
    )
    result['provenance']['data_as_of'] = data_as_of
    return result


def metadata_only(rows):
    for row in rows:
        row.update(value=None, display_value=None, unit=None, missing_reason='metadata_only')
        row['attributes'] = {
            k: v
            for k, v in row['attributes'].items()
            if k not in {'scale', 'decimal_value', 'numeric_parse'}
        }
    return rows


def financial_path(symbol, report_code, statement_code):
    return FINANCIAL.format(symbol=symbol, report_type=report_code, statement_type=statement_code)


def search_companies(session, request):
    rows, warnings = companies(session.get(search_path(request.query)))
    result = envelope(rows, endpoint='/search', page=0, total=None, warnings=warnings)
    result['pagination']['complete'] = None
    if not rows:
        result['status'] = 'ok'
    return result


def get_key_statistics(session, request):
    payload = session.get(KEYSTATS.format(symbol=request.symbol))
    rows = normalize.key_statistics(payload, request.symbol)
    return paged(rows, request, endpoint=KEYSTATS, warnings=[UNVERIFIED])


def list_metrics(session, request):
    namespace = request.namespace
    if namespace == 'keystats':
        payload = session.get(KEYSTATS.format(symbol=request.symbol))
        rows = normalize.key_statistics(payload, request.symbol)
    elif namespace == 'financials':
        paths = [financial_path(request.symbol, code, '1') for code in REPORT_TYPES.values()]
        rows = []
        for code, payload in zip(REPORT_TYPES.values(), session.get_many(paths), strict=True):
            rows += financials.financial_accounts(payload, request.symbol, code)
    else:
        rows = normalize.metric_taxonomy(session.get(TAXONOMY[namespace]), namespace)
    warnings = [UNVERIFIED]
    if namespace != 'keystats':
        warnings.append(f'Metric IDs belong to the {namespace} namespace; other services differ.')
    return paged(
        metadata_only(rows),
        request,
        endpoint=endpoint_for('list_metrics', request),
        warnings=warnings,
    )


def get_company_summary(session, request):
    endpoint = ENDPOINTS['get_company_summary']
    payload = session.get(endpoint.format(symbol=request.symbol))
    rows, warnings = normalize.company_summary(payload, request.symbol)
    result = envelope(rows, endpoint=endpoint, page=1, total=len(rows), warnings=warnings)
    result['provenance']['data_as_of'] = rows[1]['timestamp']
    return result


def get_financial_statements(session, request):
    report_code = REPORT_TYPES[request.report_type]
    statement_code = PERIOD_MODES[request.period_mode]
    payload = session.get(financial_path(request.symbol, report_code, statement_code))
    rows, notes = financials.financial_statements(
        payload, request.symbol, report_code, request.periods
    )
    for row in rows:
        row['attributes']['period_mode'] = request.period_mode
    return paged(rows, request, endpoint=FINANCIAL, warnings=notes)


def get_fundamental_history(session, request):
    endpoint = ENDPOINTS['get_fundamental_history']
    path = endpoint.format(
        metric_id=request.metric_id, symbol=request.symbol, timeframe=request.timeframe
    )
    rows, name = normalize.fundamental_history(session.get(path), request.symbol, request.metric_id)
    warnings = [
        'FundaChart values are provider-computed history; publication timing and restatements are unknown.'
    ]
    if name is None:
        warnings.append('Provider returned no series for this metric and symbol.')
    return paged(rows, request, SERIES_PAGE, warnings, endpoint)


def get_price_series(session, request):
    endpoint = ENDPOINTS['get_price_series']
    payload = session.get(endpoint.format(symbol=request.symbol, timeframe=request.timeframe))
    rows, warnings = normalize.price_series(payload, request.symbol, request.timeframe)
    return paged(rows, request, SERIES_PAGE, warnings, endpoint)


def get_price_performance(session, request):
    endpoint = ENDPOINTS['get_price_performance']
    rows = normalize.price_performance(
        session.get(endpoint.format(symbol=request.symbol)), request.symbol
    )
    warnings = ['Performance windows are provider-defined; retrieval time is not the as-of time.']
    return envelope(rows, endpoint=endpoint, page=1, total=len(rows), warnings=warnings)


def get_analyst_consensus(session, request):
    symbol = request.symbol
    ratings, consensus = session.get_many(
        [f'/analyst-ratings/{symbol}', f'/analyst-ratings/{symbol}/consensus']
    )
    rows = normalize.analyst_ratings(ratings, symbol) + normalize.analyst_consensus(
        consensus, symbol
    )
    warnings = [
        'Estimate currency is not stated; "B" values are parsed as billions of the reporting currency.',
        'last_updated is a provider display date; coverage counts are as shown by the provider.',
    ]
    return paged(rows, request, endpoint=ENDPOINTS['get_analyst_consensus'], warnings=warnings)


def get_peer_comparison(session, request):
    symbol = request.symbol
    ratios, industries, taxonomy = session.get_many(
        [f'/comparison/{symbol}/ratios', f'/comparison/{symbol}/industries', '/comparison/metrics']
    )
    rows = normalize.peer_comparison(ratios, industries, taxonomy, symbol)
    warnings = [
        "Industry and sector aggregates are provider-computed; peers are the provider's default set."
    ]
    return paged(rows, request, endpoint=ENDPOINTS['get_peer_comparison'], warnings=warnings)


def get_corporate_actions(session, request):
    symbol = request.symbol
    actions, conversions = session.get_many(
        [f'/corpaction/{symbol}?limit=30', f'/corpaction/{symbol}/stock_conversion?page=1&limit=50']
    )
    rows, warnings = events.corporate_actions(actions, symbol)
    extra, more = events.stock_conversions(conversions, symbol)
    warnings += more
    warnings.append('Provider history is bounded (limit=30); completeness is unknown.')
    result = paged(
        rows + extra, request, endpoint=ENDPOINTS['get_corporate_actions'], warnings=warnings
    )
    result['pagination']['complete'] = None
    return result


def get_dividend_calendar(session, request):
    dividends, today = session.get_many(['/corpaction/dividend', '/corpaction'])
    rows, as_of = events.dividend_calendar(dividends)
    extra, _, warnings = events.calendar_today(today)
    warnings.insert(
        0,
        "Dividend calendar is the provider's current list; date range and completeness are unknown.",
    )
    return paged(
        rows + extra,
        request,
        endpoint=ENDPOINTS['get_dividend_calendar'],
        warnings=warnings,
        data_as_of=as_of,
    )


def screen_equities(session, request):
    labels = normalize.metric_labels(session.get('/screener/metric'))
    rules = []
    for rule in request.rules:
        if rule['metric_id'] not in labels:
            raise ToolError(
                'UNSUPPORTED_INPUT',
                f'metric_id {rule["metric_id"]} is not a screener metric; use list_metrics namespace=screener.',
            )
        rules.append({**rule, 'label': labels[rule['metric_id']][0]})
    direction = 'asc' if request.sort_direction == 'ascending' else 'desc'
    payload = session.post('/screener/templates', screen_body(rules, request.page, direction))
    rows, paging = normalize.screen_results(payload)
    warnings = [
        'Unsaved screen executed once; nothing was stored. Provider refresh timing applies.',
        'Results are sorted by the first rule metric.',
    ]
    if paging['page'] != request.page:
        warnings.append('Provider returned a different page than requested.')
    return envelope(
        rows,
        endpoint=ENDPOINTS['screen_equities'],
        page=paging['page'],
        total=paging['total'],
        next_page=paging['page'] + 1
        if paging['page'] * paging['per_page'] < paging['total']
        else None,
        warnings=warnings,
    )


ADAPTERS = {
    'search_companies': search_companies,
    'get_key_statistics': get_key_statistics,
    'list_metrics': list_metrics,
    'get_company_summary': get_company_summary,
    'get_financial_statements': get_financial_statements,
    'get_fundamental_history': get_fundamental_history,
    'get_price_series': get_price_series,
    'get_price_performance': get_price_performance,
    'get_analyst_consensus': get_analyst_consensus,
    'get_peer_comparison': get_peer_comparison,
    'get_corporate_actions': get_corporate_actions,
    'get_dividend_calendar': get_dividend_calendar,
    'screen_equities': screen_equities,
}
