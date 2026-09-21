# Stockbit API catalogue

Incremental research catalogue for SohiB. Updated: 2026-09-17.

Scope: fundamental investing, swing research, intraday/interday prices, corporate actions and screening. These are observed Stockbit web-app interfaces, not a confirmed public developer API contract. Base URL: `https://exodus.stockbit.com`. Authentication, entitlements, limits and permitted automated use require separate validation. No credentials are included.

## Status legend

- **Verified response**: an HTTP 200 JSON response was captured during this investigation; only the listed examples were exercised.
- **Source only**: route found in Stockbit-delivered frontend JavaScript; successful response and parameter semantics remain unverified.
- Empty results are explicitly marked. Verified does not imply complete history, live data, or production readiness.

## Verified endpoints

1. **`GET /emitten/{symbol}/info` — Verified response**
   - Company identity and quote summary. Example: with_sub_industry=true. Account-specific flags must be discarded.
   - Observed request: `https://exodus.stockbit.com/emitten/MAPI/info?with_sub_industry=true`

2. **`GET /charts/{symbol}/daily` — Verified response**
   - Intraday and multi-year LINE data verified with timeframe=today and 5y. Sample open/high/low/volume fields are empty: do not treat this as validated OHLCV. Intraday date can be "0"; formatted_date carries time. Timezone and adjustment semantics remain unverified.
   - Observed request: `https://exodus.stockbit.com/charts/MAPI/daily?timeframe=today`

3. **`GET /company-price-feed/price-performance/{symbol}` — Verified response**
   - Price performance across periods.
   - Observed request: `https://exodus.stockbit.com/company-price-feed/price-performance/MAPI`

4. **`GET /keystats/ratio/v1/{symbol}` — Verified response**
   - Grouped valuation, profitability, growth and balance-sheet metrics; year_limit=10 observed. Values include formatted strings, percentages and missing markers.
   - Observed request: `https://exodus.stockbit.com/keystats/ratio/v1/MAPI?year_limit=10`

5. **`GET /findata-view/company/financial` — Verified response**
   - symbol=MAPI, data_type=1. report_type: 1 income statement, 2 balance sheet, 3 cash flow. statement_type=1 quarterly verified for all three; statement_type=2 annual verified for cash flow. Structured data_tables and HTML report. Normalize currency and units before calculations.
   - Observed request: `https://exodus.stockbit.com/findata-view/company/financial?symbol=MAPI&data_type=1&report_type=1&statement_type=1`

6. **`GET /corpaction/{symbol}/stock_conversion` — Verified response**
   - page=1, limit=50. Verified EMPTY conversion array for MAPI; nonempty schema unknown.
   - Observed request: `https://exodus.stockbit.com/corpaction/MAPI/stock_conversion?page=1&limit=50`

7. **`GET /corpaction/{symbol}` — Verified response**
   - limit=30. Observed dividend, RUPS, tender-offer and stock-split variants in action_type/action_info. Preserve cum/ex/record/payment dates separately. Full history/pagination unknown.
   - Observed request: `https://exodus.stockbit.com/corpaction/MAPI?limit=30`

8. **`GET /fundachart/templates` — Verified response**
   - Built-in and potentially personal chart templates. Exclude personal templates from default research tools.
   - Observed request: `https://exodus.stockbit.com/fundachart/templates`

9. **`GET /fundachart/metrics` — Verified response**
   - metric_name=fundachart. Hierarchical metric IDs and labels.
   - Observed request: `https://exodus.stockbit.com/fundachart/metrics?metric_name=fundachart`

10. **`GET /fundachart` — Verified response**
   - item=2661 (price) and 2891 (PE TTM), companies=MAPI, timeframe=1y verified. Historical metric series; publication-time availability unknown.
   - Observed request: `https://exodus.stockbit.com/fundachart?item=2661&companies=MAPI&timeframe=1y`

11. **`GET /screener/preset` — Verified response**
   - Built-in preset categories.
   - Observed request: `https://exodus.stockbit.com/screener/preset`

