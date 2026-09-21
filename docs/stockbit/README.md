# Stockbit integration — start here

This directory is the canonical build reference for SohiB's Stockbit provider. Update documents here; do not build from imported catalogue copies.

## Read in this order

1. [Tool contracts](tool-contracts/README.md): thirteen implemented browser-mode tools, generated input schemas, normalization rules and live-verification status.
2. [Authentication](tool-contracts/authentication.md): session ownership, credential boundaries, login/expiry/challenge handling and unverified details.
3. [API catalogue](stockbit-api-catalogue.md): verified routes, source-only discoveries, request examples and gaps.
4. Metric discovery: [Screener](stockbit-screener-metrics.md), [Keystats](stockbit-keystats-metrics.md), [Financials](stockbit-financials.md).
5. [Transport verification summary](stockbit-evidence/fetch-transport-2026-09-19/README.md): descriptive verification notes. Captured and normalized response datasets are not distributed.

## Machine-readable references

- Provider metric/account inventories are discovered on demand with `list_metrics`.
- [Shared output schema](tool-contracts/output.schema.json); each tool has an input schema and contract in the same directory.

## Current implementation boundary

All thirteen contracted tools are implemented in browser mode over the in-page fetch transport
([ADR 006](../decisions/006-in-page-fetch-transport.md)) and were live-verified on 19 September 2026
([evidence](stockbit-evidence/fetch-transport-2026-09-19/README.md)). Full OHLCV, unattended login/refresh,
rate limits, historical calendar ranges and point-in-time restatements remain unverified. On 20
September 2026, `screen_equities` returned `SCHEMA_CHANGED` for symbols IFSH and PNGO during
acceptance testing; the request failed cleanly with no records returned, and the root cause is not
yet investigated — treat this as a known open item for the alpha. Verified response samples do not
establish a stable public API contract. Use `{symbol}` for company routes; literal symbols identify
fixtures only.

## Source of truth and updates

- Tool interface: contract JSON and schemas. Explanation and normalization: tool-contracts/README.md.
- Provider behavior: API catalogue, with explicit verification status and evidence.
- Current metric/account discovery: `list_metrics` in browser mode; no extracted provider catalogue is bundled.
- Authentication policy: authentication.md. Store no credentials in this directory.
- Keep captured evidence local. Publish compact QA summaries, not provider datasets. Synthetic examples must be labelled as invented.
- Keep this index current when adding a capability. Add contracts only after documenting evidence and limitations.

## Broader project references

- [Architecture](../tool-provider-architecture.md)
- [Decision records](../decisions/README.md)
- [MCP server and CLI](../mcp-tools.md)

## Company discovery

- [Company search](company-search.md): verified symbol/name search, equity filtering and ambiguity handling.
- [Search tool contract](tool-contracts/search_companies.contract.json). Use this to resolve company candidates before calling `{symbol}` tools.
