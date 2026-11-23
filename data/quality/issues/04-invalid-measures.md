# Invalid measures

## What we found

Four measures contain a small set of impossible or round sentinel numbers. The rest of each column sits in a normal range.

| Governed measure | Invalid values | Rows | Values that are kept |
|---|---|---|---|
| `runtime_minutes` | `-1` (5), `99999` (5) | 10 | 2, 5, 8, 12, 25, 45, 90, 180 |
| `follower_count` | `-5` (2), `999999` (2) | 4 | 177 through 158177 |
| `monthly_price_usd` | `-9.99` (8), `999.99` (8) | 16 | 0.00 through 24.99 |
| `session_duration_sec` | `-15` (30), `86400` (4), `604800` (30) | 64 | median about 2,991 seconds |

`86400` is exactly 24 hours and `604800` is exactly 7 days. Follower counts in the hundred thousands are kept. A price of `0.00` is kept; it belongs to Free plans and is covered in the blank-subscription treatment.

## Treatment

Keep the row. Set the governed measure to null, keep the source number in the `*_raw` column, and set `*_is_invalid` to true.

Counts of rows still include these records. Sums and averages use the governed measure only, so the sentinel numbers never enter a total. `active_monthly_price_usd` on `mart_business` skips the 16 invalid prices. `mart_plans` still counts those subscriptions and reports them in `invalid_price_subscriptions`.

## Check to enforce

Fail if a governed measure is negative, or if runtime is `99999`, followers are `999999`, price is `999.99`, or session duration is `86400` or `604800`. A new value outside the kept ranges above should show up in `profile.json` and be classified before it is included in a sum.
