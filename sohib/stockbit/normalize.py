import html
import math
import re
from decimal import Decimal, InvalidOperation

from .contracts import ToolError, record


class SchemaChanged(ToolError):
    def __init__(self):
        super().__init__('SCHEMA_CHANGED', 'Unexpected upstream shape; no records returned.')


def text(value, allow_empty=True):
    if not isinstance(value, str) or (not allow_empty and not value):
        raise SchemaChanged()
    return value


def number(value):
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise SchemaChanged()
    return value


def decimal_text(value):
    """Numeric strings such as "1380" or "22590334.00"; blanks and markers stay missing."""
    if value is None or value in {'', '-', 'NA'}:
        return None
    if not isinstance(value, str):
        raise SchemaChanged()
    try:
        parsed = Decimal(value.replace(',', ''))
    except InvalidOperation:
        raise SchemaChanged() from None
    if not parsed.is_finite():
        raise SchemaChanged()
    return float(parsed)


def blank_to_none(value):
    if value is None:
        return None
    return text(value) or None


def display_number(raw):
    if raw is None:
        return None, None, 'provider_missing', {}
    if not isinstance(raw, str):
        raise SchemaChanged()
    text = html.unescape(raw).strip()
    if text in {'', '-', '—', '–'}:
        return None, None, 'provider_missing', {}
    negative = text.startswith('(') and text.endswith(')')
    if negative:
        text = text[1:-1].strip()
    percent = text.endswith('%')
    billions = text.endswith(' B')
    number = text[:-1].strip() if percent or billions else text
    # Only the observed comma-thousands/dot-decimal format is accepted.
    if not re.fullmatch(r'-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', number):
        return raw, None, None, {'numeric_parse': 'not_supported'}
    value = Decimal(number.replace(',', ''))
    if negative:
        value = -value
    scale = 10**9 if billions else 1
    value *= scale
    attrs = {'scale': scale, 'decimal_value': str(value)}
    return float(value), 'percent' if percent else ('base_units' if billions else None), None, attrs


def display_record(key, label, namespace, symbol, raw, **fields):
    """Record whose value is parsed from a provider display string."""
    value, unit, missing, attrs = display_number(raw)
    attrs.update(fields.pop('attributes', {}))
    return record(
        key,
        label,
        namespace,
        symbol,
        value=value,
        display_value=raw,
        unit=unit,
        missing_reason=missing,
        attributes=attrs,
        **fields,
    )


def key_statistics(payload, symbol):
    try:
        groups = payload['data']['closure_fin_items_results']
        if not isinstance(groups, list):
            raise SchemaChanged()
        result = []
        for group in groups:
            group_name, items = group['keystats_name'], group['fin_name_results']
            if not isinstance(group_name, str) or not isinstance(items, list):
                raise SchemaChanged()
            for item in items:
                field = item['fitem']
                ident, name, raw = field['id'], field['name'], field['value']
                if not isinstance(ident, str) or not ident.isdigit() or not isinstance(name, str):
                    raise SchemaChanged()
                value, unit, missing, attrs = display_number(raw)
                # Units/currency cannot be inferred from the report currency for every metric.
                attrs.update({'group': group_name, 'provider_metric_id': ident})
                result.append(
                    record(
                        f'keystats:{ident}',
                        name,
                        'keystats',
                        symbol,
                        value=value,
                        display_value=raw,
                        unit=unit,
                        missing_reason=missing,
                        attributes=attrs,
                    )
                )
        return result
    except (KeyError, TypeError):
        raise SchemaChanged() from None


def metric_taxonomy(payload, namespace):
    """Shared fitem tree used by the screener, FundaChart and comparison taxonomies."""
    result = []

    def walk(nodes, path):
        if not isinstance(nodes, list):
            raise SchemaChanged()
        for node in nodes:
            ident, name, children = node['fitem_id'], node['fitem_name'], node['child']
            if (
                type(ident) is not int
                or not isinstance(name, str)
                or not isinstance(children, list)
            ):
                raise SchemaChanged()
            if children:
                walk(children, [*path, name])
            else:
                result.append(
                    record(
                        f'{namespace}:{ident}',
                        name,
                        namespace,
                        missing_reason='metadata_only',
                        attributes={'provider_metric_id': str(ident), 'category_path': path},
                    )
                )

    try:
        walk(payload['data'], [])
    except (KeyError, TypeError):
        raise SchemaChanged() from None
    return result


def screener_metrics(payload):
    return metric_taxonomy(payload, 'screener')


def metric_labels(payload):
    """Map provider metric id -> (label, category path) from a taxonomy payload."""
    return {
        int(row['attributes']['provider_metric_id']): (
            row['label'],
            row['attributes']['category_path'],
        )
        for row in metric_taxonomy(payload, 'taxonomy')
    }


