# Transport verification summary — 19 September 2026

The original local verification exercised all thirteen browser-mode tools through
in-page fetch from a signed-in Stockbit tab. This is a descriptive QA record, not
a distributed dataset: captured and normalized response files are not included in
the source-only release. Successful calls do not establish current availability,
full market coverage, a stable public API, or rights to redistribute provider data.

Verified paths covered company search and summary, key statistics, metric discovery,
financial statements, fundamental history, LINE prices and performance, analyst
consensus, peer comparison, corporate actions, dividend calendar, and unsaved
screening. Unknown-company handling and both screen sort directions were exercised.

For reproducible current verification, use your own signed-in browser and the CLI
or MCP tools. Keep response captures in ignored local storage. The bundled fixtures
are authored synthetic examples, not evidence of upstream behavior.

See [ADR 006](../../../decisions/006-in-page-fetch-transport.md) and the
[ADR 006](../../../decisions/006-in-page-fetch-transport.md).
