# MTL-101 — Project Brief

## What this is

A tool to help a parent pick a Montreal neighborhood by working *backwards* from school quality — instead of "which school serves my address," the question is "which school do I want, and therefore where should I live." Grew out of a manual research session; this brief summarizes what was learned and how to build it.

**Scope**: Francophone public elementary schools on the island of Montreal only. Explicitly excludes West Island, South Shore, and Laval. Three school service centres (CSS) are in play:
- **CSSDM** (Centre de services scolaire de Montréal) — central boroughs: Plateau, Rosemont, Villeray, Ahuntsic-Cartierville, Ville-Marie, Sud-Ouest, Côte-des-Neiges–NDG, part of Mercier-Hochelaga
- **CSS Marguerite-Bourgeoys (CSSMB)** — Verdun, Outremont, LaSalle, Lachine, plus West Island (note: CSSMB territory is *not* uniformly excluded — only its West Island portion is)
- **CSS Pointe-de-l'Île (CSSPI)** — east end: Anjou, Saint-Léonard, Montréal-Nord, Rivière-des-Prairies–Pointe-aux-Trembles

## Recommended architecture: skill, not a standalone script/app

The deterministic parts of this problem (structured data lookups) are mostly already solved by existing tools — see below. What's *not* solved is synthesis: reconciling zone lookups against socioeconomic data and against neighbourhood-level crime, housing, tax, census and amenity data (Layer 2 below), catching mid-renovation relocations, disambiguating same-named schools across different boards, knowing which admission model applies to which program type. That's judgment work applied to messy, inconsistent government sources — a poor fit for a brittle fixed pipeline, a good fit for a skill that knows where to look and how to interpret what it finds, calling out to small scripts only for the genuinely clean structured-data fetches.

**Suggested structure**: one skill carrying the domain knowledge below + a `scripts/` folder with a couple of narrow, deterministic helpers (CSV/GeoJSON fetch + filter for MEQ data; geocode-address helper). Avoid trying to build a general-purpose zone-boundary geocoder from scratch — check the existing government tools first (next section).

## Don't rebuild these — check/reuse first

- **CSSDM's own school finder**: `cssdm.gouv.qc.ca/trouver-une-ecole/` — searchable by postal code, school name, level, subject. Confirm whether CSSMB and CSSPI have equivalents.
- **Quebec Ministry's interactive map of all school networks**: `infogeo.education.gouv.qc.ca` ("Carte interactive des réseaux d'enseignement du Québec"). Its docs claim the underlying geospatial territory data is downloadable via the map tool and via Données Québec. **Unverified**: whether this includes fine-grained per-school catchment boundaries or only board-level (CSS/CS) territory outlines. Check this before spending time digitizing individual schools' PDF zone maps by hand.
- **Third-party aggregator**: Montreal Tips runs a "School Zone Finder" page (CSSDM/EMSB/CSMB) plus Bill 101 language-eligibility context — mostly a link directory, but confirms the fragmentation problem is known and partially addressed elsewhere.

## Data sources

| Source | Format | Notes |
|---|---|---|
| MEQ Indices de défavorisation (IMSE/SFR) | CSV, GeoJSON, SHP, GPKG, FGDB, XLSX | Open on Données Québec, refreshed annually, per-school and per-"unité de peuplement." Direct CSV download confirmed working. This is the clean, reliable pipeline. |
| CGTSIM school success / deprivation map | PDF only | No API, no CSV found. French only. Related to but distinct from MEQ's IMSE — CGTSIM calculates its own index for its own tax-redistribution funding decisions. Treat as optional/low-priority enrichment; PDF parsing is fragile and not guaranteed to stay consistent year to year. |
| Per-school program/admission details | HTML, scattered across ~180 individual CSSDM school sites + CSSMB/CSSPI sites | No structured source found; this is manual/scripted scraping per school, prone to going stale (e.g., mid-renovation relocations, address changes). |

## Domain knowledge to encode in the skill

**IMSE**: Ministry-calculated socioeconomic index, NOT a direct measure of academic performance. Built from mother's education level (2/3 weight) and parental employment (1/3 weight), assigned by home address ("unité de peuplement"), averaged per school, ranked into deciles 1 (most advantaged) to 10 (most disadvantaged). Deciles 8–10 = officially "milieu défavorisé," gets extra funding/smaller classes. Useful as a rough proxy in the absence of any Quebec elementary-school academic ranking (Fraser Institute only ranks Quebec *secondary* schools).

