# Local MCP research tools

The server exposes tools; it does not run a model, manage conversations, or need any model
credentials. Retrieval uses the in-page fetch transport
([ADR 006](decisions/006-in-page-fetch-transport.md)). The unit suite and Ruff checks run in CI on
macOS, Linux and Windows; live browser verification is manual, and a summary of the last
run is in the [verification notes](stockbit/stockbit-evidence/fetch-transport-2026-09-19/README.md).

## Install and try

```bash
python3 -m pip install .              # not yet on PyPI; install from a checkout (see README)
STOCKBIT_MODE=fixture sohib-tools catalogue
STOCKBIT_MODE=fixture python -m sohib.interfaces.mcp_smoke --symbol MAPI
STOCKBIT_MODE=browser python -m sohib.interfaces.mcp_smoke --symbol SIDO
```

The smoke command launches the server as a separate process and calls discovery,
company search, statistics and metric metadata through the official MCP client.
MAPI is a synthetic fixture alias; browser tools accept any supported symbol.
This deterministic smoke test exercises transport and tools, not model reasoning.

To call one tool directly:

```bash
STOCKBIT_MODE=browser sohib-tools call --name search_companies --arguments '{"query":"SIDO"}'
```

The CLI requires all fields in the published schema; use `query=""` and `page=1` for an
unfiltered first statistics page. JSON errors exit with code 1.

## Connect a local MCP host

`sohib config <client>` prints a ready-to-paste server entry with the absolute path of the
Python interpreter that has SohiB installed and the private data directory written by
`sohib setup`. Supported outputs: `claude`, `codex`, `openclaw`, `mcp`. The generic form is:

```json
{
  "mcpServers": {
    "sohib": {
      "type": "stdio",
      "command": "/absolute/path/to/python",
      "args": ["-m", "sohib.interfaces.mcp_server"],
      "env": {
        "SOHIB_HOME": "/absolute/path/to/your/sohib/data",
        "STOCKBIT_MODE": "browser",
        "STOCKBIT_BROWSER_CONNECTION_FILE": "/absolute/path/to/your/sohib/data/browser.json",
        "STOCKBIT_BROWSER_PROFILE": "/absolute/path/to/your/sohib/data/chrome"
      }
    }
  }
}
```

No `.env` is loaded automatically. Default mode is `disabled` until `sohib setup` has run,
then `browser`. Modes are `disabled`, `fixture`, and `browser`. Environment variables override
saved settings. All clients sharing one browser must use the same profile path so they share
its lock.

The connection file refers to the Chrome debugging connection that `sohib connect` opens on
loopback. It is local configuration, not a tool argument. Keep the signed-in browser open.
The server never opens a replacement browser, logs in, or closes your browser. Research
requests are issued from the attached Stockbit tab's own page context against an allowlist of
API routes; the tab is not navigated and no page is scraped.

Start `sohib-mcp` only under a client: its stdout is reserved for MCP JSON-RPC.
Set the host tool deadline above the bounded browser budget (60 seconds recommended).
Browser calls use a 40-second retrieval budget plus worker cleanup allowance.

## Contracts and ownership

Catalogue version `1.1.0` is exported by `sohib-tools catalogue`. Fixture mode exposes
`search_companies`, `get_key_statistics`, and `list_metrics`. Browser mode adds
`get_company_summary`, `get_financial_statements`, `get_fundamental_history`,
`get_price_series`, `get_price_performance`, `get_analyst_consensus`,
`get_peer_comparison`, `get_corporate_actions`, `get_dividend_calendar` and
`screen_equities`, and widens `list_metrics` to the fundachart, comparison and
financials namespaces. Every tool was live-verified on 19 September 2026; see
[ADR 006](decisions/006-in-page-fetch-transport.md) and the
[tool contracts](stockbit/tool-contracts/README.md). Typical live calls take one to
three seconds; cold upstream responses have taken up to 28 seconds.

Results carry the identical envelope in MCP `structuredContent` and JSON text:
records, provenance, pagination, warnings and errors. Domain/input errors set
`isError=true`; malformed protocol requests are handled by the SDK. Partial results
are successful calls with qualifications, not complete/fresh-data guarantees.
Clients must retain warnings, source URLs, ambiguous candidates and unknown dates.

Dispatch validates inputs and normalized output. Unexpected exceptions become
sanitized errors. A busy service fails explicitly instead of queueing competing
navigation. The existing file lock coordinates processes sharing one profile path.
MCP cancellation signals the isolated browser worker and waits for cleanup; the
SDK handles cancellation protocol semantics. No new session is created on failure.
This is local stdio only: no remote HTTP listener, multi-user auth or credential API.

## Verified compatibility

For OpenClaw, use the [SohiB-owned bridge and handoff](../integrations/openclaw/README.md).
It pins mcporter locally and resolves session paths independently of the agent's
working directory without modifying OpenClaw.

| Consumer | Version | Measured result |
|---|---|---|
| Official Python MCP client/server | `mcp==2.2.0` | Separate-process discovery, all three fixture tools, malformed arguments, missing connection, structured/text envelope; in-process client cancellation and recovery |
| Official Python MCP client | `2.2.0` | Live SIDO search, four return metrics, and metadata via existing Chrome |
| mcporter | `0.13.13` | Actual stdio fixture search and live SIDO statistics with provenance/warnings preserved |
| Codex CLI | `0.154.0` | Native BBCA search → PE statistics → cited model answer with live-mode/date warnings; recovery from invalid page 0 |
| Claude Code | `2.1.278` | Native discovery of all 13 tools; BBCA search → PE statistics → cited model answer, preserving unknown-date warning and live retrieval mode |
| Full OpenClaw agent | Not run | The bridge path above works; model-driven OpenClaw tool selection and answers are unverified |

The recorded client tests used MCP SDK 2.2.0. The package declares `mcp>=2.2,<3`,
so installation can select a newer compatible 2.x release; this is a version range,
not an exact pin or a guarantee that every allowed version has been tested. We use
the SDK's low-level server to preserve the existing schemas. See the
[official SDK documentation](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/).
Client interoperability is recorded above, not inferred from protocol support.

Reproduce the tested OpenClaw ecosystem client path without changing its settings:

```bash
STOCKBIT_MODE=fixture npx --yes mcporter@0.13.13 call \
  --stdio "python -m sohib.interfaces.mcp_server" \
  search_companies --args '{"query":"AKRA"}' --output json
```

Live verification returned SIDO and SDMU search candidates, preserving ambiguity.
SIDO return metrics were ROA 29.51%, ROE 32.13%, ROCE 37.33%, ROIC 29.44% with
source `https://stockbit.com/symbol/SIDO/keystats`. These are observations at test
time, not current recommendations or evidence of full market coverage. Metadata
returned the same four labels with null values. No login was performed.

Two native-host acceptance runs passed with Claude Code and Codex CLI on
20 September 2026: search → statistics → cited answer.
Production reliability, clean-machine
browser setup, full dependency locking and unattended operation remain later gates.
