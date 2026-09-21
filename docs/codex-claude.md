# Codex and Claude: secondary clients

Codex and Claude use the same thirteen-tool MCP server and the same browser state as every
other client. There is no duplicated research adapter and no model credential in SohiB.

## Generate configuration

```bash
sohib config codex
sohib config claude
```

The command prints native TOML or JSON with absolute paths for the interpreter that has SohiB
installed and your private data directory. It reads no secrets, changes no client settings and
does not register anything. Run `sohib setup` first.

## Codex

Merge the generated TOML server block into your chosen Codex configuration, without
overwriting existing entries. Codex supports user config and trusted project-local
`.codex/config.toml`. The block sets a 20-second startup deadline and 60-second tool
deadline. See [official Codex MCP setup](https://developers.openai.com/codex/mcp).

After enabling it, start a fresh Codex session and check `/mcp`. Ask:

> Use SohiB to search for SIDO, confirm the exact symbol, and retrieve return on
> equity. Cite the source URL and preserve missing-date warnings.

The Codex desktop app's actual tool availability must be checked in a new task
after configuration; generating a file does not add tools to an already running task.
This change does not modify the user's global Codex configuration.

## Claude Code

Use session-only configuration to avoid editing global client settings:

```bash
sohib config claude > sohib-claude-mcp.json
claude --mcp-config sohib-claude-mcp.json
```

Check `/mcp`, approve the server if prompted by the client, then use the same SIDO
request above. Existing client permissions still apply. See
[official Claude Code MCP setup](https://code.claude.com/docs/en/mcp).

“Claude” currently means Claude Code, the installed client tested here. Claude
Desktop's native local MCP setup is untested; Claude's
web interface cannot reach this local stdio process merely from a configuration file.

## Verification, updated 20 September 2026

| Client | Version | Verified | Not verified |
|---|---|---|---|
| OpenClaw path | mcporter 0.13.13 | Live search/statistics through the SohiB-owned bridge | Full OpenClaw agent turn |
| Codex CLI | 0.154.0 | Native BBCA search → PE statistics → cited model answer; corrected invalid page 0 after `UNSUPPORTED_INPUT` | Desktop acceptance, other tools, ambiguous matches, native cancellation, other platforms |
| Claude Code | 2.1.278 | Native discovery of all 13 tools; model-driven BBCA search → PE statistics → cited answer with unknown-date warning and correct live/fixture distinction | Other tools, ambiguous matches, native cancellation/error recovery, other platforms |
| Claude Desktop | Not tested | Configuration design only | Install and end-to-end acceptance |

No live user configuration was changed. The earlier Claude registration was confined to a
temporary directory; the September 20 run used session-only `--mcp-config` with
`--strict-mcp-config`. Codex used per-command overrides. Shared transport tests
already cover discovery, envelopes, cancellation and provider errors; those do not
substitute for model-driven client acceptance.

The first native run surfaced a misleading tool description, corrected before the
passing run recorded above; the table's "Verified" column reflects the corrected
version. Claude Code and Codex CLI are now verified end to end. Claude Desktop,
Codex desktop and the full OpenClaw agent remain
separate acceptance gates.

Run clients on the host containing the configured Chrome session. Keep the same
connection/profile paths across clients. Do not call the shared browser concurrently;
busy calls return an explicit error. Browser expiry/verification requires restoring
the existing session, not automatic login. See [MCP setup](mcp-tools.md) and
[OpenClaw integration](../integrations/openclaw/README.md).
