# Changelog

## 0.1.0 — 2026-09-19

First public release, cut from the private Learn-SohiB development history.

- Local MCP server (`sohib-mcp`), JSON tool CLI (`sohib-tools`) and setup commands (`sohib setup|connect|doctor|config`).
- Thirteen read-only research tools over an in-page fetch transport that runs inside your own signed-in Stockbit tab: search, key statistics, metric discovery (five namespaces), company summary, financial statements, fundamental history, price series, price performance, analyst consensus, peer comparison, corporate actions, dividend calendar and unsaved screening.
- Route allowlist, static page function, bearer read in-browser only, shared error taxonomy, 24 KB response budget.
- macOS, Linux and Windows support for the browser boundary (portable locking and process control). Windows is CI-tested for the unit suite; a live Windows browser run is still pending.
- Catalogue version 1.1.0; tool contracts generated from the runtime definitions.
