# Company search

## Verified requests

On 2026-09-17, the global search field on `/stream` returned HTTP 200 for both a symbol query (`AKRA`) and a company-name query (`Mitra Adiperkasa`). The latter displayed MAPI alongside partial matches. These are examples, not hard-coded company routes.

- Endpoint: `GET https://exodus.stockbit.com/search`.
- `keyword`: URL-encoded user query.
- `page=0`: observed first page. Further-page semantics and completeness are unverified.
- `type=all`: observed; do not invent an equity-only server enum.
- Repeated `catalog_types`: `CATALOG_TYPE_SECTOR` and `CATALOG_TYPE_INDUSTRY`. These were present in both requests; necessity and other accepted values are unknown.
- No explicit sort parameter observed. Preserve server order after filtering; ranking semantics are unknown.
- `/search/recent` was also observed but is personal history, not a company directory. Its response was not retained.

## Company fields and instrument filtering

`data.company[]` contains id, name, desc, country, exchange, other, type, status, symbol_2, symbol_3, is_tradeable, img, icon_url, url, is_verified, total_followers and is_following. Here `name` holds the symbol and `desc` holds the company name. The last field is account-specific and is stripped from fixtures and outputs.

AKRA query returned an equity (`type=Saham`, `other=saham`) and related warrants (`type=Waran`, `other=waran`). A four-letter heuristic is insufficient. The v1 company tool retains entries with type=Saham AND other=saham, country=ID, exchange=IDX; unknown instrument classifications are excluded with a warning, not guessed. Preserve is_tradeable as metadata, not a trading authorization. Do not discard an equity just because it is not currently tradeable.

Discard non-company groups (people, insiders, chat, catalogue etc.) before logging or returning results. Search evidence contains company fields only.

## Normalized tool output

Use the shared envelope. One record per retained company:

- key: provider company id; namespace: `stockbit.company`.
- symbol: provider name; label: provider desc; value: symbol; display_value: company name.
- unit, currency, period, timestamp, missing_reason: null (not financial measurements).
- attributes: company_id, country, exchange, instrument_type, is_tradeable, symbol_2, symbol_3 and relative company_path.
- Validate company_path against `/symbol/{returned_symbol}`; construct the URL on the fixed Stockbit origin rather than following arbitrary provider URLs.
- pagination: page=0, total=null, next_page=null, complete=null. First-page candidates are not a complete listed-company universe.
- provenance: endpoint_template=`/search`, actual fetched_at, data_as_of=null, published_at=null, adjustment=unknown.
- Empty company candidates: status=ok, records=[], error=null; retain a warning if non-equities or unknown types were filtered.
- Exact symbol matching can assist the caller, but a fuzzy company name must not silently resolve to the first result. Ask the user or use additional company metadata when ambiguity matters.

## Verification and fixture

The packaged fixture [`company-search.json`](../../sohib/stockbit/fixtures/company-search.json) contains authored synthetic queries and drives fixture mode. Tests cover: exact symbol with related warrants, name query with partial matches, empty results, unknown type, nontradeable equity, Unicode/URL encoding, whitespace rejection, exclusion of personal groups and is_following, invalid URL paths, and auth/error envelope behavior. Existing shared retry/session rules apply.

Contract: [search_companies](tool-contracts/search_companies.contract.json). Input: [schema](tool-contracts/search_companies.input.schema.json).
