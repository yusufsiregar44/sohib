# Security

SohiB touches a brokerage account session, so its design is built around not holding secrets and
not being able to act on your behalf beyond read-only research. Both guarantees are structural,
not configuration: there is no code path that stores a token, and no order, watchlist or
portfolio route exists to be enabled later. Nothing here is a default waiting to be flipped.

## What SohiB does and does not do

1. No credentials. There is no login command, no password file and no token store. You sign in to
   Stockbit yourself in a Chrome window that SohiB opens with a dedicated profile.
2. Token stays in the browser. Tool calls run a fixed JavaScript function inside the signed-in
   page. That function reads Stockbit's own session cookie and sets the authorization header. The
   Python process, the tool output, logs and your agent never receive the token.
3. Allowlisted routes only. Every reachable Stockbit endpoint, its permitted query parameters and
   their accepted values are declared in `sohib/stockbit/api_routes.py`. Anything else is rejected
   before the browser is involved.
4. No agent-written code. Agents supply typed arguments. Paths are built by SohiB and validated.
   The page function is a constant.
5. Read-only. The only non-GET route executes an unsaved screener query; its body must match the
   documented constants (`save="0"`, `screenerid="0"`, `type="TEMPLATE_TYPE_CUSTOM"`) or it is
   refused. There are no order, portfolio, watchlist or account routes.
6. Personal data stripped. Normalizers keep public market fields and drop account flags,
   followers, personal templates and watchlists.
7. Explicit failure. HTTP 401 becomes `AUTH_EXPIRED`, a 403 challenge page becomes
   `AUTH_CHALLENGE`, a Cloudflare 1010 block becomes `FORBIDDEN`, 429 becomes `RATE_LIMITED`.
   Nothing retries, nothing re-authenticates, nothing bypasses provider protection.
8. Local only. The Chrome debugging port binds to loopback. The MCP server speaks stdio to a
   client on the same machine. The MCP server has no network listener; Chrome exposes
   its local debugging interface on loopback.

## What you are responsible for

1. The Chrome profile under your SohiB data directory holds your Stockbit session. Treat it like a
   password: do not copy it, share it or expose the debugging port.
2. Any MCP client you connect can call every tool. Connect only clients you trust with read access
   to your Stockbit data.
3. Comply with Stockbit's terms of service. SohiB is not affiliated with Stockbit.

## Reporting a vulnerability

Report security issues privately to etc@yusufsiregar.com. Do not disclose vulnerability
details in a public issue or include tokens, cookies or account data in a report. Include
the SohiB version, platform and sanitized steps to reproduce.

GitHub's private vulnerability reporting form is not yet enabled for this repository
(checking and enabling it returned HTTP 404 on 20 September 2026 while the repository was
private). We intend to enable and verify the
[private reporting form](https://github.com/yusufsiregar44/sohib/security/advisories/new)
as a second channel once the repository is public. Until then, the email address above is
the reporting channel.
