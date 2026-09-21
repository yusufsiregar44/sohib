import hashlib
import json
from pathlib import Path

from .contracts import BASE_TOOLS, BROWSER_TOOLS, Request, ToolError, envelope
from .normalize import key_statistics, screener_metrics

FIXTURES = Path(__file__).parent / 'fixtures'


class StockbitTools:
    """Synthetic fixture examples; browser mode for live, signed-in research."""

    def __init__(self, mode='disabled', fixture_dir=FIXTURES, session=None):
        if mode not in {'disabled', 'fixture', 'browser'}:
            raise ValueError('Stockbit supports disabled, fixture, or browser mode.')
        self.mode, self.fixture_dir = mode, Path(fixture_dir)
        # Only the in-page fetch transport serves the wider catalogue.
        self.names = frozenset(BROWSER_TOOLS if mode == 'browser' else BASE_TOOLS)
        if mode == 'browser' and session is None:
            from .browser import BrowserSession

            session = BrowserSession()
        self.session = session

    def call(self, name, arguments):
        fixture, endpoint = None, ''
        try:
            if name not in self.names:
                raise ToolError('UNSUPPORTED_INPUT', 'Unknown research tool.')
            request = Request.parse(name, arguments)
            if self.mode == 'disabled':
                raise ToolError(
                    'AUTH_REQUIRED',
                    'Stockbit is disabled. Configure browser mode or fixture mode for synthetic examples.',
                )
            if self.mode == 'browser':
                return self._browser(name, request)
            if name == 'search_companies':
                from .search import search_fixture

                return search_fixture(self.fixture_dir, request.query)
            if request.namespace not in {'screener', 'keystats'}:
                raise ToolError(
                    'UNSUPPORTED_INPUT',
                    'Only screener and keystats fixtures exist; other namespaces need browser mode.',
                )
            if request.namespace == 'screener':
                fixture, endpoint = 'screener-metrics.json', 'GET /screener/metric'
            elif request.symbol == 'MAPI':
                fixture, endpoint = (
                    'mapi-keystats.json',
                    'GET /keystats/ratio/v1/{symbol}?year_limit=10',
                )
            else:
                raise ToolError('NO_DATA', 'No fixture for this symbol. No live request was made.')
            raw = (self.fixture_dir / fixture).read_bytes()
            payload = json.loads(raw)
            records = (
                screener_metrics(payload)
                if request.namespace == 'screener'
                else key_statistics(payload, request.symbol)
            )
            if name == 'list_metrics':
                for row in records:
                    row.update(
                        value=None, display_value=None, unit=None, missing_reason='metadata_only'
                    )
                    row['attributes'] = {
                        k: v
                        for k, v in row['attributes'].items()
                        if k not in {'scale', 'decimal_value', 'numeric_parse'}
                    }
            for row in records:
                row['attributes']['source_observed_at'] = None
                row['attributes']['fixture_kind'] = 'synthetic'
                row['attributes']['evidence_sha256'] = hashlib.sha256(raw).hexdigest()
            records = [
                r for r in records if request.query in (r['label'] + ' ' + r['key']).casefold()
            ]
            total, start = len(records), (request.page - 1) * 20
            selected = records[start : start + 20]
            next_page = request.page + 1 if start + 20 < total else None
            result = envelope(
                selected,
                fixture=fixture,
                endpoint=endpoint,
                total=total,
                page=request.page,
                next_page=next_page,
                warnings=[
                    'Synthetic examples have no market observation date, currency or reporting period.'
                ],
            )
            if len(json.dumps(result).encode()) > 24000:
                raise ToolError(
                    'SCHEMA_CHANGED',
                    'Normalized page exceeds the context budget; narrow the query.',
                )
            return result
        except ToolError as error:
            return envelope(fixture=fixture, endpoint=endpoint, error=error)
        except (OSError, ValueError):
            return envelope(
                fixture=fixture,
                endpoint=endpoint,
                error=ToolError(
                    'SCHEMA_CHANGED', 'Fixture unavailable or malformed; no records returned.'
                ),
            )

    def _browser(self, name, request):
        from .adapters import ADAPTERS, endpoint_for

        endpoint = endpoint_for(name, request)
        try:
            result = ADAPTERS[name](self.session, request)
            for row in result['records']:
                row['attributes'].update(
                    source_url=self.session.source_url,
                    retrieval_mode='browser',
                )
            if name == 'search_companies' and len(result['records']) > 1:
                result['warnings'].append(
                    'Multiple equity candidates; do not silently select a company.'
                )
                result['status'] = 'partial'
            if len(json.dumps(result).encode()) > 24000:
                raise ToolError('SCHEMA_CHANGED', 'Normalized response exceeds context budget.')
            return result
        except ToolError as error:
            return envelope(endpoint=endpoint, page=request.page, total=None, error=error)
