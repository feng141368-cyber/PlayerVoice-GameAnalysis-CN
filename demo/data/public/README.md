# Public market-review sample

`market_reviews.csv` is a small English-language sample fetched from Steam's public review endpoint for:

- Tower of Fantasy (`app_id=2064650`)
- Palia (`app_id=2707930`)

It is used only to demonstrate cross-product market-context analysis. It is not joined to Veloura player telemetry and does not represent first-party product feedback.

The fetcher stores the source, app ID, app name, creation timestamp, recommendation flag, playtime hours, and review text. It intentionally excludes Steam account IDs and profile names. A local sequential ID is added for analysis.

Refresh the sample from the repository root:

```bash
python scripts/fetch_steam_reviews.py --per-app 100
python scripts/run_pipeline.py
```

Public review text belongs to its respective authors/platform. For downstream publication or commercial use, confirm the current source terms and replace or remove the sample if needed.
