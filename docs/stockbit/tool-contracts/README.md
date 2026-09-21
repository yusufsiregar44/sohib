# Stockbit research tool contracts

Version 1.1.0 (19 September 2026). All thirteen contracts are implemented in browser mode over the
in-page fetch transport ([ADR 006](../../decisions/006-in-page-fetch-transport.md)) and were each
live-verified once; see [ADR 006](../../decisions/006-in-page-fetch-transport.md) and the
[verification summary](../stockbit-evidence/fetch-transport-2026-09-19/README.md). Fixture and
disabled modes expose only the first three. Input schemas are generated from the runtime definitions
in `sohib/stockbit/contracts.py`; regenerate them when the definitions change. Company routes use
`{symbol}`; fixture symbols are examples.

## Registry

- `search_companies`: resolve symbol/name queries to equity candidates; see [company search](../company-search.md).
- `list_metrics`: metric discovery; symbol required for keystats and financials, `symbol=null` for screener, fundachart and comparison.
- `get_key_statistics`: grouped current company metrics.
- `get_company_summary`: identity, classification and last quote; account flags stripped.
- `get_financial_statements`: account x period cells from the HTML report; quarterly, annual or ttm; balance_sheet + ttm rejected.
- `get_fundamental_history`: FundaChart series for one metric; timeframes 1y, 3y, 5y, 10y; newest first, 40 per page.
- `get_price_series`: LINE price points only, newest first with a summary record; ten verified timeframes. OHLCV unavailable.
- `get_price_performance`: change, high and low per provider window.
- `get_analyst_consensus`: recommendation counts, price targets, yearly estimates.
- `get_peer_comparison`: company ratios with industry and sector aggregates and peer symbols.
- `get_corporate_actions`: company events with separate cum/ex/record/payment dates; `complete=null`.
- `get_dividend_calendar`: market-wide dividends plus today's other events.
- `screen_equities`: unsaved IHSG screen; basic rules only; sorted by the first rule metric (verified); one provider page of 25 per call. Known open issue: returned `SCHEMA_CHANGED` for symbols IFSH and PNGO during acceptance testing on 20 September 2026 (clean typed-error failure, no records returned); root cause not yet investigated.

## Common normalization contract

- Use output.schema.json for the shared envelope. Each record is a metric, financial account-period cell, screener company, series point or corporate event. Preserve provider-specific event fields in attributes; do not flatten cum/ex/record/payment dates into a single timestamp.
- Metric keys include endpoint namespace and ID. Financial account keys include report type and account number; when absent, use a stable provider path plus label and mark identity confidence in attributes.
- Parse percentages into percentage points with unit=percent; preserve display_value. Parse B using an explicit scale of 1e9 only where the provider display establishes that unit. Parentheses denote negative values. Blank, dash and HTML empty cells become null with missing_reason, never zero.
- Financials: prefer structured tables when nonempty; otherwise parse html_report. Preserve bilingual names, hierarchy and period headers. Reconcile HTML units against rounding metadata and displayed cells before returning numbers. Reject balance-sheet TTM. Apply sort locally to period columns.
- Price series: only line format is allowed. Preserve source date and formatted_date in attributes; date=0 is not a valid market timestamp. Unknown timezone stays explicit. Never manufacture OHLCV or adjusted prices.
- Corporate events retain provider event type and source identifier. Unknown event variants must remain available as typed unknown records with raw public fields, or return SCHEMA_CHANGED if parsing would lose meaning.
- Screener: validate IDs against screener namespace; force IHSG, save="0", screenerid="0", type=TEMPLATE_TYPE_CUSTOM. Serialize universe and filters as JSON strings; sequence as metric IDs. Basic rules only initially. Comparison rules and alternate universes stay out of v1 until tested. No save/delete/favorite actions.
- Screen pagination returns one requested page. Do not infer completeness without total/next-page evidence. Corporate-action limit=30 is bounded coverage; complete=null. Return partial for truncation or incomplete parsing.
- Never substitute retrieval time for data-as-of or publication time. Null means unknown. Store fetched_at in UTC; preserve original timestamps in attributes. Current fundamentals are not a point-in-time backtest dataset.
- Errors have status=error, records=[], nonnull error. Success has error=null. Empty valid results are ok with records=[], not fabricated data. Validate these semantic rules in addition to JSON Schema.

## Authentication and operational behavior

See [authentication.md](authentication.md). Provider session secrets are never tool inputs or outputs. Runtime limits in contracts are proposed harness defaults, not Stockbit service limits. Retry transient transport errors/5xx with bounded exponential backoff and jitter; honor Retry-After for 429. No retry loop for 403 or interactive challenges. Stop on schema changes. Cache by symbol, arguments, source entitlement and schema version; never treat stale cache as fresh without an explicit warning.

## Fixture and activation checks

- Contracts reference descriptive verification notes. Provider captures stay local; bundled examples are synthetic and do not establish current upstream behavior.
- Verify metric namespaces, missing markers, negative values, percentages, unit conversions, all financial statement types, empty structured-table fallback and event variants.
- Verify screening never sends save=1; validate page transitions and first-metric sort mapping before enabling it.
- Verify session expiry, redirect-to-login, HTML returned instead of JSON, 401/403/429, network timeout and malformed responses without logging secrets.
- Required activation gates: credentials/session provisioning; fixture-to-schema adapter tests; one authorized live smoke test per capability; freshness/coverage labels; secret-redaction tests. No trade execution tool is included.
