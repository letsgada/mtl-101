# MTL-101 — Project Brief

## What this is

A tool to help a parent pick a Montreal neighborhood by working *backwards* from school quality — instead of "which school serves my address," the question is "which school do I want, and therefore where should I live." Grew out of a manual research session; this brief summarizes what was learned and how to build it.

**Scope**: Francophone public elementary schools on the island of Montreal only. Explicitly excludes West Island, South Shore, and Laval. Three school service centres (CSS) are in play:
- **CSSDM** (Centre de services scolaire de Montréal) — central boroughs: Plateau, Rosemont, Villeray, Ahuntsic-Cartierville, Ville-Marie, Sud-Ouest, Côte-des-Neiges–NDG, part of Mercier-Hochelaga
- **CSS Marguerite-Bourgeoys (CSSMB)** — Verdun, Outremont, LaSalle, Lachine, plus West Island (note: CSSMB territory is *not* uniformly excluded — only its West Island portion is)
- **CSS Pointe-de-l'Île (CSSPI)** — east end: Anjou, Saint-Léonard, Montréal-Nord, Rivière-des-Prairies–Pointe-aux-Trembles

## Recommended architecture: skill, not a standalone script/app

The deterministic parts of this problem (structured data lookups) are mostly already solved by existing tools — see below. What's *not* solved is synthesis: reconciling zone lookups against socioeconomic data, catching mid-renovation relocations, disambiguating same-named schools across different boards, knowing which admission model applies to which program type. That's judgment work applied to messy, inconsistent government sources — a poor fit for a brittle fixed pipeline, a good fit for a skill that knows where to look and how to interpret what it finds, calling out to small scripts only for the genuinely clean structured-data fetches.

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

## Open questions before building

1. Does the Ministry's interactive map actually expose school-level (not just board-level) catchment boundaries as downloadable geospatial data?
2. Do CSSMB and CSSPI have finder tools equivalent to CSSDM's?
3. Is CGTSIM data worth the PDF-parsing effort, or should v1 skip it entirely and rely on MEQ IMSE alone?
4. How to keep per-school program/admission details from going stale — scheduled re-scrape? User-triggered refresh only?
