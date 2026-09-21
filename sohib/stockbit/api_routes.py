"""Allowlisted exodus.stockbit.com research routes. The browser worker fetches nothing else."""

import json
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlsplit

from .contracts import CHART_TIMEFRAMES, FUNDACHART_TIMEFRAMES, SCREEN_OPERATORS, ToolError

ORIGIN = 'https://exodus.stockbit.com'
SITE = 'https://stockbit.com'
SYMBOL = r'[A-Z0-9.-]{1,32}'
SCREEN_UNIVERSE = json.dumps({'scope': 'IHSG', 'scopeID': '', 'name': ''}, separators=(',', ':'))
SCREEN_CONSTANTS = {
    'save': '0',
    'screenerid': '0',
    'type': 'TEMPLATE_TYPE_CUSTOM',
    'description': '',
    'ordercol': 2,
    'universe': SCREEN_UNIVERSE,
}
SCREEN_NAME = 'TEMPLATE_BUILD_0000_0000'


def _re(pattern):
    return re.compile(pattern)


def _choice(*values):
    return _re('|'.join(re.escape(v) for v in values))


def reject(message='Endpoint is not an allowed research read.'):
    raise ToolError('UNSUPPORTED_INPUT', message)


@dataclass(frozen=True)
class Route:
    method: str
    path: re.Pattern
    params: dict = field(default_factory=dict)
    required: frozenset = frozenset()
    repeatable: frozenset = frozenset()
    page: str | None = None
    body: object = None


ROUTES = (
    Route(
        'GET',
        _re('/search'),
        {
            'keyword': _re(r'[^\x00-\x1f\x7f]{1,100}'),
            'page': _re('0'),
            'type': _re('all'),
            'catalog_types': _choice('CATALOG_TYPE_SECTOR', 'CATALOG_TYPE_INDUSTRY'),
        },
        frozenset({'keyword'}),
        frozenset({'catalog_types'}),
        SITE + '/stream',
    ),
    Route(
        'GET',
        _re(f'/keystats/ratio/v1/(?P<symbol>{SYMBOL})'),
        {'year_limit': _re('10')},
        frozenset({'year_limit'}),
        page=SITE + '/symbol/{symbol}/keystats',
    ),
    Route('GET', _re('/screener/metric'), page=SITE + '/screener'),
    Route(
        'GET',
        _re('/fundachart/metrics'),
        {'metric_name': _re('fundachart')},
        frozenset({'metric_name'}),
    ),
    Route('GET', _re('/comparison/metrics')),
    Route(
        'GET',
        _re(f'/emitten/(?P<symbol>{SYMBOL})/info'),
        {'with_sub_industry': _re('true')},
        page=SITE + '/symbol/{symbol}',
    ),
    Route(
        'GET',
        _re('/findata-view/company/financial'),
        {
            'symbol': _re(SYMBOL),
            'data_type': _re('1'),
            'report_type': _re('[123]'),
            'statement_type': _re('[1-9]|1[0-3]'),
        },
        frozenset({'symbol', 'data_type', 'report_type', 'statement_type'}),
        page=SITE + '/symbol/{symbol}/financials',
    ),
    Route(
        'GET',
        _re('/fundachart'),
        {
            'item': _re(r'[1-9][0-9]{0,7}'),
            'companies': _re(SYMBOL),
            'timeframe': _choice(*FUNDACHART_TIMEFRAMES),
        },
        frozenset({'item', 'companies', 'timeframe'}),
        page=SITE + '/symbol/{symbol}/fundachart',
    ),
    Route(
        'GET',
        _re(f'/charts/(?P<symbol>{SYMBOL})/daily'),
        {'timeframe': _choice(*CHART_TIMEFRAMES)},
        frozenset({'timeframe'}),
        page=SITE + '/symbol/{symbol}',
    ),
    Route(
        'GET',
        _re(f'/company-price-feed/price-performance/(?P<symbol>{SYMBOL})'),
        page=SITE + '/symbol/{symbol}',
    ),
    Route(
        'GET',
        _re(f'/analyst-ratings/(?P<symbol>{SYMBOL})'),
        page=SITE + '/symbol/{symbol}/analysis',
    ),
    Route(
        'GET',
        _re(f'/analyst-ratings/(?P<symbol>{SYMBOL})/consensus'),
        page=SITE + '/symbol/{symbol}/analysis',
    ),
    Route(
        'GET',
        _re(f'/comparison/(?P<symbol>{SYMBOL})/industries'),
        page=SITE + '/symbol/{symbol}/comparison',
    ),
    Route(
        'GET',
        _re(f'/comparison/(?P<symbol>{SYMBOL})/ratios'),
        page=SITE + '/symbol/{symbol}/comparison',
    ),
    Route('GET', _re('/corpaction/dividend'), page=SITE + '/calendar/dividend'),
    Route('GET', _re('/corpaction'), page=SITE + '/calendar'),
    Route(
        'GET',
        _re(f'/corpaction/(?P<symbol>{SYMBOL})'),
        {'limit': _re('[1-9][0-9]?|100')},
        frozenset({'limit'}),
        page=SITE + '/symbol/{symbol}',
    ),
    Route(
        'GET',
        _re(f'/corpaction/(?P<symbol>{SYMBOL})/stock_conversion'),
        {'page': _re('[1-9][0-9]{0,3}'), 'limit': _re('[1-9][0-9]?|100')},
        frozenset({'page', 'limit'}),
        page=SITE + '/symbol/{symbol}',
    ),
    Route('POST', _re('/screener/templates'), page=SITE + '/screener', body='screen'),
)


