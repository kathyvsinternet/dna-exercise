# Blank subscription fields

## What we found

`billing_cycle` is blank on 215 subscriptions, `monthly_price_usd` is `0` on 215, and `plan_tier` is `Free` on 215. These are the same 215 rows. No paid plan has a blank cycle or a zero price.

`end_date` is blank on 619 subscriptions:

| Status | Subscriptions | Blank `end_date` |
|---|---|---|
| `active` | 465 | 465 |
| `paused` | 96 | 96 |
| `trialing` | 38 | 38 |
| `TEST_STATUS_DO_NOT_USE` | 20 | 20 |
| `canceled` | 224 | 0 |

No end date falls before the start date.

## Treatment

Keep the rows.

- On Free plans, store `billing_cycle` as `not_applicable` and `monthly_price_usd` as `0.00`. The raw billing cycle stays blank.
- A blank `end_date` is stored as null. It is valid for every status other than `canceled`.
- `TEST_STATUS_DO_NOT_USE` is mapped to `unknown` by the sentinel treatment. Its blank end date stays null.

## Check to enforce

Fail if a Free subscription has a non-zero price or a raw billing cycle that is not blank. Fail if a paid subscription has a blank billing cycle or a zero price. Fail if a canceled subscription has a blank end date, or if an end date is earlier than the start date.
