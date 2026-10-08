# Analysis method

## Topic assignment

The baseline classifier uses a bilingual, auditable keyword taxonomy and assigns one primary topic. Inspect the `Other` share; a high share means the taxonomy or language coverage needs improvement.

## Negative proxy

- Steam: use the source-native recommended/not-recommended flag.
- Other sources: use the declared lexicon or model score.
- Never compare these measures without labelling the different methods.

## Momentum

Compare a recent window with the immediately preceding equal-length window using topic share, not raw counts alone. Suppress momentum scoring for very small samples.

## Cross-source breadth

Count distinct collected sources mentioning a topic. Unavailable or disabled sources do not increase breadth. Convergence improves investigation priority but does not prove prevalence or impact.

## Priority

Score volume, negativity, momentum, and source breadth from 0 to 3. Treat the total as triage support only. `Other` is never a product priority.
