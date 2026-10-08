# Relevance baseline

Issue 7 adds an inspectable rule-based relevance stage between retrieval and
the default corpus. It does not use sentiment words as relevance evidence.

## Labels and signals

- `relevant`: the record has strong game identity/context evidence.
- `ambiguous`: some game evidence exists but is insufficient for safe corpus
  inclusion.
- `irrelevant`: identity conflicts or game-specific evidence is absent.

The strongest signal is a source-native entity ID such as a matching Steam app
ID. Other positive evidence includes an official/localized title, a validated
alias, developer/publisher context, and configured game-specific terms.
Competing entity names and mismatching native IDs are negative evidence.

A medium/high-ambiguity alias by itself can never produce `relevant`. For
example, `CS2 is terrible` is reviewable but ambiguous. `CS2 update made my FPS
worse on Mirage` can become relevant when `Mirage` is configured as a
game-specific term and the surrounding context supports the scoped alias.

Every evaluated `EvidenceItem` stores the label, score, named reasons, and a
method version whose hash includes thresholds and configured term sets.
Structured signals remain in `source_metadata.relevance_signals`.

## Review and corpus policy

`write_review_queue` exports ambiguous records as JSON or CSV with original
text, source reference, query provenance, score, reasons, and method version.
`relevant_only` is the explicit default-corpus gate. Ambiguous and irrelevant
records remain available for counts/review rather than being silently deleted.

This deterministic baseline is not a universal semantic classifier. New games
benefit from curated game-specific terms and competing-entity fixtures; manual
sampling remains required for real retrieval quality claims.