COMPANY_FIELDS = {
    'name': str,
    'symbol': str,
    'sector': str,
    'sub_sector': str,
    'exchange': str,
    'country': str,
    'status': str,
    'type_company': str,
    'id': str,
    'price': str,
    'previous': str,
    'change': str,
    'percentage': int | float,
    'volume': str,
    'formatted_price': str,
    'date': str,
    'time': str,
    'updated': str,
}


def company_summary(payload, symbol):
    """Identity and quote fields only; followers, sentiment and account flags never leave."""
    try:
        data = payload['data']
        for field, kind in COMPANY_FIELDS.items():
            if not isinstance(data[field], kind) or isinstance(data[field], bool):
                raise SchemaChanged()
        if data['symbol'].upper() != symbol:
            raise SchemaChanged()
        classification = {}
        for catalog in data.get('catalogs') or []:
            kind, name = catalog.get('company_type'), catalog.get('catalog_name')
            if kind in {'listing-board', 'sub_industry'} and isinstance(name, str):
                classification[kind.replace('-', '_')] = name
        indexes = data.get('indexes') or []
        if not all(isinstance(index, str) for index in indexes):
            raise SchemaChanged()
        market = data.get('market_hour') or {}
        quote = {
            'quote_date': data['date'],
            'quote_time': data['time'],
            'market_status': blank_to_none(market.get('status')),
        }
        if market.get('suspend_info'):
            quote['suspend_info'] = text(market['suspend_info'])
        updated = data['updated']
        rows = [
            record(
                'company:profile',
                data['name'],
                'company',
                symbol,
                value=data['name'],
                display_value=data['name'],
                attributes={
                    'company_id': data['id'],
                    'exchange': data['exchange'],
                    'country': data['country'],
                    'sector': data['sector'],
                    'sub_sector': data['sub_sector'],
                    'sub_industry': classification.get('sub_industry'),
                    'listing_board': classification.get('listing_board'),
                    'status': data['status'],
                    'instrument_type': data['type_company'],
                    'tradeable': bool(number(data.get('tradeable', 0))),
                    'indexes': sorted(indexes),
                },
            ),
            record(
                'company:price',
                'Last price',
                'company',
                symbol,
                value=decimal_text(data['price']),
                display_value=data['formatted_price'] or data['price'],
                timestamp=updated,
                missing_reason=None
                if decimal_text(data['price']) is not None
                else 'provider_missing',
                attributes=quote,
            ),
            record(
                'company:previous_close',
                'Previous close',
                'company',
                symbol,
                value=decimal_text(data['previous']),
                display_value=data['previous'],
                timestamp=updated,
            ),
            record(
                'company:change',
                'Price change',
                'company',
                symbol,
                value=decimal_text(data['change']),
                display_value=data['change'],
                timestamp=updated,
            ),
            record(
                'company:change_percent',
                'Price change percent',
                'company',
                symbol,
                value=number(data['percentage']),
                display_value=str(data['percentage']),
                unit='percent',
                timestamp=updated,
            ),
            record(
                'company:volume',
                'Volume',
                'company',
                symbol,
                value=decimal_text(data['volume']),
                display_value=data['volume'],
                unit='shares',
                timestamp=updated,
            ),
        ]
        book = data.get('orderbook') or {}
        for side in ('bid', 'offer'):
            level = book.get(side)
            if isinstance(level, dict):
                rows.append(
                    record(
                        f'company:{side}',
                        f'Best {side}',
                        'company',
                        symbol,
                        value=decimal_text(text(level.get('price'))),
                        display_value=level.get('price'),
                        timestamp=updated,
                        attributes={'volume': decimal_text(text(level.get('volume')))},
                    )
                )
        for row in rows[1:]:
            if row['value'] is None and row['missing_reason'] is None:
                row['missing_reason'] = 'provider_missing'
        return rows, [
            'Quote currency is not stated by the provider; IDX equities trade in IDR.',
            'Quote timestamp is provider time; it is not a publication or filing date.',
        ]
    except (KeyError, TypeError, AttributeError):
        raise SchemaChanged() from None


def price_performance(payload, symbol):
    try:
        rows = []
        for item in payload['data']['prices']:
            timeframe = text(item['timeframe'], allow_empty=False)
            change = item['percentage']
            attrs = {}
            for field in ('close', 'high', 'low'):
                attrs[field] = number(item[field]['raw'])
                attrs[field + '_display'] = text(item[field]['formatted'])
            rows.append(
                record(
                    f'price_performance:{timeframe}',
                    f'Price change {timeframe}',
                    'price_performance',
                    symbol,
                    value=number(change['raw']),
                    display_value=text(change['formatted']),
                    unit='percent',
                    period=timeframe,
                    attributes=attrs,
                )
            )
        return rows
    except (KeyError, TypeError):
        raise SchemaChanged() from None


