# SohiB

Research Indonesian equities with AI agents through your own Stockbit account.

SohiB is a local [MCP](https://modelcontextprotocol.io) server. Point Claude Code, Claude Desktop,
Codex, Cursor, OpenClaw or any other MCP client at it and the agent gains thirteen read-only
research tools: company search, key statistics, financial statements, price history, analyst
consensus, peer comparison, corporate actions, the dividend calendar and unsaved screening.

Every request runs inside a Chrome tab where you are already signed in to Stockbit — the page
reads its own session cookie and sets the auth header itself, so SohiB never asks for your
password, never stores a token, and its own process never sees one either. Read-only is
structural here, not a setting: there is no login command, no token store and no order,
watchlist or portfolio route anywhere in the codebase to turn on.

SohiB is an independent open-source project. It is not a Stockbit product. Use it with your own
account under Stockbit's terms of service.

## How it works

1. `sohib connect` opens a dedicated Chrome profile with a loopback-only debugging port. You sign
   in to Stockbit yourself, including any device verification.
2. When an agent calls a tool, SohiB attaches to that tab over the local debugging connection and
   runs one fixed JavaScript function that calls Stockbit's own web API from the page. The page
   reads its session token from Stockbit's cookie and sets the header itself. The token never
   leaves the browser.
3. The response is validated, normalized into one envelope (records, provenance, pagination,
   warnings, error) and returned to the agent. Only the routes listed in
   [`sohib/stockbit/api_routes.py`](sohib/stockbit/api_routes.py) can be requested.

## Requirements

1. Python 3.12 or newer
2. Google Chrome or Chromium on the same machine as your agent client
3. A Stockbit account
4. macOS, Linux or Windows. Windows support is new; please report issues.

## Quickstart

```bash
git clone https://github.com/yusufsiregar44/sohib.git && cd sohib
python3 -m pip install .             # not yet on PyPI; install from this checkout
sohib setup                          # private configuration in your user data directory
sohib connect                        # opens Chrome; sign in to Stockbit yourself
sohib doctor --smoke SIDO            # checks the session and runs one live search
```

Then print the configuration for your client and paste it where that client expects it:

```bash
sohib config claude      # Claude Code and Claude Desktop (mcpServers JSON)
sohib config codex       # Codex (TOML block)
sohib config openclaw    # mcporter JSON for OpenClaw
sohib config mcp         # generic mcpServers JSON (Cursor, Windsurf, others)
```

For Claude Code, one command is enough:

```bash
sohib config claude > sohib-mcp.json && claude --mcp-config sohib-mcp.json
```

Keep exactly one Stockbit tab open in the SohiB Chrome window. After a reboot, run
`sohib connect` again; the profile keeps your session until Stockbit expires it, at which point
tools return `AUTH_EXPIRED` or `AUTH_CHALLENGE` and you sign in again in the browser.

Try asking your agent:

> Search Stockbit for SIDO, confirm the symbol, compare its PE ratio with its industry, and show
> the last four quarters of revenue. Cite the source URLs and keep the warnings.

## Tools

| Tool | What it returns |
|---|---|
| `search_companies` | IDX equity candidates for a symbol or name; warrants excluded, ambiguity preserved |
| `get_company_summary` | Identity, sector classification and the last provider quote |
| `get_key_statistics` | Grouped valuation, profitability, growth and balance-sheet metrics |
| `list_metrics` | Metric labels and IDs for keystats, screener, fundachart, comparison and financials |
| `get_financial_statements` | Income statement, balance sheet or cash flow cells; quarterly, annual or TTM |
| `get_fundamental_history` | Historical series for one FundaChart metric |
| `get_price_series` | LINE price points with a period summary (not OHLCV) |
| `get_price_performance` | Price change, high and low across provider windows |
| `get_analyst_consensus` | Recommendation counts, price targets and yearly estimates |
| `get_peer_comparison` | Ratios beside industry and sector aggregates, plus peer symbols |
| `get_corporate_actions` | Dividends, meetings, splits and tender offers with dates kept separate |
| `get_dividend_calendar` | Market-wide dividend calendar and today's scheduled events |
| `screen_equities` | Unsaved IHSG screen from numeric rules on screener metrics |

Full contracts, input schemas and live evidence: [docs/stockbit](docs/stockbit/README.md).

## What the agent gets back

Every tool returns the same envelope. `status` is `ok`, `partial` (valid data with warnings you
should keep) or `error`. Records carry a value, the provider's display string, unit, currency,
period and a `missing_reason` when the provider had no value. Missing values are never turned into
zero. `provenance.fetched_at` is retrieval time, not publication time; `data_as_of` is null unless
the provider states it. Each record cites a `source_url` on stockbit.com.

## Safety model

None of this is a default you could switch off — it is the entire feature set. There is no code
path anywhere in this repository that stores a token or places an order.

1. Read-only. There is no order, watchlist, portfolio or account tool, and no write route in the
   allowlist except one unsaved screen execution whose body is checked field by field.
2. Your credentials stay with you. SohiB has no login step and no password file. The browser
   reads its own cookie; SohiB's Python process never sees the token.
3. Fixed page function. Agents pass arguments, never JavaScript. Paths are validated against the
   allowlist before anything is sent to the browser.
4. Explicit failure. Expired sessions, verification prompts, rate limits and provider blocks come
   back as typed errors. Nothing retries, nothing logs in for you, nothing bypasses Cloudflare.
5. One call at a time per browser. Concurrent callers get a busy error rather than a queue.

See [SECURITY.md](SECURITY.md) for details and how to report a problem.

## Limits

1. Price data is the provider's LINE series only. Timezone and adjustment are unverified.
2. Latency is dominated by Stockbit's response time: usually one to three seconds, occasionally
   much longer on cold endpoints. Give your client a tool timeout of at least 60 seconds.
3. Responses are capped at about 24 KB per page. Use `query` filters and `page` to move through
   large results.
4. Nothing here is investment advice. Values are observations at retrieval time.

## Development

```bash
git clone https://github.com/yusufsiregar44/sohib.git && cd sohib
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e . && python -m pip install --group dev
python -m ruff check . && python -m ruff format --check .
python -m unittest discover -s tests -v
```

Tests run offline against synthetic examples; optional private-capture tests skip when local evidence is absent. Live verification against Stockbit is
manual; a descriptive summary of the last run is in
[docs/stockbit/stockbit-evidence](docs/stockbit/stockbit-evidence/fetch-transport-2026-09-19/README.md).
See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add an endpoint.

## Documentation

1. [Setup and browser lifecycle](docs/portable-setup.md)
2. [MCP server, CLI and verified clients](docs/mcp-tools.md)
3. [Codex and Claude](docs/codex-claude.md) · [OpenClaw](integrations/openclaw/README.md)
4. [Architecture](docs/tool-provider-architecture.md) and [decisions](docs/decisions/)
5. [Stockbit API catalogue, contracts and evidence](docs/stockbit/README.md)

## License

Apache-2.0. See [LICENSE](LICENSE).
