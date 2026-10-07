# Layer 3 for a quartier: listings per school

Same rules as `school-report/references/listings.md` (web search only, open a listing page at
most once to confirm, quote price, bedrooms, type, street or sector, link and date seen, never
scrape, never store beyond what is quoted, never present as a statistic). What differs: the
search is done **per school**, the volume is **2 to 3 per side per school**, and every listing
is **attributed to the school whose building is nearest** so it appears once even though
neighbouring kilometres overlap.

## The CSV the skill fills

`data/derived/area_<slug>_listings.csv`, one row per listing:

```
side,type,bedrooms,street_or_sector,address,price,url,source,date_seen,school_hint
buy,Condo,3,"rue Lajeunesse, near Jarry","7272 rue Lajeunesse",539000,https://…,Centris,2026-10-07,762107
rent,Apartment,3,"rue Drolet","7372 rue Drolet",2350,https://…,Centris,2026-10-07,762107
```

- `side` is `buy` or `rent`; `price` is the asking price or the monthly rent, digits only.
- `address` is what the listing shows (civic number and street); it is geocoded by
  `listings_assign.py` through Nominatim (cached, one request per second). When a listing only
  gives a sector, leave `address` empty and fill `school_hint` with the code of the school it
  was searched for; the script then uses that school.
- `url` is the listing page when it has one, otherwise the neighbourhood search page it was
  read on; duplicates by `url` are dropped, so prefer listing pages.
- `source` is the site name (Centris, DuProprio, Realtor.ca).

## Searching per school

Use the school's address and the quartier name, in French and English, for example
`site:centris.ca Villeray "3 chambres" à vendre rue Sagard OR Saint-Barthélemy`, then the
rent equivalent. Aim for variety of type across the quartier rather than the cheapest. Stop at
3 per side per school; fewer is fine and the tables say which schools got none.

## In the post

`listings_assign.py` emits `tbl-for-sale` and `tbl-for-rent` grouped by school, plus a line
naming the schools with no listing on each side. Follow them with the `callout-warning`
"Listings expire" from the school-report template, adapted: the date, "chosen for variety",
"asking prices", "each listing shown once under its nearest school", "not refreshed".