12. **`GET /screener/metric` — Verified response**
   - Metric taxonomy. Preserve endpoint namespace with IDs; do not assume all services use identical IDs.
   - Observed request: `https://exodus.stockbit.com/screener/metric`

13. **`GET /screener/universe` — Verified response**
   - Universe/index/sector metadata; response can also contain private watchlists. Strip watchlists for generic research.
   - Observed request: `https://exodus.stockbit.com/screener/universe`

14. **`GET /screener/templates/{id}` — Verified response**
   - id=29, type=TEMPLATE_TYPE_GURU: PE Undervalued preset; result includes columns, rules, companies, raw/display values and pagination.
   - Observed request: `https://exodus.stockbit.com/screener/templates/29?type=TEMPLATE_TYPE_GURU`

15. **`POST /screener/templates` — Verified response**
   - POST used to execute an UNSAVED screen with save="0", screenerid="0", type=TEMPLATE_TYPE_CUSTOM. Enforce these constants in the adapter. Body includes name, description, ordertype, ordercol, page, universe, filters, sequence. universe and filters are JSON-encoded strings. Result: 25 of 91 rows in tested query. Never expose save/favourite/delete mutations as research tools.
   - Observed request: `https://exodus.stockbit.com/screener/templates`

16. **`GET /analyst-ratings/{symbol}` — Verified response**
   - Analyst rating summary.
   - Observed request: `https://exodus.stockbit.com/analyst-ratings/MAPI`

17. **`GET /analyst-ratings/{symbol}/consensus` — Verified response**
   - Consensus forecasts/estimates. Coverage and estimate dates should accompany values.
   - Observed request: `https://exodus.stockbit.com/analyst-ratings/MAPI/consensus`

18. **`GET /comparison/metrics` — Verified response**
   - Peer comparison metric taxonomy.
   - Observed request: `https://exodus.stockbit.com/comparison/metrics`

19. **`GET /comparison/{symbol}/templates` — Verified response**
   - Verified EMPTY personal template list. Not needed for core research.
   - Observed request: `https://exodus.stockbit.com/comparison/MAPI/templates`

20. **`GET /comparison/{symbol}/industries` — Verified response**
   - Industry peers/universe.
   - Observed request: `https://exodus.stockbit.com/comparison/MAPI/industries`

21. **`GET /comparison/{symbol}/ratios` — Verified response**
   - Peer ratios verified for MAPI, ERAA, IMAS and TURI.
   - Observed request: `https://exodus.stockbit.com/comparison/MAPI/ratios`

22. **`GET /order-trade/broker/top` — Verified response**
   - Observed sort=TB_SORT_BY_TOTAL_VALUE, order=ORDER_BY_DESC, period=TB_PERIOD_LAST_1_DAY, market_type=MARKET_TYPE_ALL, eod_only=true. Broker activity research; not order execution.
   - Observed request: `https://exodus.stockbit.com/order-trade/broker/top?sort=TB_SORT_BY_TOTAL_VALUE&order=ORDER_BY_DESC&period=TB_PERIOD_LAST_1_DAY&market_type=MARKET_TYPE_ALL&eod_only=true`

23. **`GET /corpaction` — Verified response**
   - Market-wide current calendar response. Historical/date range semantics not established.
   - Observed request: `https://exodus.stockbit.com/corpaction`

24. **`GET /corpaction/dividend` — Verified response**
   - Market-wide dividend calendar. Other category routes remain source-only below.
   - Observed request: `https://exodus.stockbit.com/corpaction/dividend`

## Source-only endpoints awaiting response validation

1. **`GET /emitten/{symbol}/profile` — Source only**
   - Company profile; parameters unverified.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

2. **`GET /emitten/{symbol}/contact` — Source only**
   - Company contact information.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

3. **`GET /company-price-feed/seasonality/{symbol}` — Source only**
   - Seasonality; year, back_year.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

4. **`GET /insider/company/majorholder` — Source only**
   - Major-holder changes; insider, symbol, date_start, date_end, page.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

5. **`GET /insider/shareholding/composition/companies/{symbol}` — Source only**
   - Ownership composition; period_start, period_end.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

