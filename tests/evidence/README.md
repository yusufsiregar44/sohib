# Local captured responses for the research tests

`tests/test_stockbit_research.py` replays sanitized Stockbit API responses through the
normalizers. Those captures are not distributed with the repository: everything in this
directory except this file is ignored by git. When a capture is missing, the test that needs
it is skipped with a message naming the file, so the rest of the suite still runs in CI.

To run the full suite locally, place the captured JSON files here (or point
`SOHIB_EVIDENCE_DIR` at a directory that holds them). The file names the tests expect are
listed in the test module; each is one raw JSON response body from the route it exercises,
with account-specific fields removed and no request headers.

To add a capture for a new endpoint, follow [CONTRIBUTING.md](../../CONTRIBUTING.md): call
the route once through `sohib-tools call`, save the response body here, strip any personal or
account-specific fields, and reference it from the test by file name.
