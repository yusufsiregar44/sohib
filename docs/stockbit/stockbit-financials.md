# Financial-account discovery

Captured reports and extracted account inventories are not distributed in this
source-only release. Use `list_metrics` with `namespace="financials"`, a confirmed
symbol, a label query and `page=1` in browser mode to discover current accounts.
Use `get_financial_statements` for values. Accounts can differ between companies.

The implementation parses the provider's HTML report when structured tables are
empty. A populated structured table is an unverified shape and fails explicitly.
Keep reporting periods, units, missing values and duplicate-label row identities.
