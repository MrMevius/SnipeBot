## Context

Marktplaats has no public API for consumers. Its web client uses a JSON search endpoint (`/lrp/api/search`) that accepts the same search request as the result pages. Result-page URLs encode filters in two places: the path (`/l/<category>/<subcategory>/f/<slug>/<id>/`, `/q/<query>/`), which the server resolves, and the `#` fragment (`f:<ids>|<attr>From:<n>|<attr>To:<n>|postcode:…|distanceMeters:…|q:…`), which only the browser reads.

## Goals / Non-goals

**Goals:**
- Paste-a-URL setup that supports every Marktplaats filter without rebuilding them in SnipeBot.
- Notify quickly (~10 minutes) and only for listings that are really new, plus price drops.
- Make URL interpretation verifiable by the user before saving.

**Non-goals:**
- Building a filter form for brands/models in SnipeBot.
- Quiet hours, favourites/hiding listings, multi-page crawling.
- Notifications about listings that disappear.

## Decisions

1. **URL resolution: server for the path, SnipeBot for the fragment.**
   The pasted URL without fragment is fetched once; the page's `__NEXT_DATA__` contains `searchRequestAndResponse.searchRequest.originalRequest` with category ids, attribute ids, ranges, query and distance. The fragment is parsed with the same rules as the Marktplaats client (`q`, `f`, `<attr>From/To`, `offeredSince`, `ta`, `postcode`, `distanceMeters`; sort/view keys ignored; unknown keys reported as warnings). Subcategories must be sent as `l2CategoryIds[]` (the singular parameter is silently ignored).

2. **Preview with labels and count.** The preview runs the resolved request against the search endpoint and turns facet labels into readable lines ("Model: Golf", "Bouwjaar: vanaf 2018") plus the total count, so mistakes are visible against marktplaats.nl.

3. **Seller filter via the `advertiser` facet.** The chosen seller type is added as the `advertiser` attribute id taken from the facets (ids are not hard-coded). `all` keeps whatever advertiser filter the pasted URL already contains. Categories without that facet reject a non-`all` seller filter.

4. **New-listing detection uses an id watermark.** Paid "Dagtopper" ads are bumped to the top of the newest-first ordering daily, so an unseen id is not necessarily new. Listing ids (`m<number>`) increase over time. An unseen listing is new when its id is above the highest id known for the search, or when the previous check covered the complete result set (total ≤ fetched; then any unseen listing has just entered the search, e.g. after a price cut). Other unseen listings are recorded without an alert.

5. **Baseline.** The first successful check (and the first check after changing keywords or seller type) records listings silently (`from_baseline`).

6. **Exclude keywords** are matched case-insensitively against title and the (truncated) description from the search response. Excluded listings are not stored.

7. **Alert safety.** Dedup per listing/kind/key (`new_listing`; `price_drop|old|new`). At most 10 alerts per search per check; the rest is summarised in one message. Failures back off with the existing retry settings (no dead-lettering; the search stays active and shows the error).

8. **Listings gone.** Only when the fetched page held the complete result set are missing listings marked `gone_at` (shown greyed in the UI, no alert).

9. **Plain HTTP client.** `urllib` with an honest `SnipeBot/0.1` user agent works for both the page and the JSON endpoint; no Playwright. One request per search per interval, page size 100, newest first.

## Risks / Trade-offs

- Marktplaats can change the page data or endpoint. Parsing failures surface as `parse_error` in the UI/logs and back off; no alerts are sent from bad data.
- Rate limiting/blocking (403/429) is reported as `blocked` and backs off up to the configured maximum.
- With large result sets (> 100), an older listing that newly enters the search (e.g. price cut into range) is recorded without alert. Narrow searches (≤ 100 results) do alert on those.
