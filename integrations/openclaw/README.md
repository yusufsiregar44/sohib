# OpenClaw access without modifying OpenClaw

This SohiB-owned bridge follows the mcporter workflow from OpenClaw's mcporter skill. It
does not import, patch, register with or write into OpenClaw.
The launcher's client is installed here, pinned to mcporter 0.13.13 with a lockfile.
It uses an explicit empty client configuration and an ad-hoc stdio server, so no
OpenClaw or global MCP configuration is needed.

## Ready on this machine

Give your OpenClaw agent this message:

> Read `/absolute/path/to/sohib/integrations/openclaw/TOOLS.md` and use the bridge
> beside it to search for SIDO and retrieve its return-on-equity metric. Run on this
> machine using the existing Stockbit browser session. Preserve the tool's warnings and
> cite the returned source URL. Do not change OpenClaw configuration.

The agent needs host shell execution, Node on PATH, and access to the SohiB checkout on
the same machine as Chrome. If OpenClaw is isolated in a container or on another
machine, this local path does not provide remote access; use its existing host/node
execution capability, subject to its current permissions. No policy changes are made.

Direct commands work from any directory:

```bash
python3 /absolute/path/to/sohib/integrations/openclaw/bridge.py list
python3 /absolute/path/to/sohib/integrations/openclaw/bridge.py call search_companies --arguments '{"query":"SIDO"}'
python3 /absolute/path/to/sohib/integrations/openclaw/bridge.py call get_key_statistics --arguments '{"symbol":"SIDO","query":"return on equity","page":1}'
```

Browser mode is the default; `STOCKBIT_MODE=fixture` explicitly selects replay.
The launcher uses the Python interpreter that has SohiB installed (`SOHIB_PYTHON`
overrides it), reads session paths from `sohib setup`, retains explicit environment
overrides, and sets a 60-second client deadline. No credentials are
read by the launcher and no automatic sign-in is attempted. Inspect JSON errors,
not only exit codes: mcporter can exit successfully for a domain-error envelope.

## Reinstall after cloning

```bash
cd /absolute/path/to/sohib
python3 -m pip install .
npm ci --prefix integrations/openclaw --ignore-scripts
```

The browser connection must already be configured with `sohib setup` and `sohib connect`
as described in [setup](../../docs/portable-setup.md). Keep the signed-in Chrome open.

## Verification boundary

Discovery and live SIDO search/statistics are tested through this exact bridge
from `/tmp`, outside both checkouts. Source URLs, ambiguity and warnings survive
the mcporter transport. The launcher has regression tests for fixed paths,
argument handling and missing dependencies.

On 19 September 2026 live search returned SIDO and SDMU; SIDO ROE (TTM) returned 32.13% with
`https://stockbit.com/symbol/SIDO/keystats` as its source and unknown data-as-of
explicitly preserved. The npm lockfile installation was also verified.

No OpenClaw model turn was run and no OpenClaw settings were changed. Reading this
handoff explicitly gives its agent the invocation instructions. Automatic skill
discovery or native tool registration would require a separate installation step;
it is deliberately not claimed here.
