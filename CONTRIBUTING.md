# Contributing

Thanks for helping Stockbit users research with their agents. This guide covers setup, checks and
the pattern for adding a new endpoint.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e . && python -m pip install --group dev
```

Before opening a pull request run the same checks as CI:

```bash
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
```

Tests are offline. They use synthetic package fixtures plus optional sanitized captured responses that are
kept out of the repository: place them in `tests/evidence/` (see its README) or the tests that
need them are skipped. Never add a fixture that contains a token, cookie, request header,
watchlist or other personal data; strip account flags before sharing.

## Adding an endpoint

1. Capture one real response from your own signed-in session, sanitize it and keep it in your
   local `tests/evidence/`. Record the route in `docs/stockbit/stockbit-api-catalogue.md`.
2. Add the route to `sohib/stockbit/api_routes.py`: method, path pattern, permitted query
   parameters with accepted values, and the stockbit.com page to cite. GET only unless you can
   show the request cannot persist or mutate anything.
3. Write a normalizer that turns the payload into records with `record()`. Keep provider display
   strings, leave missing values as `None` with a `missing_reason`, raise `SchemaChanged` on an
   unexpected shape, and drop personal fields.
4. Add the tool to `sohib/stockbit/contracts.py` (argument parsing and the model-facing
   definition), an adapter in `sohib/stockbit/adapters.py`, and a description in
   `sohib/tools/catalogue.py`.
5. Add tests with a browser double covering the happy path, missing values, personal-data
   stripping and a mutated shape. Regenerate the contract files in `docs/stockbit/tool-contracts`.
6. Verify once live through `sohib-tools call` and record a compact, dated result
   summary. Keep captured payloads local by default. Sanitizing credentials and
   personal fields does not establish permission to redistribute provider data;
   review that separately before adding an envelope or expanding a fixture.

## Before publishing a release

Review both the candidate files and all reachable Git history, not only the diff.
Fetch remote branches/tags first. Run a secret scanner with redacted output, inspect
the JSON examples for personal/account fields, and inspect a freshly built wheel
and source distribution for local captures, browser profiles, credentials and logs.
Check commit author/committer metadata as well: those addresses become public.

Use a current Gitleaks release from its official repository, verify its release
checksum, and keep reports outside the checkout:

```bash
gitleaks git . --log-opts='--all --full-history' --redact --ignore-gitleaks-allow
python -m build
```

Also scan an exported candidate tree and extracted release archives with
`gitleaks dir`. A clean scan is evidence about known patterns, not a guarantee of
absence or a redistribution license. Recheck the final release commit after edits.

## Style

Python 3.12+, standard library first. Ruff enforces layout with a 100 character line and single
quotes. Comments say why, not what. Error messages never echo provider bodies, headers or paths
that could carry secrets.
