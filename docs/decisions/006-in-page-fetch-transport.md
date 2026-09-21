# ADR 006 — In-page fetch transport for Stockbit research

- Status: Accepted, 19 September 2026
- Replaces: navigate-and-observe retrieval, where the worker opened Stockbit pages and captured
  the XHR responses the page happened to make
- Evidence: [verification summary, 19 September 2026](../stockbit/stockbit-evidence/fetch-transport-2026-09-19/README.md)

## Browser policy

SohiB attaches over a loopback CDP connection to a Chrome instance the user has already signed
in to. It never launches a browser, never submits credentials, never solves a verification
challenge and never closes the attached browser or tab. Missing or expired session state stops
the tool with an explicit error for the user to act on. This transport changes how reads are
issued inside that attachment; it does not change the policy.

## Decision

Research reads run as `fetch` calls issued from inside the already signed-in Stockbit tab's own
JavaScript context, through the existing Playwright CDP attachment. The page function is a fixed
literal; the only data passed in are the validated exodus path, the HTTP method, an optional
validated body, and the constant name and JSON path of the SPA's session cookie. The function
reads the bearer token from that cookie inside the browser and sets the header itself, so the
token never reaches the Python worker, tool outputs, logs or model context.

The worker fetches only routes in `sohib/stockbit/api_routes.py`. The allowlist names each
route's method, path shape, permitted query parameters and their accepted values, and a citation
page. `POST /screener/templates` is the only non-GET route and its body must equal an unsaved
custom IHSG screen (`save="0"`, `screenerid="0"`, `type="TEMPLATE_TYPE_CUSTOM"`, basic rules only).

Cloudflare is satisfied by the real browser; no fingerprint impersonation, challenge solving or
cookie replay is involved. A 401 maps to `AUTH_EXPIRED`, 403 HTML to `AUTH_CHALLENGE`, the
Cloudflare 1010 JSON body to `FORBIDDEN`, 429 to `RATE_LIMITED`, 400/404 to `NO_DATA`.

## Consequences

- Tool coverage grows from three tools to thirteen in browser mode: company summary, financial
  statements, fundamental history, price series, price performance, analyst consensus, peer
  comparison, corporate actions, dividend calendar and unsaved screening join search, key
  statistics and metric discovery. Fixture and disabled modes still expose only the original three.
- One browser attachment can serve several allowlisted paths, so multi-endpoint tools cost one
  worker run. Typical live calls complete in one to three seconds; upstream cold responses can
  take much longer.
- `retrieve` (navigate and observe) stays importable behind `PlaywrightBrowser(transport='observe')`
  for the three original routes as the documented rollback. No other code path navigates the tab.
- Financial statements are parsed from the provider's HTML report because its structured tables
  arrive empty; a populated structured table is treated as an unverified shape.
- Catalogue version becomes 1.1.0. The MCP protocol surface is unchanged.

## Verification

Observed on 19 September 2026 in the user's signed-in tab, with no browser launched, no login
submitted and no token or cookie value printed, logged or stored:

- A token-less in-page `fetch` returns HTTP 401 JSON, so Cloudflare accepts the real browser and
  only the application bearer is missing. The SPA keeps that bearer in a JavaScript-readable
  cookie (`credentialStorage`, JSON path `state.access.token`), which the page function reads in
  place.
- `credentials: 'include'` fails at the network layer because the API answers with a wildcard
  CORS origin; `credentials: 'omit'` works and the API needs no cookie.
- No `cf_clearance` cookie exists for the API host, so there is no clearance expiry to track.
- All 18 catalogued research routes return readable 200 JSON bodies from the page context.
- Parameter variants: fundachart `timeframe` 1y, 3y, 5y and 10y return series and `all` returns
  an empty one; chart `timeframe` today, 1d, 1w, 1m, 3m, 6m, ytd, 1y, 3y and 5y return LINE
  series and unknown values fall back silently; financial `statement_type` 2 (annual) and 3 (TTM)
  return populated HTML reports while `data_tables` stays empty; unknown symbols return 400 or
  404 JSON, mapped to `NO_DATA`.
- `POST /screener/templates` with `ordercol=2` sorts by the first rule metric in both directions.
  The screen is not saved.
- Each of the thirteen tools ran once; every envelope validated against the shared output schema
  and stayed under the 24 KB budget. Typical calls took one to three seconds; one cold
  financial-statement call took 28 seconds against the 40-second worker budget.

Known limits: market-wide taxonomies cite the API URL because no UI page maps to them; head rows
and their collapsed total rows can share a label and are told apart by key and `row_kind`;
estimate and quote currencies are not stated by the provider and stay null with a warning; price
series are LINE only, with timezone and adjustment unverified.

## Revisit triggers

Revisit if the SPA moves its session out of a readable cookie, if exodus starts requiring
cookies or a CSRF token, if CORS stops exposing bodies to the page origin, or if provider terms
for automated access change.