**Programs found in CSSDM's "volets particuliers" system**: alternative pedagogy (Freinet, not Montessori — Montessori exists only in the private system), international education (IB), gifted education, science enrichment, music/arts vocation. Admission mechanics vary by category:
- *Selective/dossier-based* (e.g., École Saint-Barthélemy IB PYP, École internationale de Montréal): grades, teacher recommendation, parent questionnaire, CSSDM-residency requirement.
- *Non-selective lottery within a defined catchment* (e.g., École La Vérendrye IB PYP in Tétreaultville): no exam, lottery only if oversubscribed.
- *CSSDM-wide lottery, no academic screening* (e.g., École FACE since 2014): complete application by end of October, sibling priority, then random draw.
- *Neighborhood/"libre choix"*: default assignment by address, but CSSDM allows applying outside your zone if space remains, with zone residents and siblings getting priority.

**Known specific schools from this research** (useful as seed/test data):
- IB PYP: École Saint-Barthélemy (Villeray), École internationale de Montréal (NDG, mid-renovation relocation to nearby transitional site), École La Vérendrye (Tétreaultville, non-selective)
- Freinet alternative: École Charles-Lemoyne (Pointe-Saint-Charles, environmental focus), École Saint-Nom-de-Jésus (Hochelaga-Maisonneuve, 60/40 catchment split lottery)
- Arts/bilingual, non-selective since 2014: École F.A.C.E. (relocated to Christophe-Colomb during 2025 building renovation)

