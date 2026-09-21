# Synthetic test fixtures

These small examples were authored for parser, pagination and MCP transport tests.
They are not captured Stockbit responses and contain no observed company values.
Existing query aliases (AKRA, MAPI and Mitra Adiperkasa) are retained for CLI test
compatibility; their fixture identities and numbers are invented.

- `company-search.json`: synthetic equity/warrant filtering and ambiguous matches.
- `mapi-keystats.json`: synthetic numeric, missing, percentage and negative values.
- `screener-metrics.json`: 26 synthetic entries, including one duplicate ID across
  categories, to exercise pagination and preserve namespace/category semantics.
- `output.schema.json`: SohiB's shared output contract.

The two metric IDs used by the unsaved-screen contract example remain as interface
identifiers. The taxonomy is deliberately incomplete; discover actual metrics with
`list_metrics` in browser mode. Fixture results carry `fixture_kind=synthetic`, null
observation dates and a warning against using invented values for research.
