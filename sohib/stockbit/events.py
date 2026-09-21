"""Corporate action and calendar normalization. Event dates stay separate, never flattened."""

import re

from .contracts import record
from .normalize import SchemaChanged, blank_to_none, decimal_text, text

PRIVATE = re.compile(r'hash|lock|iqp|icon|_url$')


def currency_code(value):
    if not value:
        return None
    value = text(value)
    return value.removeprefix('CURRENCY_') or None


def date(info, field):
    value = info.get(field)
    if value is None:
        return None
    value = text(value).strip()
    if not value or value.startswith('0001-01-01'):
        return None
    return value


def public_fields(info):
    """Scalar provider fields minus hashes, locks, internal ids and asset links."""
    return {
        key: value
        for key, value in info.items()
        if isinstance(value, str | int | float | bool)
        and not isinstance(value, bool)
        and not PRIVATE.search(key)
        and value not in ('', None)
    }


def dividend(info, namespace, symbol):
    formatted = blank_to_none(info.get('dividend_value_formatted'))
    value = decimal_text(text(info.get('dividend_value', '')))
    fiscal_year = info.get('dividend_fiscal_year')
    adjusted = info.get('dividend_value_adjusted')
    return record(
        f'{namespace}:dividend:{text(info["dividend_id"], allow_empty=False)}',
        f'Cash dividend {formatted}' if formatted else 'Cash dividend',
        namespace,
        symbol,
        value=value,
        display_value=formatted or blank_to_none(info.get('dividend_value')),
        currency=currency_code(info.get('dividend_currency')) if value is not None else None,
        missing_reason=None if value is not None else 'provider_missing',
        attributes={
            'event_type': 'dividend',
            'cum_date': date(info, 'dividend_cumdate'),
            'ex_date': date(info, 'dividend_exdate'),
            'record_date': date(info, 'dividend_recdate'),
            'payment_date': date(info, 'dividend_paydate'),
            'announced': date(info, 'dividend_created'),
            'last_update': date(info, 'dividend_lastupdate'),
            'fiscal_year': fiscal_year if isinstance(fiscal_year, int) and fiscal_year else None,
            'adjusted_value': adjusted if isinstance(adjusted, int | float) and adjusted else None,
            'active': bool(info.get('corp_action_active')),
            'last_price': decimal_text(text(info.get('lastprice', ''))),
            'note': blank_to_none(info.get('event_note')),
        },
    )


def rups(info, namespace, symbol):
    attributes = {
        'event_type': 'rups',
        'meeting_date': date(info, 'rups_date'),
        'meeting_time': blank_to_none(info.get('rups_time')),
        'venue': blank_to_none(info.get('rups_venue')),
        'eligible_date': date(info, 'rups_eligible_date'),
        'announced': date(info, 'rups_created'),
        'active': bool(info.get('corp_action_active')),
    }
    for field in ('rups_iqp_agenda', 'rups_iqp_result', 'rups_iqp_remark'):
        if info.get(field):
            attributes[field.removeprefix('rups_iqp_')] = text(info[field])
    return record(
        f'{namespace}:rups:{text(info["rups_id"], allow_empty=False)}:{attributes["meeting_date"]}',
        'Shareholder meeting (RUPS)',
        namespace,
        symbol,
        value=attributes['meeting_date'],
        display_value=attributes['meeting_date'],
        attributes=attributes,
    )


def tender_offer(info, namespace, symbol):
    price = decimal_text(text(info.get('tender_price', '')))
    return record(
        f'{namespace}:tenderoffer:{text(info["tender_id"], allow_empty=False)}',
        'Tender offer',
        namespace,
        symbol,
        value=price,
        display_value=blank_to_none(info.get('tender_price_formatted'))
        or blank_to_none(info.get('tender_price')),
        missing_reason=None if price is not None else 'provider_missing',
        attributes={
            'event_type': 'tenderoffer',
            'start_date': date(info, 'tender_start'),
            'end_date': date(info, 'tender_end'),
            'payment_date': date(info, 'tender_paydate'),
            'percentage': decimal_text(text(info.get('tender_percentage', ''))),
            'shares': decimal_text(text(info.get('tender_shares', ''))),
            'announced': date(info, 'tender_created'),
            'active': bool(info.get('corp_action_active')),
            'note': blank_to_none(info.get('event_note')),
        },
    )