6. **`GET /emitten-metadata/subsidiary/{symbol}` — Source only**
   - Subsidiary information.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

7. **`GET /earnings` — Source only**
   - Earnings discovery; filter, search, quarter, year, sort_column, order, page.
   - Source: [Stockbit frontend bundle 9](https://stockbit.com/_next/static/chunks/70453.7c813676bd60c94e.js).

8. **`GET /chartbit/{symbol}/price/daily` — Source only**
   - Candidate daily OHLCV route; from, to, limit; frontend sets limit=0 when both boundaries supplied. Units and limits unverified; may be legacy.
   - Source: [Stockbit frontend bundle 5](https://stockbit.com/_next/static/chunks/90330-f15effadf67c3d39.js).

9. **`GET /chartbit/{symbol}/price/intraday` — Source only**
   - Candidate intraday OHLCV route; from, to, limit plus forwarded options. Resolution enum, retention and timestamps unverified; may be legacy.
   - Source: [Stockbit frontend bundle 5](https://stockbit.com/_next/static/chunks/90330-f15effadf67c3d39.js).

10. **`GET /chartbit/initial/{symbol}` — Source only**
   - Chart initialization/metadata; schema unverified.
   - Source: [Stockbit frontend bundle 5](https://stockbit.com/_next/static/chunks/90330-f15effadf67c3d39.js).

11. **`GET /chartbit/chart/corpaction` — Source only**
   - Chart event annotations; from, to, symbol.
   - Source: [Stockbit frontend bundle 5](https://stockbit.com/_next/static/chunks/90330-f15effadf67c3d39.js).

12. **`GET /company-price-feed/prices/close` — Source only**
   - Close-price lookup; interval=1 and symbol, with repeated-array serialization.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

13. **`GET /company-price-feed/prices/{symbol}/market` — Source only**
   - Market-board prices; date and boards.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

14. **`GET /company-price-feed/v2/orderbook/companies/{symbol}` — Source only**
   - Order-book snapshot candidate; not a historical candle feed.
   - Source: [Stockbit frontend bundle 56](https://stockbit.com/_next/static/chunks/47038-c9fb4b031eb29e7c.js).

15. **`GET /order-trade/trade-book` — Source only**
   - Trade-book research; parameters forwarded, not yet validated.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

16. **`GET /order-trade/running-trade` — Source only**
   - Trade tape; parameters forwarded, not yet validated.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

17. **`GET /order-trade/running-trade/group` — Source only**
   - Grouped trade tape; schema unverified.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

18. **`GET /marketdetectors/{symbol}` — Source only**
   - Broker/flow analysis; parameters forwarded.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

19. **`GET /findata-view/marketdetectors/brokers` — Source only**
   - Broker reference metadata.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

20. **`GET /order-trade/broker/activity` — Source only**
   - Broker activity; array query serialization in source.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

21. **`GET /emitten/hotlist/{category}` — Source only**
   - Observed source categories topgainer, toploser, mostactive; limit=10.
   - Source: [Stockbit frontend bundle 63](https://stockbit.com/_next/static/chunks/46906-648a1f0b8bfc4e30.js).

22. **`GET /corpaction/{category}` — Source only**
   - Source categories: bonus, economic, ipo, pubex, reversesplit, rightissue, rups, stock_dividend, stocksplit, tenderoffer, warrant. dividend is separately verified. Optional symbol filter; response schemas/date ranges unverified.
   - Source: [Stockbit frontend bundle 100](https://stockbit.com/_next/static/chunks/50333-c2de2f5b805a298f.js).

## Integration details confirmed in the UI

- Financial statement UI additionally lists TTM=3, interim YTD=4, Q1–Q4=5–8, QoQ growth=9, quarter YoY=10, YTD YoY=11, annual YoY=12, 3-year CAGR=13. These modes were not all requested and validated.
- Screener comparator options: `>`, `<`, `<=`, `=`, `>=`. Tested rules: PE TTM below its minus-one-standard-deviation 3-year value; PE > 0; volume MA20 > 500000; net income TTM > 0.
- Screener page states technical data refreshes every 15 minutes and fundamental data at 18:30; timezone was not explicitly confirmed. Do not describe this as tick-level screening.
- Metric IDs must be namespaced: for example net income TTM differs between Keystats and Screener.
- Preserve both raw values and display strings. Missing values must not become zero. Store source, fetched_at, market/as-of time, currency, unit and adjustment status.
- Statement period end is not the publication timestamp. Point-in-time history, restatements and survivorship handling remain unverified.

## Harness tools (implemented 19 September 2026)

Implemented in browser mode over the in-page fetch transport and live-verified; see
[tool contracts](tool-contracts/README.md) and [ADR 006](../decisions/006-in-page-fetch-transport.md).

- `get_company_summary(symbol)` → `/emitten/{symbol}/info`.
- `get_key_statistics(symbol, query, page)` → Keystats.
- `get_financial_statements(symbol, report_type, period_mode, periods, query, page)` → HTML report cells.
- `list_metrics(namespace, symbol, query, page)` → Screener, FundaChart, Comparison, Keystats or Financials labels.
- `get_fundamental_history(symbol, metric_id, timeframe, page)` → FundaChart (1y, 3y, 5y, 10y).
- `get_price_series(symbol, timeframe, page)` → verified LINE series; explicitly not an OHLCV tool.
- `get_price_performance(symbol)` → performance summary.
- `get_analyst_consensus(symbol, query, page)` → ratings and consensus.
- `get_peer_comparison(symbol, query, page)` → ratios, industry and sector aggregates, peers.
- `screen_equities(rules, page, sort_direction)` → unsaved POST, fixed save=0, IHSG, sorted by the first rule metric.
- `get_corporate_actions(symbol, query, page)` → company events and stock conversions.
- `get_dividend_calendar(query, page)` → dividend calendar plus today's events.
- Every tool returns provenance, warnings and pagination in the shared output envelope.

## Incremental update procedure

- Add each discovered endpoint immediately, with method, route, parameters, purpose, evidence and verification status.
- Upgrade a source-only entry only after capturing a successful response; keep empty-result limitations visible.
- Append a dated discovery note after each inspection batch. Never store session tokens, cookies, private watchlists or portfolio data in this catalogue.
- Next validation priorities: actual intraday/daily OHLCV, timestamp timezone, split/dividend adjustment, backfill limits, calendar category schemas, earnings publication dates and rate limits.

## Discovery log

- 2026-09-19: In-page fetch transport ([ADR 006](../decisions/006-in-page-fetch-transport.md)). Token-less fetch returns 401 JSON; the bearer is read in-page from the `credentialStorage` cookie. All 18 verified research routes are CORS-readable with `credentials: omit`. Verified parameter variants: fundachart `timeframe` 1y/3y/5y/10y (`all` returns an empty series); chart `timeframe` today/1d/1w/1m/3m/6m/ytd/1y/3y/5y (unknown values fall back silently); financial `statement_type` 2 (annual, `12M YYYY` labels) and 3 (TTM); unknown symbols return 400/404 JSON. `POST /screener/templates` `ordercol=2` sorts by the first rule metric (asc and desc confirmed). Verification summary: `stockbit-evidence/fetch-transport-2026-09-19/`.
- 2026-09-17: Consolidated 50 captured responses into 24 method/route entries. Inspected Keystats, financials, FundaChart, Screener, analysts, comparison and corporate-action/calendar pages. Chartbit encountered a load failure; full candle data remains unverified.
- 2026-09-17, second batch: Added 22 source-only route families. Retried the MAPI corporate-action page successfully: both company actions and stock-conversion requests returned HTTP 200; dividends, RUPS and split history rendered in the UI.

## Evidence files

- Raw captured responses from the 2026-09-17 investigation are not distributed with this
  repository. The maintainers keep them privately and replay a sanitized subset through the
  research tests; see `tests/evidence/README.md`.
- Distributed examples under `sohib/stockbit/fixtures/` are authored synthetic test cases.
  Captured/normalized responses and bulk metric inventories are not distributed.
  Descriptive QA notes remain in `stockbit-evidence/fetch-transport-2026-09-19/`.

## Create New screener — verified 2026-09-17

- **Flow tested:** blank custom builder → select Current PE Ratio (TTM) → threshold > 0 → Add a Rule → Basic Ratio → Volume MA 20 > 500000 → Screen.
- **Result:** HTTP 200; 440 matching equities, 25 per page. This is an API demonstration, not an investment shortlist.
- **Rule types exposed by Add a Rule:** Basic Ratio and Ratio Vs Ratio. This batch executed two basic rules; the earlier preset investigation captured a compare rule.
- **Endpoint:** `POST https://exodus.stockbit.com/screener/templates`.
- **Execution versus persistence:** Screen sent `save="0"`, `screenerid="0"`, `type="TEMPLATE_TYPE_CUSTOM"`. Save Screener is a separate UI action and was not exercised. A generated screen name does not mean the screen was saved.
- **Metric IDs:** PE TTM `2891`; Volume MA 20 `12464`. Resolve metric labels through `/screener/metric` before building rules.
- **Encoding:** `universe` and `filters` are serialized JSON strings inside the JSON body. `sequence` is a comma-separated metric-ID string.
- **Default universe observed:** `{"scope":"IHSG","scopeID":"","name":""}`. Do not require nonempty scopeID/name for this observed IHSG form.
- **Ordering:** this custom builder emitted `ordertype="asc"` and `ordercol=2`; previous preset execution emitted uppercase DESC. Full accepted enums and index semantics remain unverified.
- **Output:** `calcs`, `rules`, `columns`, `curpage`, `perpage`, `totalrows`, ordering metadata and screen metadata. Use raw numeric result fields for calculations and display values for presentation.
- **Harness implication:** expose `screen_equities` with structured metric rules, universe, columns, sorting and page. The adapter serializes the payload and fixes save=0; agent callers need not manipulate UI templates.
- **Still to verify:** pagination request behavior, alternate universes, custom ratio-vs-ratio multipliers, maximum rule count, OR/group logic and screen-save response semantics. Do not infer these from the controls alone.

Illustrative request body (fixed example name):

```json
{
  "name": "TEMPLATE_BUILD_0000_0000",
  "description": "",
  "save": "0",
  "ordertype": "asc",
  "ordercol": 2,
  "page": 1,
  "universe": "{\"scope\":\"IHSG\",\"scopeID\":\"\",\"name\":\"\"}",
  "filters": "[{\"type\":\"basic\",\"item1\":2891,\"item1name\":\"Current PE Ratio (TTM)\",\"operator\":\">\",\"item2\":\"0\",\"multiplier\":\"\"},{\"type\":\"basic\",\"item1\":12464,\"item1name\":\"Volume MA 20\",\"operator\":\">\",\"item2\":\"500000\",\"multiplier\":\"\"}]",
  "sequence": "2891,12464",
  "screenerid": "0",
  "type": "TEMPLATE_TYPE_CUSTOM"
}
```

## Metric and account discovery

Captured Screener, Keystats and Financials inventories are not distributed. Use
`list_metrics` in browser mode to retrieve names and IDs from your own session;
keep namespaces distinct and follow pagination. See [Screener discovery](stockbit-screener-metrics.md),
[Keystats discovery](stockbit-keystats-metrics.md) and [Financial-account discovery](stockbit-financials.md).
Company routes use `{symbol}`; example symbols in protocol documentation are not
hard-coded company routes or bundled market observations.

## Harness tool contracts and authentication

All thirteen [tool contracts](tool-contracts/README.md) are implemented in browser
mode. The [authentication notes](tool-contracts/authentication.md) describe session
boundaries; no automated login or refresh is supplied.

## Company search — 2026-09-17

- **Verified** `GET /search?keyword={query}&page=0&type=all&catalog_types=CATALOG_TYPE_SECTOR&catalog_types=CATALOG_TYPE_INDUSTRY`. Symbol and company-name queries captured.
- [Field mapping, query options and limitations](company-search.md). [Tool contract](tool-contracts/search_companies.contract.json).
- Results include warrants and partial matches. Filter instrument types explicitly; first-page results are not exhaustive. Personal recent searches are excluded.