def analyst_ratings(payload, symbol):
    try:
        data = payload['data']
        target = data['price_target']
        last_updated = text(data['last_updated'])
        counts = {key: number(data[f'total_{key}']) for key in ('buy', 'hold', 'sell', 'analyst')}
        rows = [
            record(
                'analyst:recommendation',
                'Analyst recommendation',
                'analyst',
                symbol,
                value=text(data['recommendation']),
                display_value=text(data['recommendation']),
                attributes={
                    'buy': counts['buy'],
                    'hold': counts['hold'],
                    'sell': counts['sell'],
                    'analysts': counts['analyst'],
                    'last_updated': last_updated,
                },
            ),
            record(
                'analyst:coverage',
                'Analyst coverage',
                'analyst',
                symbol,
                value=counts['analyst'],
                display_value=str(counts['analyst']),
                unit='analysts',
                attributes={'last_updated': last_updated},
            ),
        ]
        for key, label in (
            ('best_target', 'Consensus price target'),
            ('best_low_target', 'Lowest price target'),
            ('best_high_target', 'Highest price target'),
        ):
            value = number(target[key])
            # The provider uses 0 where no target exists; a zero target is not a price.
            rows.append(
                record(
                    f'analyst:{key}',
                    label,
                    'analyst',
                    symbol,
                    value=value if value > 0 else None,
                    display_value=str(value) if value > 0 else None,
                    missing_reason=None if value > 0 else 'provider_missing',
                    attributes={
                        'current_price': number(target['current_price']),
                        'last_updated': last_updated,
                    },
                )
            )
        return rows
    except (KeyError, TypeError):
        raise SchemaChanged() from None


def analyst_consensus(payload, symbol):
    try:
        rows = []
        for group in payload['data']:
            name = text(group['name'], allow_empty=False)
            slug = re.sub(r'[^a-z0-9]+', '_', name.casefold()).strip('_')
            for item in group['items']:
                year, estimate = item['year'], item['is_estimate']
                if type(year) is not int or type(estimate) is not bool:
                    raise SchemaChanged()
                rows.append(
                    display_record(
                        f'analyst:consensus:{slug}:{year}',
                        f'{name} {year} {"estimate" if estimate else "actual"}',
                        'analyst',
                        symbol,
                        text(item['value']),
                        period=str(year),
                        attributes={
                            'metric': name,
                            'is_estimate': estimate,
                            # raw_value was 0 in every observed sample; the display string is used.
                            'provider_raw_value': item.get('raw_value'),
                        },
                    )
                )
        return rows
    except (KeyError, TypeError):
        raise SchemaChanged() from None


def comparison_values(items, labels, symbol, scope):
    rows = []
    for item in items:
        ident = item['fitem_id']
        if type(ident) is not int:
            raise SchemaChanged()
        label, path = labels.get(ident, (f'Comparison metric {ident}', []))
        suffix = '' if scope == 'company' else f' ({scope})'
        rows.append(
            display_record(
                f'comparison:{scope}:{ident}' if scope != 'company' else f'comparison:{ident}',
                label + suffix,
                'comparison',
                symbol if scope == 'company' else None,
                text(item['value']),
                attributes={
                    'provider_metric_id': str(ident),
                    'category_path': path,
                    'scope': scope,
                    'label_source': 'taxonomy' if ident in labels else 'unknown_metric',
                },
            )
        )
    return rows


def peer_comparison(ratios, industries, taxonomy, symbol):
    """Company ratios, then industry and sector aggregates, then peer symbols."""
    labels = metric_labels(taxonomy)
    try:
        if text(ratios['data']['symbol']).upper() != symbol:
            raise SchemaChanged()
        rows = comparison_values(ratios['data']['data_value'], labels, symbol, 'company')
        rows += comparison_values(industries['data']['industry'], labels, symbol, 'industry')
        rows += comparison_values(industries['data']['sector'], labels, symbol, 'sector')
        for peer in industries['data']['competitor']:
            peer_symbol = text(peer['symbol'], allow_empty=False).upper()
            rows.append(
                record(
                    f'comparison:peer:{peer_symbol}',
                    'Industry peer',
                    'comparison',
                    peer_symbol,
                    value=peer_symbol,
                    display_value=peer_symbol,
                    attributes={'scope': 'peer', 'compared_with': symbol},
                )
            )
        return rows
    except (KeyError, TypeError):
        raise SchemaChanged() from None


