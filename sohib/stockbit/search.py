"""Company normalization and synthetic-query replay."""

import hashlib
import json
import re
from urllib.parse import urlencode

from .contracts import ToolError, envelope, record


def search_path(query):
    """Encode only the observed request parameters, on a fixed endpoint."""
    return '/search?' + urlencode(
        [
            ('keyword', query),
            ('page', 0),
            ('type', 'all'),
            ('catalog_types', 'CATALOG_TYPE_SECTOR'),
            ('catalog_types', 'CATALOG_TYPE_INDUSTRY'),
        ]
    )


def companies(payload):
    data = payload.get('data') if isinstance(payload, dict) else None
    rows = data.get('company') if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ToolError('SCHEMA_CHANGED', 'Expected company candidates.')
    records, warnings = [], []
    for row in rows:
        if not isinstance(row, dict):
            raise ToolError('SCHEMA_CHANGED', 'Malformed company candidate.')
        if (row.get('type'), row.get('other'), row.get('country'), row.get('exchange')) != (
            'Saham',
            'saham',
            'ID',
            'IDX',
        ):
            if 'Excluded non-equity or unknown instrument classifications.' not in warnings:
                warnings.append('Excluded non-equity or unknown instrument classifications.')
            continue
        symbol, label, key = row.get('name'), row.get('desc'), row.get('id')
        if (
            not isinstance(symbol, str)
            or not re.fullmatch(r'[A-Za-z0-9.-]{1,32}', symbol)
            or not isinstance(label, str)
            or not label
            or not isinstance(key, str)
            or not key
            or type(row.get('is_tradeable')) is not bool
        ):
            raise ToolError('SCHEMA_CHANGED', 'Malformed company identity or tradeability.')
        path = '/symbol/' + symbol
        if row.get('url') not in (path, path[1:]):
            raise ToolError('SCHEMA_CHANGED', 'Unexpected company path.')
        attrs = {
            k: row.get(k) for k in ('country', 'exchange', 'is_tradeable', 'symbol_2', 'symbol_3')
        }
        attrs.update(company_id=key, instrument_type=row['type'], company_path=path)
        records.append(
            record(
                key,
                label,
                'stockbit.company',
                symbol,
                value=symbol,
                display_value=label,
                attributes=attrs,
            )
        )
    return records, warnings


def search_fixture(directory, query):
    fixture = 'company-search.json'
    try:
        raw = (directory / fixture).read_bytes()
        capture = json.loads(raw)
        if not isinstance(capture, dict) or not isinstance(capture.get('examples'), list):
            raise ToolError('SCHEMA_CHANGED', 'Malformed search capture.')
        match = None
        for example in capture['examples']:
            if not isinstance(example, dict) or not isinstance(example.get('query'), str):
                raise ToolError('SCHEMA_CHANGED', 'Malformed captured query.')
            if example['query'].strip().casefold() == query.casefold():
                match = example
                break
        if match is None:
            raise ToolError(
                'NO_DATA', 'No captured response for this query; no live request was made.'
            )
        records, warnings = companies(match.get('response'))
        for row in records:
            row['attributes'].update(
                source_observed_at=None,
                fixture_kind='synthetic',
                evidence_sha256=hashlib.sha256(raw).hexdigest(),
            )
        result = envelope(
            records, fixture=fixture, endpoint='/search', page=0, total=None, warnings=warnings
        )
        result['pagination']['complete'] = None
        if not records:
            result['status'] = 'ok'
        if len(json.dumps(result).encode()) > 24000:
            raise ToolError('SCHEMA_CHANGED', 'Search response exceeds context budget.')
        return result
    except ToolError as error:
        return envelope(fixture=fixture, endpoint='/search', page=0, total=None, error=error)
    except (OSError, ValueError):
        return envelope(
            fixture=fixture,
            endpoint='/search',
            page=0,
            total=None,
            error=ToolError('SCHEMA_CHANGED', 'Search capture unavailable or malformed.'),
        )
