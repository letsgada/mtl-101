---
name: quartier-report
description: Produce an MTL-101 quartier report as a Quarto post comparing every in-scope francophone public elementary school in a named Montreal neighbourhood — the city's Quartiers sociologiques polygon (e.g. Villeray without Parc-Extension and Saint-Michel) plus schools within 300 m of its boundary, with each school's program, admission model and MEQ IMSE/SFR deciles, the kilometre around each building across the same metric tables as the school report (schools as rows, the whole quartier and the island median as reference rows), an interactive map of the area with every school and métro station, and per-school snapshots of 3+ bedroom listings. Use it whenever the user says "quartier report", "/quartier-report", "compare the schools in <quartier>", "which schools are in Villeray", "rapport de quartier", "all the schools around <neighbourhood>", or names a Montreal neighbourhood and asks about its schools. It resolves the area with the repo's scripts, asks when a name is ambiguous and confirms the school set, drafts through quarto-writeup with pre-filled answers, lints and renders, and never commits or pushes without a yes.
---

# Quartier report

One neighbourhood in, every school in it compared, one post out. The report has the same
three layers as `school-report` but turned sideways: **the schools** (Layer 1 from files only),
**the kilometres compared** (Layer 2, schools as rows), and **living there now** (Layer 3,
listings attributed to the nearest school). The deliverable is a lint-clean
`posts/<quartier-slug>-schools.qmd` that renders; committing is offered, never done unprompted.

Read `project_brief.md` before the first run in a session, and `school-report/SKILL.md` for
the rules this skill shares with it. The rules below override everything else, exactly as there:
never invent a school fact; ask, do not assume; no scraping; no composite score, no verdicts;
every number from an artifact produced in this run; do not edit the symlinked skills.

## What "the area" means

- A **quartier** from the city's *Quartiers sociologiques* file (32 polygons over the 19
  boroughs; Villeray, Parc-Extension and Saint-Michel are separate units). Exact names win over
  partial matches; a partial match that fits several quartiers is asked back.
- A name that is not a quartier but a **related city or borough** (Mont-Royal, Westmount,
  Côte-Saint-Luc, Outremont…) uses the municipality or borough polygon from the agglomeration
  limits; the post says so in its first paragraph.
- **West Island** units are refused: project scope.
- A school is **in** the area when its MEQ building lies inside the polygon; schools up to the
  **margin** (300 m by default) outside are included as **edge** schools, marked † everywhere.
- Schools whose program row says `specialised` (a mandate for pupils with disabilities,
  supraregional intake) go to the "Also in the quartier" note with their mandate and are
  excluded from the tables, together with anglophone, secondary, adult and private schools.

## Procedure

### 0. Preflight

As in `school-report` step 0, plus `data/raw/quartiers-sociologiques.geojson` and
`data/raw/pps_prive_etablissement.geojson` (fetch keys `quartiers`, `schools_private`). Carry the
90-day age warning and the fetch dates into the sources section.

### 1. Resolve the area and confirm the school set

```bash
uv run scripts/area_info.py "<quartier>" --margin 300
```

Show the user the output: the polygon source, the inside and edge schools with distance,
program, admission, IMSE/SFR, pupils and any existing report, and the out-of-scope note. Then
**ask** them to confirm the set: drop a school, change the margin, or flag a school as
specialised (write its row to `data/schools_programs.csv` with a source URL after they confirm;
`area_info.py` then moves it to the note). A school with no program row stays in with
"unknown"; do not research it unless the user asks.

### 2. Layer 1, from files only

No web research per school. `area_info.py` already carries IMSE/SFR and pupils (from
`imse.py`'s file) and the program row. Keep the IMSE caveat sentence from
`school-report/references/layer1.md` in the post.

### 3. Layer 2: tables and map

```bash
uv run scripts/zone_stats.py <all codes…> --edge <edge code> … --area data/derived/area_<slug>.geojson --format csv --out data/derived/area_<slug>.csv   # <1>
uv run scripts/report_tables.py data/derived/area_<slug>.csv --layout rows --info data/derived/area_<slug>_schools.csv --out data/derived/area_<slug>_tables.md  # <2>
uv run scripts/zone_map.py <all codes…> --edge <edge code> … --area data/derived/area_<slug>.geojson --out data/derived/area_<slug>_map.html  # <3>
```
1. one row per school (role `school` or `edge`) and one `area` row over the whole polygon; the area row's victims-within-500-m and métro-distance cells are blank by design
2. the overview table (`tbl-overview`) and the six group tables with schools as rows, the quartier row and the island median row, ▲/▼ in headers, the most favourable school shaded per column
3. the MapLibre block: polygon outline, one zone-coloured pin per school (edge dashed), stations inside; no accent pin because no school is chosen

Specialised schools are not passed to these commands. Read the Markdown view of `zone_stats.py`
once for the DA counts, IEMV coverage and tax-bill match rates to quote in the sources.

### 4. Layer 3: listings per school (`references/listings.md`)

For each school, web-search 2 to 3 for-sale and 2 to 3 for-rent 3+ bedroom listings near its
address, append them to `data/derived/area_<slug>_listings.csv` (columns in the reference), then:

```bash
uv run scripts/listings_assign.py data/derived/area_<slug>_listings.csv data/derived/area_<slug>_schools.csv --out data/derived/area_<slug>_listings.md
```

The script geocodes each address, attributes the listing to the nearest school, drops
duplicates by URL, and names the schools that received none. Same no-scraping rules as the
school report; each listing is opened at most once to confirm.

### 5. Draft through `quarto-writeup`

Invoke the `quarto-writeup` skill with the interview pre-filled from `references/interview.md`
(destination `posts/<quartier-slug>-schools.qmd`, framing, scope, examples = the confirmed
set), showing each pre-filled answer so the user can override. Draft from `assets/report.qmd`;
paste the tables, the map block and the listings tables; link each school's row to its existing
`posts/<school>-report.qmd` where one exists (`area_info.py` reports the path); keep the front
matter to the house style.

### 6. Lint, render, screenshot

As in `school-report` step 7, including the headless-browser check of the map (polygon, pins,
stations) and the shaded cells.

### 7. Hand off

Report: the file path; the area and its polygon source; the school set with who was excluded
and why; listings count and date, and which schools got none; what is `unverified`; the data
fetch dates. Offer the commit of the post and of any new `schools_programs.csv` rows through
`/commit-changes`; a dry run stops here with nothing committed.

## Files in this skill

- `assets/report.qmd` — the quartier post template.
- `references/interview.md` — pre-filled answers for the quarto-writeup interview.
- `references/listings.md` — the per-school listings procedure and the CSV columns.

Shared with `school-report`: `references/layer1.md` (vocabulary, relocation cues, the IMSE
sentence). Scripts live in `scripts/`: `area_info.py`, `zone_stats.py`, `report_tables.py`,
`zone_map.py`, `listings_assign.py`, `geocode.py`.