def fundamental_history(payload, symbol, metric_id):
    """FundaChart points, newest first. Values are provider numbers; suffix hints the unit."""
    try:
        series = None
        for company in payload['data']:
            if text(company['company_name']).upper() != symbol:
                continue
            for ratio in company['ratios']:
                if ratio['item_id'] == metric_id:
                    series = ratio
        if series is None:
            return [], None
        name = text(series['item_name'])
        suffix = text(series.get('suffix', ''))
        unit = 'percent' if suffix == '%' else None
        rows = []
        for point in series['chart_data']:
            date = text(point['formated_date'], allow_empty=False)
            rows.append(
                record(
                    f'fundachart:{metric_id}:{date}',
                    name,
                    'fundachart',
                    symbol,
                    value=number(point['value']),
                    display_value=f'{point["value"]}{suffix}',
                    unit=unit,
                    timestamp=date,
                    attributes={
                        'provider_metric_id': str(metric_id),
                        'source_date_epoch': number(point['date']),
                        'ratio_value': number(point['ratio_value']),
                        'decimal_point': series.get('decimal_point'),
                    },
                )
            )
        rows.reverse()
        return rows, name
    except (KeyError, TypeError):
        raise SchemaChanged() from None


def price_series(payload, symbol, timeframe):
    """LINE chart points, newest first, preceded by the provider's period summary."""
    try:
        data = payload['data']
        if data['chart_type'] != 'PRICE_CHART_TYPE_LINE':
            raise SchemaChanged()
        warnings = [
            'LINE series only: open/high/low/volume are not provided; this is not OHLCV data.',
            'Point timestamps are provider-formatted strings; timezone and adjustment are unverified.',
        ]
        rows, unverified = [], False
        for point in data['prices']:
            date = text(point['formatted_date'], allow_empty=False)
            source_date = text(point['date'])
            if any(point.get(field) for field in ('open', 'high', 'low', 'volume')):
                unverified = True
            rows.append(
                record(
                    f'price:{timeframe}:{date}',
                    'Price',
                    'price',
                    symbol,
                    value=decimal_text(text(point['value'])),
                    display_value=point['value'],
                    timestamp=date,
                    attributes={
                        'source_date_ms': None if source_date in {'', '0'} else source_date,
                        'change': number(point['change']),
                        'change_percent': decimal_text(text(point['percentage'])),
                        'timeframe': timeframe,
                        'resolution': blank_to_none(data.get('xaxisopt')),
                    },
                )
            )
        for row in rows:
            if row['value'] is None:
                row['missing_reason'] = 'provider_missing'
        rows.reverse()
        if unverified:
            warnings.append('Provider returned OHLCV-like fields; they are unverified and omitted.')
        summary = record(
            f'price:{timeframe}:summary',
            f'Price change over {timeframe}',
            'price',
            symbol,
            value=decimal_text(text(data['percentage'])),
            display_value=data['percentage'],
            unit='percent',
            period=timeframe,
            attributes={
                'change': number(data['change']),
                'cagr_percent': decimal_text(text(data.get('cagr', ''))),
                'previous': number(data['previous']) if data.get('previous') is not None else None,
                'points': len(rows),
                'first_point': rows[-1]['timestamp'] if rows else None,
                'last_point': rows[0]['timestamp'] if rows else None,
            },
        )
        if summary['value'] is None:
            summary['missing_reason'] = 'provider_missing'
        return [summary, *rows], warnings
    except (KeyError, TypeError):
        raise SchemaChanged() from None


def screen_results(payload):
    """One record per company; each rule metric keeps raw and display values."""
    try:
        data = payload['data']
        rows = []
        for entry in data['calcs']:
            company = entry['company']
            symbol = text(company['symbol'], allow_empty=False).upper()
            metrics = []
            for result in entry['results']:
                ident = result['id']
                if type(ident) is not int:
                    raise SchemaChanged()
                metrics.append(
                    {
                        'provider_metric_id': str(ident),
                        'label': text(result['item']),
                        'value': decimal_text(text(result['raw'])),
                        'display_value': text(result['display']),
                    }
                )
            rows.append(
                record(
                    f'screener:company:{symbol}',
                    text(company['name']),
                    'screener',
                    symbol,
                    value=symbol,
                    display_value=text(company['name']),
                    attributes={
                        'company_id': text(company['id']),
                        'exchange': company.get('exchange'),
                        'country': company.get('country'),
                        'metrics': metrics,
                    },
                )
            )
        page, per_page, total = data['curpage'], data['perpage'], data['totalrows']
        for value in (page, per_page, total):
            if type(value) is not int:
                raise SchemaChanged()
        return rows, {'page': page, 'per_page': per_page, 'total': total}
    except (KeyError, TypeError):
        raise SchemaChanged() from None
