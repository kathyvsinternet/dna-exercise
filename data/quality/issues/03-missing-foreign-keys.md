# Missing foreign keys

## What we found

The blank keys are blank cells. No content or event row points at an id that is absent from its parent table.

`creator_id` is blank on 195 of 300 content items. That is every PageGarden item (BIZ_1, 112) and every GatherSquare item (BIZ_2, 83). Every MakerHarbor item (BIZ_3, 105) has a creator.

The creator table has 40 creators: 37 on MakerHarbor and 3 on PageGarden (`CR_0002`, `CR_0012`, `CR_0035`). None of the PageGarden content rows use those three creators. GatherSquare has no creators.

`content_id` is blank on 323 of 6,000 events. The blanks cover four event types completely:

| Event type | Events | Blank `content_id` |
|---|---|---|
| `search_query` | 76 | 76 |
| `page_view` | 76 | 76 |
| `subscription_start` | 84 | 84 |
| `subscription_cancel` | 85 | 85 |
| `glitch_in_the_matrix` | 40 | 2 |

The other 5,639 events, including opens, completes, likes, shares, comments, and downloads, all have a content id.

## Treatment

Keep the row. Store a null `creator_id` or `content_id`.

PageGarden and GatherSquare content stays unattributed. The three PageGarden creators stay on `dim_creator` with no content attached. Search, page-view, and subscription events stay on `fct_engagement_event` without a content id, because those events are not about one title.

`mart_business` counts engagement through the content item's business. Events with no content id are left out of that count. A user can subscribe to more than one business, and those events have no business id, so assigning them to a business would be a guess. They remain on the fact table: 304 of them belong to non-test accounts.

## Check to enforce

Fail if a non-null `creator_id` or `content_id` is missing from its dimension. Alert if a MakerHarbor content item has no creator, if a search, page-view, or subscription event gains a content id, or if an open, complete, like, share, comment, or download is missing one. That pattern would be new.