**Caveats worth surfacing to the user for any school**: check for active building renovations/relocations (common across CSSDM's aging stock — École Ahuntsic is a live example, mid-split across two temporary buildings as of this school year), and note that a borough's general reputation can mask wide IMSE variation between specific schools within it (Villeray ranged from decile 3 to decile 10 depending on the exact school).

## Layer 2: evaluating the neighbourhood once the school is chosen

Layer 1 answers "which school, therefore which zone." Layer 2 asks whether that zone is a place the family wants to live: crime, income and who lives there, what housing costs to buy, rent and hold (assessed values, tax bills), childcare, parks, transit, the child's walk to school, and which secondary school the zone feeds later.

The candidate sources first proposed were SPVM's "Vue sur la sécurité publique", Centraide's neighbourhood profiles, CourtiConnect/Immovision price pages, Immovision's property-tax calculator, and school ratings (Fraser Institute or MEQ). Checked 2026-09-17: the SPVM tool is only a viewer over the city's open data; Centraide's profiles are narrative pages over a French-only Power BI dashboard refreshed every three years; the price and tax sites are commercial front-ends over public records; and no elementary-school rating exists (Fraser ranks Quebec *secondary* schools only, the MEQ "Tableau de bord" is a Power BI embed at CSS level with no CSV). Every one has an open, structured equivalent, mostly on `donnees.montreal.ca` (CC-BY 4.0), Données Québec (CC-BY 4.0) and Statistics Canada (Open Licence), which fits the "narrow deterministic scripts" model far better than scraping broker sites.

### Data sources (Layer 2)

**Core: the original five, replaced by open equivalents**

| Source | Format | Notes |
|---|---|---|
| Ville de Montréal — *Actes criminels* (`actes-criminels`) | CSV, GeoJSON | One row per SPVM-reported incident since 2015-01-01: `CATEGORIE`, `DATE`, `QUART`, `PDQ`, `X`/`Y` (MTM8, SRID 2950) plus lat/long. Positions obfuscated to the nearest intersection; the city states these are *not* official statistics. Official monthly counts by PDQ: `bilan-mensuel-criminalite` (CSV). PDQ polygons: `limites-pdq-spvm` (GeoJSON; PDQ 50 is the métro and has no territory; 21 and 22 merged). |
| Ville de Montréal — *Imposition annuelle de taxes municipales* (`taxes-municipales`) | CSV × 20 (one per borough, 33–254 MB) | 2021–2026, one row per tax line per unit: civic address, `ID_UEV`, **valeur imposable**, rate, amount, borough. This is both the price proxy (assessed value; the 2026–2028 roll reflects the July 2024 market) and the actual tax bill (base + borough services/investment taxes + water + ARTM). Initial issuance only; later corrections are not reflected. Replaces both Immovision and CourtiConnect. |
| Ville de Montréal — *Unités d'évaluation foncière* (`unites-evaluation-fonciere`) | CSV, GeoJSON, SHP (weekly) | Parcel geometry and attributes (`CODE_UTILISATION` CUBF, `ANNEE_CONSTRUCTION`, `NOMBRE_LOGEMENT`, `CATEGORIE_UEF` regular/condo). **Contains no values**; join to the tax-bill CSVs on `ID_UEV`. |
| Ville de Montréal — tax rates | PDF ("Taux de taxes 2026" on montreal.ca) | The open dataset `taux-de-taxation-et-tarification` is stale (2019–2020 only). Rates are already embedded per line in the tax-bill CSVs, so the PDF is documentation, not a pipeline input. |
| Statistics Canada — 2021 Census Profile (98-401-X) | CSV bulk per geography level; Web Data Service API | Dissemination-area (DA) level: median household income, low income (LIM-AT), no-diploma share, immigration, tenure, structural type. Five years old; next census releases start 2027. The city's own custom census order on `donnees.montreal.ca` is IVT (Beyond 20/20): skip. |
| Centris statistics tool; APCIQ *Baromètre résidentiel* | HTML tables; quarterly PDF | Market medians by single-family / condo / plex for 19 Montreal boroughs, sales, listings, days on market. Copyrighted: quote manually with attribution as a cross-check on assessed values, never bulk-scrape. |
| Centraide — *Portraits de territoire* | HTML + Power BI (French only) | Read for narrative context on a neighbourhood; not a data source. |

**Additions: high decision value for a parent, low marginal effort**

| Source | Format | Notes |
|---|---|---|
| Statistics Canada — Census Profile, family variables | CSV, DA | Children 0–14, families with children, population growth 2016→2021, movers in the last five years, language spoken at home. Same DA pipeline as income, near-zero marginal cost. Language at home is *not* Bill 101 eligibility (a parental-schooling test): say so. |
| `unites-evaluation-fonciere`, housing-stock view | CSV/GeoJSON | Share of plex / condo / single-family from CUBF (needs a lookup table), median building age, dwelling count. Also the denominator for every per-dwelling rate. |
| Données Québec — *Collisions routières* (`vmtl-collisions-routieres`) | CSV, GeoJSON | SAAQ-sourced, lat/long, pedestrian and cyclist death/injury counts. Count within 500 m of the school: the one safety metric about the child's walk rather than the borough. Pool 5–10 years; the city's own copy stops at 2021. Excludes the highway network. |
| Ministère de la Famille — *Liste des CPE et garderies en fonction* | CSV (monthly) | `NOM`, `TYPE` (CPE/GARD), `ADRESSE`, `CODE_POSTAL`, `PLACE_TOTAL`, `PLACE_TOTAL_POUPON`, `SUBV`. **No coordinates**: geocode ~3,000 island addresses. Metric: subsidised places per child 0–4 within 1 km. Waitlist data (La Place 0-5) does not exist as open data. |
| Ville de Montréal — *Règle 3-30-300* (`regle-3-30-30-pour-le-suivi-de-l-acces-aux-espaces-verts`) | SHP, GeoJSON | The city has already computed pedestrian access to a park within 300 m / 1 km and canopy by DA; spatial join only. Ville de Montréal territory only (excludes related cities). Park polygons themselves: `grands-parcs-parcs-d-arrondissements-et-espaces-publics`; playgrounds, pools, splash pads: `installations-recreatives-sportives-et-culturelles`. |
| INSPQ — *Îlots de chaleur urbains 2020–2022* | GeoTIFF, GPKG, SHP (Données Québec / ouvert.canada.ca) | 15 m raster, classes 1–9. Share of zone in classes 8–9. Surface temperature modelled from Landsat, not air temperature. |
| STM — static GTFS (`stm-horaires-planifies-et-trajets-des-bus-et-du-metro`), line traces | GTFS, SHP | Weekday 7–9 am departures per km² from `stop_times`, distance to nearest métro entrance. Separates "a bus hourly" from "two frequent lines". REM geometry exists only via a Transitland mirror, not an official Quebec portal. |
| Ville de Montréal — `pistes-cyclables`, `reseau-express-velo` | GeoJSON, SHP | Km of *protected* path per km² and distance to a REV axis. Filter by infrastructure type; painted lanes overstate safety. |
| CSS board resolutions — elementary → secondary feeder | PDF (e.g. CSSDM CA-10-202511-58, Annexe I, >10 MB) | **Which public secondary school the zone feeds.** The highest-value single fact for a ten-year decision and the only one with no substitute. Budget as a hand-built ~180-row lookup refreshed each November, not a pipeline. CSSMB/CSSPI equivalents unverified. Only once the feeder is known does a Fraser secondary rank become quotable, in prose, with the caveat that it tracks intake socioeconomics. |
| CMHC — Rental Market Survey, Montréal CMA zones | HTML with Excel/CSV export (annual, October) | Average rent, vacancy and turnover by CMHC zone (aggregates of census tracts, e.g. "Plateau-Mont-Royal"). Only credible rent benchmark for a family renting first. Needs a hand-built CT→zone crosswalk (no official zone shapefile found); purpose-built rentals only, so it misses most plex and condo rentals. |

**Composite indices: quote as independent cross-checks, never as inputs to a score of our own**

| Source | Format | Notes |
|---|---|---|
| Ville de Montréal — *Indice d'équité des milieux de vie* (`indice-equite-milieux-vie`) | CSV, GeoJSON, methodology PDF, dictionary XLSX | 2026 edition, census-tract level, six dimensions including urban safety and access to culture/sport, cumulative score 0–6 where high means more vulnerable. Co-built with the DRSP. |
| INSPQ — *Indice de défavorisation du Québec 2021* (`indice-de-defavorisation-du-quebec-2021`) | GeoJSON, SHP | Pampalon material and social deprivation quintiles by DA. Residence-weighted, unlike IMSE (attendance-weighted). The social axis runs high in the Plateau and Villeray for lone-parent and living-alone reasons that do not mean "bad for children"; report the two axes separately. |
| Statistics Canada — *Proximity Measures Database 2021* (17-26-0002) | CSV (`pmd-eng.zip`) | Ten amenity indices (transit, grocery, childcare, primary school, parks, health, library, …) 0–1 on a national scale at dissemination-*block* level. Saturates near 1.0 in central boroughs, so it discriminates poorly inside CSSDM territory; useful for the eastern and northern quartiers. |

**Optional flags (cheap; label as proxies, never as conditions)**

- `requete-311`: requests per 1,000 dwellings by category (snow, cleanliness, noise, rodents). Measures propensity to complain as much as conditions; normalise within borough.
- Inside Airbnb (CSV, CC-BY): entire-home listings per 100 dwellings, a flag for family-rental supply being hollowed out. Points jittered ~150 m.
- INSPQ food-desert / distance-to-food-store index (Données Québec, DA). Report the raw distance; the "desert" flag blends in material deprivation already covered by IMSE.
- `permis-construction`: permits and declared cost per 1,000 dwellings over three years (renovation pressure). 73% geocoded to parcel.
- MELCCFP *Répertoire des terrains contaminés* (GTC): active sites in or near the zone. Not exhaustive.
- `locaux-commerciaux`: food-retail mix and storefront vacancy on the zone's commercial streets.

**Checked and skipped**

- Walk Score: free tier forbids batch or offline use, which is exactly what comparing zones needs.
- Canadian Index of Multiple Deprivation: overlaps Pampalon, and its "ethno-cultural composition" dimension is inappropriate framing for a parent-facing tool.
- ISQ *indice de vitalité économique*: municipality level only; Montreal is one unit.
- Voter turnout (`resultats-detailles`): the file has votes cast but not electors registered, so turnout is not computable.
- Scraping Fraser: pages return 403 to automated fetch, licence unclear, and a raw exam ranking mostly tracks intake socioeconomics, a point the tool should make in prose, not with a number.
- Childcare waitlists, GMF/pediatric wait times, YUL noise contours, road-noise layers, gentrification indices, TAL or citizen rent registries: none exist as downloadable data.
- RSQA air quality: eleven stations for the island cannot separate two school zones.

### Geography: nothing nests

School zones, PDQs (about 30 on the island), boroughs (19), census DAs and tracts, CMHC zones and Centris "boroughs" all cut the island differently. **Confirmed 2026-09-17:** the MEQ geospatial download (`quebec.ca/education/cartes-donnees-geographiques`) contains CSS territory boundaries and school point locations only, no per-school catchment polygons, for elementary or secondary. Zone polygons therefore come from the CSS finders and PDF zone maps (open question 1, now answered), and the tool needs a fallback geometry: a 1.0–1.5 km network buffer around the school point, or the set of DAs whose centroids fall inside the zone.

Aggregation rule: anything with point, parcel, DA or raster granularity (incidents, tax bills, census, canopy, heat, collisions, childcare, GTFS stops) is aggregated to the zone polygon or its fallback. Anything inherently borough-level (Centris medians, tax rates) is reported at borough level and labelled as such, echoing the caveat that a borough's average masks intra-borough variation. Population denominators come from census DAs; dwelling denominators from the *unités d'évaluation* file.

### Scoring stance

MTL-101 does **not** invent a composite livability score. It shows a short dashboard of roughly ten headline metrics, each as the zone's decile against the island-wide distribution (which maps onto the site's `decile-low / decile-mid / decile-high` classes and the one-emphasis-colour rule), with the IEMV and Pampalon indices quoted alongside as independent composites. Weighting is the parent's job; the tool's job is comparable, sourced numbers.

