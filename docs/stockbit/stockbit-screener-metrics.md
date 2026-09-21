# Screener metric discovery

The captured Stockbit taxonomy is not distributed in this source-only release.
Use `list_metrics` with `namespace="screener"`, `symbol=null`, a label query and
`page=1` in browser mode. Follow `pagination.next_page` until complete.

IDs belong to this namespace; do not substitute keystats IDs. The packaged fixture
is a small synthetic parser/pagination example, not the current provider taxonomy.
