# Alias validation rules

Issue 3 keeps alias discovery separate from canonical game resolution and applies these deterministic
rules before an alias can be used in search:

1. Official and localized titles inherited from a resolved, evidenced `GameEntity` are validated and
   standalone-safe.
2. An alias without evidence is rejected.
3. Co-occurrence-only observations remain pending and search-disabled.
4. High-ambiguity terms are never standalone-safe. They may be `scoped_only` when evidence and a
   platform scope exist; otherwise they are rejected.
5. Medium-ambiguity or explicitly platform-scoped aliases are `scoped_only`.
6. Community nicknames need at least two evidence records. Other non-official alias types have
   type-specific confidence thresholds.
7. Low-ambiguity aliases may validate but are not standalone-safe.
8. Normalization-equivalent observations merge evidence IDs, source references and platform scopes.

`AliasDiscoveryResult.query_ready_aliases()` returns only validated aliases by default. Scoped aliases
must be requested explicitly and require disambiguation in the Query Builder.
