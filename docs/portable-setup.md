# Portable local setup

SohiB owns installation setup and browser connection management independently of a
source checkout or client. Every client uses the same local MCP server.

## Install

Requirements: Python 3.12+, Google Chrome or Chromium, and a local graphical desktop on
macOS, Linux or Windows. Windows browser support is new in 0.1.0: the unit suite runs there in
CI, but please report any problem with the live browser path.

```bash
git clone https://github.com/yusufsiregar44/sohib.git && cd sohib
python3 -m pip install .
```

Install into a virtual environment. The installed commands do not need the source checkout
afterward. `sohib config` points clients at the interpreter that has SohiB installed, so keep
that environment after setup. Not yet on PyPI: `pip install sohib` will work once published.

## First-time connection

```bash
sohib setup
sohib connect
```

Setup writes private configuration to the user's application data directory:
macOS Application Support/SohiB, Linux XDG data home/sohib, or Windows LOCALAPPDATA/SohiB. `SOHIB_HOME` selects
an isolated installation explicitly. These paths are separate from the checkout.
Setup is idempotent and keeps existing configuration. It does not start a browser.

Connect explicitly opens Chrome with a dedicated persistent SohiB profile and a
loopback-only debugging connection. Sign in through the browser and complete any
device approval or verification yourself. SohiB does not need to collect or store
your password. The browser profile contains sensitive session state and must remain
private. Do not share it, commit it, or expose its debugging port remotely.

Keep exactly one Stockbit tab open. Session cookies persist in this profile, but
Stockbit can expire them or require verification again. After closing Chrome or
restarting the computer, run `sohib connect`: it opens the same profile. If the
browser is already running, it is reused. No background login retry is performed.

```bash
sohib doctor
sohib doctor --smoke SIDO
```

Doctor checks installed dependencies, browser connectivity, the Stockbit tab and
visible authentication state. Only the smoke request verifies actual research
retrieval; it issues one allowlisted request from the Stockbit tab and returns the normalized
tool envelope.
It reports missing sessions and verification requirements without attempting login.
Neither research tools nor doctor automatically launch a browser.

Set `SOHIB_CHROME_BINARY` if Chrome is installed in a nonstandard location.

## Keep an existing browser setup

If you already run Chrome with a loopback debugging port, register that connection and a
lock path instead of letting SohiB manage a profile:

```bash
sohib setup --connection-file /absolute/path/to/stockbit-browser.json \
  --profile /absolute/path/to/existing-profile-lock-base
```

Use the same profile argument as existing consumers to share their lock. This does
not copy credentials or browser state. An unavailable external browser is reported;
connect will never replace it with a new managed profile. Existing checkout-based
environment configuration still works. Environment values override saved settings;
saved settings override legacy checkout defaults. Corrupt saved settings fail
explicitly instead of falling back to a different browser.

## Connect your harness

```bash
sohib config openclaw > /tmp/sohib-mcporter.json
sohib config codex
sohib config claude > /tmp/sohib-claude.json
sohib config mcp
```

These commands print configuration, with absolute installed-interpreter and session
paths; they do not edit any client. OpenClaw uses its mcporter workflow:

```bash
mcporter --config /tmp/sohib-mcporter.json list sohib --json
mcporter --config /tmp/sohib-mcporter.json call sohib.search_companies \
  --args '{"query":"SIDO"}' --output json
```

Merge the generated Codex block into the chosen Codex configuration. For Claude Code:
`claude --mcp-config /tmp/sohib-claude.json`. Generic MCP output is a conventional
`mcpServers` object; host-specific import formats and permissions still apply.
See [client setup](codex-claude.md) and the [OpenClaw bridge](../integrations/openclaw/README.md).
The OpenClaw bridge remains available; installed users can use the generated config
directly. Run all local clients on the same machine as the browser.

## Acceptance boundary

Automated tests cover private/idempotent setup, environment precedence, generated
client formats, profile reuse and no browser replacement for external connections.
A fresh virtual environment installed the wheel with dependencies; setup, all client exports,
a fixture MCP call and an existing-session live SIDO smoke call worked from outside the
checkout. A separate
unauthenticated Chrome profile retained a synthetic persistent cookie across actual
browser shutdown and relaunch. That proves profile persistence, not Stockbit's
future session lifetime. Generated OpenClaw configuration also passed discovery.
An isolated application directory successfully attached to the existing Chrome
session and retrieved SIDO without a new login. Full clean-user Stockbit sign-in
requires that user's credentials and device approval; it cannot be claimed from
testing against an existing authenticated session.

Unattended refresh, remote multi-user hosting, browser auto-start on tool requests, and
guaranteed permanent authentication are not provided.
