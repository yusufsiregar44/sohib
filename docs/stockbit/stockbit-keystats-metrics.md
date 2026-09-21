# Key-statistics metric discovery

Captured metric tables and historical values are not distributed in this release.
Use `list_metrics` with `namespace="keystats"`, a confirmed symbol, a label query
and `page=1` in browser mode. Follow pagination rather than assuming full coverage.
Use `get_key_statistics` for values and preserve its units, dates and warnings.
The package's MAPI fixture contains invented test values, not historical prices.
