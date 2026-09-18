# Layer 3: the listings snapshot

A parent wants to know what a family-sized home costs near the school right now, to buy and to
rent. The assessed values in `@tbl-cost` are a lagging proxy; this section shows a handful of
real, current listings. It is a snapshot, not a statistic, and the post must say so.

## What is allowed

- Web search (the `WebSearch` tool) for current listings, then opening **only the individual
  listing pages you will quote** (at most five for sale and five for rent) to confirm price,
  bedrooms and type.
- Quoting, per listing: price, bedrooms, property type, street or sector, the link, and the
  date seen. Nothing else is stored.
- Attribution: "Listings as seen on Centris.ca on <date>" (or DuProprio.com, Realtor.ca).

## What is not allowed

- Automated or repeated fetching of Centris search results, pagination, or any scraping
  script. Centris pages are copyrighted and their terms forbid bulk use; the project brief
  records this decision.
- Storing listing data in `data/`, or quoting more than the handful shown.
- Presenting listing prices as a median or a market rate. The Centris statistics tool's
  borough medians may be quoted separately, by hand, with attribution, if the user asks.

## Procedure

1. Name the search area from the anchor: the borough and the neighbourhood the school's site
   or borough page uses (e.g. "Le Plateau-Mont-Royal", "Villeray", "Tétreaultville",
   "Pointe-Saint-Charles"). Use the anchor the user chose in Layer 1 (permanent or temporary
   site).
2. Search, in French and English, e.g.:
   - `site:centris.ca <neighbourhood> 3 chambres à vendre`
   - `site:centris.ca <neighbourhood> 3 chambres à louer`
   - `centris <neighbourhood> "3 chambres" plex OR condo OR maison`
   - `duproprio <neighbourhood> 3 chambres` (fallback for sale)
   - `realtor.ca <neighbourhood> 3 bedroom rent` (fallback for rent)
3. Pick 3 to 5 per side that are within about the zone radius of the anchor and have at least
   three bedrooms. Prefer variety of type (plex unit, condo, house) over the cheapest.
4. Open each chosen listing once (`WebFetch`) to confirm the figures; if a page will not load,
   quote only what the search snippet showed and mark it `unverified`.
5. Record the date seen (today) and the source site per listing.

## Table format for the post

```markdown
::: {.column-page}
| Type | Bedrooms | Street or sector | Asking price | Source, date seen |
|:---|---:|:---|---:|:---|
| Plex unit (upper) | 3 | rue X, near the school | $749,000 | [Centris](https://…), 2026-09-18 |

: For sale, 3+ bedrooms, within about 1 km of the anchor {#tbl-for-sale}
:::

::: {.column-page}
| Type | Bedrooms | Street or sector | Monthly rent | Source, date seen |
|:---|---:|:---|---:|:---|

: For rent, 3+ bedrooms, within about 1 km of the anchor {#tbl-for-rent}
:::
```

Follow with a `callout-warning` titled "Listings expire": these are the listings found on the
date shown, chosen for variety, not a sample; prices are asking prices; the section is not
refreshed when the post is republished. If fewer than three were found on one side, say so in
the caption and the callout.
