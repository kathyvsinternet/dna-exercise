# Test accounts and sentinel values

## What we found

Test accounts and planted values are separate problems.

After the duplicate drop, 40 of 800 users have `is_test_account_flag = True`. Those users have 39 subscriptions and 308 engagement events. The other 760 users are kept in the metrics.

The planted values below also appear on users who are not flagged as test accounts. Only 1 of the 20 `TEST_STATUS_DO_NOT_USE` subscriptions belongs to a test account.

| Location | Value | Rows, after the duplicate drop |
|---|---|---|
| `acquisition_channel` | `influencer_TEST_CAMPAIGN` | 20 users |
| `acquisition_channel` | `carrier_pigeon` | 20 users |
| `acquisition_channel` | blank | 20 users |
| `age_band` | `999` | 8 users |
| `age_band` | `N/A` | 20 users |
| `age_band` | blank | 20 users |
| `primary_device` | `smart_toaster` | 20 users, and 50 events |
| `primary_device` | `unknown_device` | 20 users |
| `content_type` | `TEST_TYPE` | 8 content items |
| subscription `status` | `TEST_STATUS_DO_NOT_USE` | 20 subscriptions |
| `event_type` | `glitch_in_the_matrix` | 40 events |

Two odd-looking values are part of the synthetic world, so they stay as they are:

- Fictional countries sit beside real ones: Altara, Eloria, Freelandia, Genora, Gondale, Hogglewick, Latoria, Nearia, Wavanda, Wondervale, and Zubria. Nearia and Wavanda are also headquarters planets.
- `lifetime_deal_fake` is the billing cycle on 148 subscriptions. It is a populated plan attribute. The `_fake` suffix matches other synthetic labels in this dataset.

## Treatment

Keep every row.

- `is_test_account` stays on `dim_user` and is copied onto both fact tables. Marts leave test accounts out. The fact tables still contain them, so the exclusion can be audited.
- Map each planted token in the table above to `unknown` on the governed column. Keep the original value in the matching `*_raw` column.
- A blank age band or acquisition channel also becomes `unknown`. The raw column shows whether the source was blank, `N/A`, `999`, or a planted token.
- Leave fictional countries and `lifetime_deal_fake` unchanged.

## Check to enforce

Fail the build if a mart is built from a test account. Fail if a governed column still contains one of the planted tokens in the table. A new token in a low-cardinality column should appear in `profile.json` and be classified before it is allowed into a governed column.