def stock_split(info, namespace, symbol):
    old, new = blank_to_none(info.get('stocksplit_old')), blank_to_none(info.get('stocksplit_new'))
    factor = decimal_text(text(info.get('stocksplit_factor', '')))
    return record(
        f'{namespace}:stocksplit:{text(info["stocksplit_id"], allow_empty=False)}',
        f'Stock split {old}:{new}' if old and new else 'Stock split',
        namespace,
        symbol,
        value=factor,
        display_value=f'{old}:{new}' if old and new else None,
        missing_reason=None if factor is not None else 'provider_missing',
        attributes={
            'event_type': 'stocksplit',
            'cum_date': date(info, 'stocksplit_cumdate'),
            'ex_date': date(info, 'stocksplit_exdate'),
            'record_date': date(info, 'stocksplit_recdate'),
            'old_shares': old,
            'new_shares': new,
            'new_price': info.get('stocksplit_new_price')
            if isinstance(info.get('stocksplit_new_price'), int | float)
            else None,
            'shares_after': info.get('stocksplit_new_share')
            if isinstance(info.get('stocksplit_new_share'), int | float)
            else None,
            'announced': date(info, 'stocksplit_created'),
            'active': bool(info.get('corp_action_active')),
            'note': blank_to_none(info.get('event_note')),
        },
    )


def public_expose(info, namespace, symbol):
    return record(
        f'{namespace}:pubex:{text(info["puexp_id"], allow_empty=False)}',
        'Public expose',
        namespace,
        symbol,
        value=date(info, 'puexp_date'),
        display_value=date(info, 'puexp_date'),
        attributes={
            'event_type': 'pubex',
            'date': date(info, 'puexp_date'),
            'time': blank_to_none(info.get('puexp_time')),
            'venue': blank_to_none(info.get('puexp_venue')),
            'active': bool(info.get('corp_action_active')),
        },
    )


def unknown_event(kind, info, namespace, symbol):
    fields = public_fields(info)
    ident = next((str(v) for k, v in fields.items() if k.endswith('_id')), None) or str(
        abs(hash(tuple(sorted(fields.items()))))
    )
    return record(
        f'{namespace}:{kind}:{ident}',
        f'{kind} event (unverified type)',
        namespace,
        symbol,
        attributes={'event_type': kind, 'verified_shape': False, **fields},
    )


BUILDERS = {
    'dividend': dividend,
    'rups': rups,
    'tenderoffer': tender_offer,
    'tender': tender_offer,
    'stocksplit': stock_split,
    'pubex': public_expose,
}


def build(kind, info, namespace, symbol, warnings):
    if not isinstance(info, dict):
        raise SchemaChanged()
    builder = BUILDERS.get(kind)
    if builder is None:
        note = f'Unverified event type "{kind}"; public provider fields retained as-is.'
        if note not in warnings:
            warnings.append(note)
        return unknown_event(kind, info, namespace, symbol)
    try:
        return builder(info, namespace, symbol)
    except (KeyError, TypeError):
        raise SchemaChanged() from None


def corporate_actions(payload, symbol):
    warnings = []
    try:
        rows = []
        for item in payload['data']:
            kind = text(item['action_type'], allow_empty=False)
            info = item['action_info'][kind]
            event_symbol = info.get('company_symbol')
            if isinstance(event_symbol, str) and event_symbol and event_symbol.upper() != symbol:
                raise SchemaChanged()
            rows.append(build(kind, info, 'corpaction', symbol, warnings))
        return rows, warnings
    except (KeyError, TypeError):
        raise SchemaChanged() from None


def stock_conversions(payload, symbol):
    warnings = []
    try:
        conversions = payload['data']['conversion']
        if not isinstance(conversions, list):
            raise SchemaChanged()
        rows = [
            build('stock_conversion', info, 'corpaction', symbol, warnings) for info in conversions
        ]
        return rows, warnings
    except (KeyError, TypeError):
        raise SchemaChanged() from None


def dividend_calendar(payload):
    try:
        data = payload['data']
        rows = []
        for info in data['dividend']:
            symbol = text(info['company_symbol'], allow_empty=False).upper()
            rows.append(build('dividend', info, 'calendar', symbol, []))
        return rows, blank_to_none(data.get('today'))
    except (KeyError, TypeError):
        raise SchemaChanged() from None


def calendar_today(payload):
    """Every category the provider lists for today; dividends are covered by the calendar."""
    warnings = []
    try:
        data = payload['data']
        rows = []
        for category, items in data.items():
            if category in {'today', 'dividend'} or not isinstance(items, list):
                continue
            for info in items:
                symbol = text(info['company_symbol'], allow_empty=False).upper()
                rows.append(build(category, info, 'calendar', symbol, warnings))
        return rows, blank_to_none(data.get('today')), warnings
    except (KeyError, TypeError):
        raise SchemaChanged() from None
