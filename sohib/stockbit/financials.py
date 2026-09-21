"""Financial statement HTML report parsing. The provider's structured tables arrive empty."""

import re
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

from .contracts import REPORT_TYPES, record
from .normalize import SchemaChanged, display_number, text

REPORT_NAMES = {code: name for name, code in REPORT_TYPES.items()}
DIGITS = re.compile(r'-?\d+(\.\d+)?')


class ReportParser(HTMLParser):
    """Collect tables, period headers, rows and cells with their data attributes."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = self.row = self.cell = None
        self.in_head = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table':
            self.table = {'attrs': attrs, 'periods': [], 'rows': []}
            self.tables.append(self.table)
        elif tag == 'thead':
            self.in_head = True
        elif tag == 'tr' and self.table is not None and not self.in_head:
            self.row = {'attrs': attrs, 'cells': []}
            self.table['rows'].append(self.row)
        elif tag == 'th' and self.in_head and self.table is not None:
            self.cell = {'attrs': attrs, 'text': [], 'names': [], 'icons': []}
            self.table['periods'].append(self.cell)
        elif tag == 'td' and self.row is not None:
            self.cell = {'attrs': attrs, 'text': [], 'names': [], 'icons': []}
            self.row['cells'].append(self.cell)
        elif tag == 'span' and self.cell is not None and 'acc-name' in (attrs.get('class') or ''):
            self.cell['names'].append(attrs)
        elif tag in {'i', 'em'} and self.cell is not None and 'data-acc-number' in attrs:
            self.cell['icons'].append(attrs)

    def handle_endtag(self, tag):
        if tag == 'thead':
            self.in_head = False
        elif tag in {'td', 'th'}:
            self.cell = None
        elif tag == 'tr':
            self.row = None
        elif tag == 'table':
            self.table = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell['text'].append(data)


def cell_text(cell):
    return ''.join(cell['text']).replace('\xa0', ' ').strip()


def classes(attrs):
    return set((attrs.get('class') or '').split())


def parse_report(payload):
    """Return (currency, tables) where each table has periods and typed rows."""
    try:
        data = payload['data']
        report = text(data['html_report'])
        tables = data['data_tables']
        if not report:
            raise SchemaChanged()
        if tables.get('accounts') or tables.get('periods'):
            # Structured tables were always empty in evidence; a populated shape is unverified.
            raise SchemaChanged()
        currency = text(data['default_currency']) or None
        selected = re.search(r'name="selected_currency"[^>]*value="([a-z]{3})"', report)
        if selected:
            currency = selected.group(1).upper()
    except (KeyError, TypeError, AttributeError):
        raise SchemaChanged() from None
    parser = ReportParser()
    parser.feed(report)
    parser.close()
    parsed = []
    for index, table in enumerate(parser.tables):
        periods = [
            {'label': cell_text(cell), 'code': cell['attrs'].get('data-label') or cell_text(cell)}
            for cell in table['periods']
            if 'periods-list' in classes(cell['attrs'])
        ]
        if not periods or any(not period['label'] for period in periods):
            raise SchemaChanged()
        formula = 'ratio-table' in (table['attrs'].get('class') or '')
        rows, heads = [], {}
        for position, row in enumerate(table['rows']):
            if len(row['cells']) != len(periods) + 1:
                raise SchemaChanged()
            rows.append(describe_row(row, position, formula, heads))
        parsed.append({'index': index, 'periods': periods, 'rows': rows, 'formula': formula})
    if not parsed:
        raise SchemaChanged()
    return currency, parsed


def describe_row(row, position, formula, heads):
    head, cells = row['cells'][0], row['cells'][1:]
    row_classes = classes(row['attrs'])
    kind = (
        'formula'
        if formula
        else 'total'
        if 'total' in row_classes
        else 'others'
        if 'other' in row_classes
        else 'account'
    )
    names = head['names'][0] if head['names'] else {}
    name_en = (names.get('data-lang-1-full') or names.get('data-lang-1') or '').strip()
    name_id = (names.get('data-lang-0-full') or names.get('data-lang-0') or '').strip()
    label = name_en or name_id or cell_text(head)
    if kind == 'total':
        label = 'Total ' + (name_en or name_id or cell_text(head).removeprefix('Total').strip())
    elif kind == 'others':
        label = 'Others'
    if not label:
        raise SchemaChanged()
    icons = head['icons'][0] if head['icons'] else {}
    account = icons.get('data-acc-number')
    confidence = 'account_number'
    if not account:
        account, confidence = f'row{position}', 'row_position'
    left, right = row['attrs'].get('data-left'), row['attrs'].get('data-right')
    parent = None
    if kind == 'account' and right:
        heads[right] = (account, label)
    elif left in heads and kind != 'account':
        parent = heads[left]
        if kind == 'total' and not (name_en or name_id):
            label = 'Total ' + parent[1]
    return {
        'kind': kind,
        'account': account,
        'label': label,
        'name_en': name_en or None,
        'name_id': name_id or None,
        'identity_confidence': confidence,
        'parent_account': parent[0] if parent else None,
        'collapsed_by_default': 'hides' in row_classes,
        'cells': cells,
    }


def raw_value(value):
    """Provider numeric attribute; markers and unparsable text stay None, never zero."""
    if (
        not isinstance(value, str)
        or value.strip() in {'', '-'}
        or not DIGITS.fullmatch(value.strip())
    ):
        return None
    try:
        return float(Decimal(value.strip()))
    except InvalidOperation:
        return None


def account_key(report_code, row):
    return f'financials:{REPORT_NAMES[report_code]}:{row["kind"]}:{row["account"]}'


def row_attributes(row, table):
    return {
        'report_type': None,
        'row_kind': row['kind'],
        'account_number': row['account']
        if row['identity_confidence'] == 'account_number'
        else None,
        'identity_confidence': row['identity_confidence'],
        'name_en': row['name_en'],
        'name_id': row['name_id'],
        'parent_account': row['parent_account'],
        'collapsed_by_default': row['collapsed_by_default'],
        'table_index': table['index'],
    }


def financial_accounts(payload, symbol, report_code):
    """Metadata-only rows for list_metrics(namespace=financials)."""
    _, tables = parse_report(payload)
    rows = []
    for table in tables:
        for row in table['rows']:
            attrs = row_attributes(row, table)
            attrs.update(
                report_type=REPORT_NAMES[report_code],
                periods_available=len(table['periods']),
                latest_period=table['periods'][-1]['label'],
            )
            rows.append(
                record(
                    account_key(report_code, row),
                    row['label'],
                    'financials',
                    symbol,
                    missing_reason='metadata_only',
                    attributes=attrs,
                )
            )
    return rows


def financial_statements(payload, symbol, report_code, periods):
    """Account x period cells for the most recent `periods` columns, newest period first."""
    currency, tables = parse_report(payload)
    rows, notes = [], []
    for table in tables:
        chosen = list(enumerate(table['periods']))[-periods:]
        chosen.reverse()
        for row in table['rows']:
            for index, period in chosen:
                cell = row['cells'][index]
                attrs = cell['attrs']
                raw = attrs.get('data-raw')
                value = raw_value(raw)
                display = cell_text(cell) or raw or None
                missing = None
                if value is None:
                    missing = 'provider_missing' if raw in (None, '', '-') else 'provider_unparsed'
                unit, currency_code = 'base_units', currency
                if row['kind'] == 'formula':
                    # Ratio rows are unitless or percentages; the display string decides.
                    _, unit, _, _ = display_number(display) if display else (None,) * 4
                    currency_code = None
                attributes = row_attributes(row, table)
                attributes.update(
                    report_type=REPORT_NAMES[report_code],
                    period_code=period['code'],
                    value_idr=raw_value(attrs.get('data-value-idr')) if value is not None else None,
                    value_usd=raw_value(attrs.get('data-value-usd')) if value is not None else None,
                    common_size_percent=raw_value(attrs.get('data-percentage'))
                    if row['kind'] != 'formula' and value is not None
                    else None,
                )
                rows.append(
                    record(
                        f'{account_key(report_code, row)}:{period["code"]}',
                        row['label'],
                        'financials',
                        symbol,
                        value=value,
                        display_value=display,
                        unit=unit if value is not None else None,
                        currency=currency_code if value is not None else None,
                        period=period['label'],
                        missing_reason=missing,
                        attributes=attributes,
                    )
                )
    notes.append(
        'Values are provider raw base-currency units (verified equal to data-value-idr); '
        'the report header "In Million" describes the web display, not these numbers.'
    )
    notes.append(
        'Period labels are statement periods, not publication dates; restatements are not tracked.'
    )
    return rows, notes