def split(path, method='GET'):
    """Return (route, match, params) for an allowlisted request or raise UNSUPPORTED_INPUT."""
    if not isinstance(path, str) or not path.isascii() or not path.isprintable() or ' ' in path:
        reject()
    url = urlsplit(path)
    if url.scheme or url.netloc or url.fragment or not url.path.startswith('/'):
        reject()
    if '//' in url.path or '..' in path or '\\' in path or '%' in url.path:
        reject()
    try:
        pairs = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        reject()
    for route in ROUTES:
        match = route.path.fullmatch(url.path)
        if route.method != method or not match:
            continue
        seen = set()
        for name, value in pairs:
            pattern = route.params.get(name)
            if pattern is None or not pattern.fullmatch(value):
                reject()
            if name in seen and name not in route.repeatable:
                reject()
            seen.add(name)
        if route.required - seen:
            reject()
        return route, match, dict(pairs)
    reject()


def validate_api_path(path, method='GET'):
    split(path, method)
    return path


def validate_body(path, body):
    route = split(path, 'GET' if body is None else 'POST')[0]
    if route.body is None:
        if body is not None:
            reject()
        return None
    return validate_screen_body(body)


def citation(path):
    """Human page for provenance; the API URL itself when no page fits."""
    route, match, params = split(path, 'GET' if route_method(path) == 'GET' else 'POST')
    symbol = match.groupdict().get('symbol') or params.get('symbol') or params.get('companies')
    if route.page is None or ('{symbol}' in route.page and not symbol):
        return ORIGIN + path
    return route.page.format(symbol=symbol)


def route_method(path):
    for method in ('GET', 'POST'):
        try:
            split(path, method)
            return method
        except ToolError:
            continue
    reject()


def screen_body(rules, page, sort_direction):
    """Serialize an unsaved custom screen exactly as the observed web request does."""
    filters = [
        {
            'type': 'basic',
            'item1': rule['metric_id'],
            'item1name': rule['label'],
            'operator': rule['operator'],
            'item2': rule['value'],
            'multiplier': '',
        }
        for rule in rules
    ]
    body = {
        'name': SCREEN_NAME,
        'ordertype': sort_direction,
        'page': page,
        'filters': json.dumps(filters, separators=(',', ':')),
        'sequence': ','.join(str(rule['metric_id']) for rule in rules),
        **SCREEN_CONSTANTS,
    }
    return validate_screen_body(body)


def validate_screen_body(body):
    """Execution only: reject anything that could persist, favourite, or widen a screen."""
    expected = {'name', 'ordertype', 'page', 'filters', 'sequence', *SCREEN_CONSTANTS}
    if not isinstance(body, dict) or set(body) != expected:
        reject('Screen request shape is not allowed.')
    if any(body[key] != value for key, value in SCREEN_CONSTANTS.items()):
        reject('Screen request must stay an unsaved custom IHSG screen.')
    if body['name'] != SCREEN_NAME or body['ordertype'] not in {'asc', 'desc'}:
        reject('Screen request shape is not allowed.')
    if type(body['page']) is not int or not 1 <= body['page'] <= 10000:
        reject('Screen page must be a positive integer.')
    try:
        filters = json.loads(body['filters'])
    except (TypeError, ValueError):
        reject('Screen filters must be serialized rules.')
    if not isinstance(filters, list) or not 1 <= len(filters) <= 20:
        reject('Provide between 1 and 20 screen rules.')
    for rule in filters:
        if not isinstance(rule, dict) or set(rule) != {
            'type',
            'item1',
            'item1name',
            'operator',
            'item2',
            'multiplier',
        }:
            reject('Screen rule shape is not allowed.')
        if (
            rule['type'] != 'basic'
            or type(rule['item1']) is not int
            or rule['item1'] <= 0
            or not isinstance(rule['item1name'], str)
            or rule['operator'] not in SCREEN_OPERATORS
            or not isinstance(rule['item2'], str)
            or not re.fullmatch(r'-?[0-9]{1,18}(\.[0-9]{1,6})?', rule['item2'])
            or rule['multiplier'] != ''
        ):
            reject('Screen rules accept one screener metric, a comparator and a number.')
    if body['sequence'] != ','.join(str(rule['item1']) for rule in filters):
        reject('Screen sequence must list the rule metrics.')
    return body
