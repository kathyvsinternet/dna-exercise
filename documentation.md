# Documentation

How this product keeps the numbers trustworthy, keeps person-level data off the public page, and is modeled. `python pipeline/build.py` rebuilds the model and every mart, and it stops if a check fails.

## Data quality and trust

`data/raw/` is never edited. The build profiles it, applies a treatment, and writes the result to `data/model/`. Each issue is written up in `data/quality/issues/`, and `pipeline/checks.py` fails the build if the same problem comes back.

- **Duplicate users.** 806 rows, 800 ids. Each repeated pair agreed on every column, so the first row is kept. A repeated id fails the build, and so does a new pair that disagrees.
- **Test accounts and planted values.** 40 test users stay in the facts, flagged, and every mart filters them out. Tokens such as `carrier_pigeon`, `TEST_TYPE`, and `glitch_in_the_matrix` become `unknown` on the governed column. The original value stays in a `_raw` column. A governed column that still holds a planted token fails the build.
- **Missing foreign keys.** A blank creator or content id stays null. Nothing is invented to fill it. A key that points at a missing row fails the build, and so does a break in the known pattern (MakerHarbor content without a creator, or a content event with no content id).
- **Invalid measures.** Sentinel numbers (a runtime of `-1` or `99999`, a price of `999.99`, a session of exactly 7 days) are nulled, the source number is kept, and an invalid flag is set. The row still counts. It does not add to a sum.
- **Blank subscription fields.** A Free plan with a blank billing cycle becomes `not_applicable`. A canceled plan with no end date fails the build.

The dashboard reads only the published marts, and each chart names the mart it came from. The build checks those marts against the facts: quarterly subscriptions and cancellations add up to the non-test fact rows, the net subscriptions and churn rate recompute from those counts, and each share table adds up to the 389 active non-test users, with shares adding up to about 1.

## Access

`user_name` and `email` are marked restricted in `data/model/schema.yml`. No mart selects them, and they are not in anything published under `site/`. `age_band` is not restricted, so the age table may use it.

The public page gets aggregates only, as JSON in `site/data/marts/`. The person-level tables (`dim_user`, `eph_user_info`) are built for the pipeline and are not copied into the site. `user_id` is used to count distinct people and is not shown.

A distinct count of people below 5 is not meant for the public page. The two subscription tables, Users by Active Subscriptions and Users by Paid Subscriptions, are an approved exception and show every group, including a group of one. The other share tables have no group smaller than 14.

## The model

One row per real thing. Facts record what happened. Dimensions describe the things the facts point at. The build checks every foreign key.

| Table | Grain | Rows |
|---|---|---|
| `dim_business` | one business | 3 |
| `dim_user` | one person, after dropping duplicate ids | 800 |
| `dim_creator` | one creator | 40 |
| `dim_content` | one title | 300 |
| `fct_subscription` | one subscription, not one person, because a person can hold more than one | 843 |
| `fct_engagement_event` | one event | 6,000 |

Only MakerHarbor content has a creator. PageGarden and GatherSquare titles stay unattributed, with a null creator, rather than a made-up one. An event with no title stays on the event fact and is left out of content counts.

Marts are SQL files in `data/marts/sql/`. A file named `mart_*` is published as a CSV and as JSON for the dashboard. `int_*` and `eph_*` files are built as views and are not published.

- `eph_user_info` is one row per person with an active, non-test subscription, with their country, age band, acquisition channel, device, and subscription counts.
- `mart_user_info_counts` is the score cards.
- `mart_user_qtr_counts` is subscriptions and cancellations by quarter. It reads `int_user_qtr_counts`, the quarterly roll-up of the daily counts.
- `mart_growth_qtr_counts` adds the net subscriptions still in place at the end of each quarter and the quarterly churn rate. Churn rate is a quarter's cancellations divided by the net subscriptions at the end of the previous quarter. It counts subscriptions, not people, and it counts paused, trialing, and unknown-status subscriptions as in place, so the net total is larger than the Active Subscriptions score card. The first quarter has no rate, and the last quarter is partial.
- `mart_user_share_*` is one row per value of a column, with a distinct-user count and its share. Adding a table is one line in `USER_SHARE_CUTS` in `pipeline/user_share.py`. There is no SQL file per table.
- `mart_content_engagement` is one row per title, with completes, opens, downloads, and total engagements. Test-account events are excluded.

A reader uses the dashboard. Someone checking a number reads the SQL for that mart and the model table it came from. Both see the same rows, because the page is the mart.