### Caveats to surface with every Layer 2 number

- Crime is a rate per 1,000 residents, split violent / property / vehicle, never a raw count. Ville-Marie and the Plateau are inflated by non-resident footfall; because positions are obfuscated to intersections, radius counts under ~300 m are noise.
- Assessed value lags the market by about 18 months and the roll is triennial. Report by property type (regular vs condo, single-family vs plex), never a single median. Tax bills are the initial issuance; compare like with like.
- Census 2021 is five years old; DA-level ratios are randomly rounded and noisy in small DAs. Centraide profiles are three-yearly and narrative.
- **Do not double count residence income against IMSE.** IMSE encodes parental education and employment of the school's *enrolled* population; census income and Pampalon describe the zone's *residents*. They diverge where choice programs draw from outside the zone or where families leave for the private system. Report both and say why they differ.
- Collisions and 311 requests are small-count and behaviour-dependent: pool years, normalise, and label them as proxies.

### Scripts implied (still not built)

- `fetch_open_data`: download and cache the datasets above by slug (Ville CKAN, Données Québec CKAN, StatCan zips), with a manifest of dates fetched.
- `census_da`: filter the StatCan DA profile to the Montréal CSD and the selected variables.
- `geocode`: the address helper already suggested above, now also needed for the CPE list.
- `zone_stats`: given a zone polygon or a school point plus buffer, return every Tier B metric as value plus island decile, and the IEMV / Pampalon values for the intersecting tracts and DAs.

## Open questions before building

1. ~~Does the Ministry's interactive map expose school-level catchment boundaries?~~ **Answered 2026-09-17: no.** The download has CSS territory boundaries and school points only. Zone polygons must come from the CSS finders and PDF zone maps; see the fallback geometry under Layer 2.
2. Do CSSMB and CSSPI have finder tools equivalent to CSSDM's?
3. Is CGTSIM data worth the PDF-parsing effort, or should v1 skip it entirely and rely on MEQ IMSE alone?
4. How to keep per-school program/admission details from going stale — scheduled re-scrape? User-triggered refresh only?
5. When no zone polygon is available, which fallback: a network buffer (what radius?) or the set of DAs whose centroids fall in the zone?
6. Fetch the 20 tax-bill CSVs (up to 254 MB each) on demand, or pre-aggregate them once a year into a zone-ready table?
7. Centris terms of use: is a manual borough-median quote with attribution acceptable, and is any automated fetch off the table?
8. Who maintains the elementary → secondary feeder lookup (CSSDM board resolution each November; CSSMB and CSSPI sources unverified)?
