---
name: school-report
description: Produce an MTL-101 school report as a Quarto post for one francophone public elementary school on the island of Montreal — the school itself (service centre, buildings, program and admission model, MEQ IMSE/SFR deciles, renovation or relocation status, links to its fondation, OPP and parent groups), the kilometre around it (census, deprivation indices, crime, road safety, housing stock, assessed values and tax bills, parks, métro access, with island deciles and an interactive map), and a dated snapshot of 3+ bedroom listings for sale and for rent. Use it whenever the user says "school report", "/school-report", "report on école X", "évalue l'école X", "what is it like around école X", "should we live near school X", or names a Montreal elementary school and asks for the neighbourhood picture. It resolves the school with the repo's scripts, asks when a name is ambiguous or the school is relocated, lets the user pick comparator schools, hands the draft to the quarto-writeup skill with pre-filled interview answers, lints and renders, and never commits or pushes without a yes.
---

# School report

One school in, one post out. The post has three layers, in this order: **the school**
(Layer 1), **the zone** (Layer 2, the `scripts/zone_stats.py` tables plus a map), and
**living there now** (Layer 3, a perishable snapshot of listings). The deliverable is a
lint-clean `posts/<slug>.qmd` that renders; committing is offered, never done unprompted.

Read `project_brief.md` before the first run in a session: it holds the domain facts this
skill relies on (IMSE is socioeconomic, not academic; admission models; the caveats that go
with every Layer 2 number; the no-composite-score stance). `CLAUDE.md` holds the run order for
the data pipeline and the house style for posts.

## Rules that override everything else

- **Never invent a school fact.** Program, admission model, buildings, renovation status and
  return dates come from a page you opened, with its URL. What you could not open is marked
  `unverified` in the post, not guessed.
- **Ask, do not assume**, in exactly these cases: the name matches several schools; the school
  is relocated or split across buildings (which address anchors the zone); a source the report
  needs is unreachable and web search gives nothing; the user's choice of comparators.
- **No scraping.** Layer 3 quotes a few listings found by web search, each with its link and
  the date seen. Never fetch listing pages in bulk, never store more than what is quoted, never
  automate Centris. The brief records this decision (open question 7).
- **No composite score, no verdicts.** Framing is "report plus cautious reading": tables carry
  the numbers with island deciles, prose says what a decile means and where zones differ, and
  never calls a zone or a school better or worse. The IMSE line always carries the
  socioeconomic-not-academic caveat.
- **Every number is recomputed from an artifact** you produced in this run (the zone_stats CSV,
  the imse.py output). Follow `quarto-writeup`'s rules for everything about the draft itself.
- **Do not edit the symlinked skills.** `quarto-writeup` and `commit-changes` live in dotfiles.

## Procedure

### 0. Preflight

Check that these exist: `data/derived/zone_stats_all.parquet`, `data/derived/taxes_2026.parquet`,
`data/derived/uev_points.parquet`, `data/derived/census_da_island.parquet`,
`data/raw/defav_ecole_prim_public.csv`, `data/raw/manifest.json`. If any is missing, print the
run order from CLAUDE.md ("Scripts (Layer 2)") and stop; the pipeline takes about ten minutes
and 3.5 GB and is the user's call. Then run any script once; `zone_stats.py` warns per dataset
older than 90 days (`--age-warn`). Do not refresh; carry the warning and the fetch dates into
the report's sources section.

### 1. Resolve the school

```bash
uv run scripts/school_info.py "<name or code>" --nearest 8 --same-program
```

- Several matches: show the list with codes and ask which one.
- Refused as out of scope (anglophone board, secondary only, West Island, off island): tell the
  user why and stop; the project's scope is the brief's.
- Keep the output: code, service centre, borough, website, all MEQ buildings with addresses,
  IMSE/SFR line, program row if any, nearest and same-program lists.

### 2. Layer 1 research (`references/layer1.md`)

1. `uv run scripts/imse.py <code>` for the deciles and pupil count. If the school has
   `Diffusion = NON`, say the index is not published this year.
2. Open the school's own site (home, the "École" or "Notre école" page, admission/inscription,
   and "Nouvelles → Travaux" or "Info-travaux"), then the service centre's establishment page.
   Extract: program(s) and whether the volet is the whole school or one stream; admission
   model in the brief's vocabulary; buildings and annexes; any travaux, délocalisation,
   relocalisation, école transitoire, with dates and the return date if given.
3. On 403, timeout or an empty page: web-search the same facts, quote the snippets, and mark
   each fact `unverified` in the post. Never stop the run for this alone.
4. Gather the **community and parent links** for the `Community` row of the school table — the
   fondation, the OPP, the conseil d'établissement, parent Facebook groups — following
   `references/layer1.md`. At most five, best first, each labelled with who runs it and whether
   the page loaded, each with its own footnote. Links that will not open are included and marked
   `unverified`; a link that cannot be tied to this school rather than a same-named one says so.
   Run this every time: when nothing is found, the row stays and reads `None found on <date>`.
5. **If a relocation or a split site is found, ask** which address anchors the zone and the
   listings: the permanent building, the temporary one, or both (two columns). Geocode a
   temporary address with `uv run scripts/geocode.py "<address>"` and pass it as `--anchor` to
   `zone_stats.py` and `zone_map.py`.
6. Prepare the school's row for `data/schools_programs.csv` (schema in `references/layer1.md`)
   and show it to the user; it is written in step 8 with the commit offer.

### 3. Comparators

Show the nearest and same-program lists from step 1 (distance, borough, program when known)
and ask which schools to compare with. Any number is fine, zero included; the user may name
others. Comparators are always in-scope schools.

### 4. Layer 2: tables and map

```bash
uv run scripts/zone_stats.py <code> <comparator codes...> [--anchor LON LAT] --format csv --out data/derived/report_<slug>.csv  # <1>
uv run scripts/report_tables.py data/derived/report_<slug>.csv --out data/derived/report_<slug>_tables.md            # <2>
uv run scripts/zone_map.py <code> <comparator codes...> [--anchor LON LAT | --mark LON LAT --mark-label "..."] --out data/derived/report_<slug>_map.html  # <3>
```
1. the artifact every number in the post is recomputed from; also run without `--format` to read the Markdown view yourself
2. the six captioned tables with decile spans, ready to paste
3. the MapLibre block; paste it into the post inside a ```` ```{=html} ```` fence, one map per post. `--anchor` moves the
   circle to a temporary site; `--mark` keeps the circle on the home building and adds a dashed marker for the temporary
   one (use it when the user chose "both"). For two zones, run `zone_stats.py` twice (`--point` for the temporary site with
   a `--label`) and concatenate the CSVs with the subject rows first; `report_tables.py` uses the `label` column as header.

Check the footer of the Markdown view: number of DAs, IEMV coverage (related cities have none)
and tax-bill match rate, and quote them in the post's sources section.

### 5. Layer 3: listings snapshot (`references/listings.md`)

Web-search current 3+ bedroom listings near the anchor address, for sale and for rent, on
Centris first (DuProprio and Realtor.ca for coverage, and say which). Record 3 to 5 of each:
price, bedrooms, property type, street or sector, link, date seen. Fewer is acceptable; say so.
Everything is dated and framed as a snapshot that will expire, never as a market statistic.

### 6. Draft through `quarto-writeup`

Invoke the `quarto-writeup` skill. Answer its interview from `references/interview.md`
(destination `posts/<slug>.qmd`, framing, scope, examples = the school and the chosen
comparators, additions open), showing the user each pre-filled answer so they can override.
Draft from `assets/report.qmd`: replace every placeholder, paste the tables and the map block,
keep the front matter to the house style (no `format:` block, `author` comes from
`posts/_metadata.yml`), reference tables as `@tbl-…`, and keep numbers in tables, not prose.

### 7. Lint and render

```bash
python3 .claude/skills/quarto-writeup/scripts/check_post.py posts/<slug>.qmd   # <1>
quarto render                                                                  # <2>
```
1. `author` and `abstract` warnings are expected on this site (see CLAUDE.md, Writing posts); everything else must be fixed
2. only if the user said yes to rendering in the interview. `quarto render` does not run JavaScript, so check the map
   in a headless browser and look at the screenshot:

   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars \
     --window-size=1200,3000 --virtual-time-budget=20000 --enable-logging=stderr --v=0 \
     --user-agent="Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/128.0 Safari/537.36" \
     --screenshot=/tmp/post.png "file://$PWD/_site/posts/<slug>.html" 2>/tmp/console.log; grep -c Uncaught /tmp/console.log
   ```

   Zero `Uncaught` lines, basemap visible, the circle, pins and station squares drawn, decile spans coloured. Add
   `--use-angle=swiftshader --enable-unsafe-swiftshader` if the basemap stays blank (MapLibre needs WebGL). The dry run
   found three real problems this way: a Leaflet bounds call before the view was set, OSM tiles refusing the site, and
   CARTO tiles watermarked "API KEY REQUIRED"; hence MapLibre over OpenFreeMap.

### 8. Hand off

Report: the file path; the school's key facts and where each came from; the anchor decision;
the comparators; the community links found and which of them are `unverified`; the listings
count and date; what else is `unverified`; the data fetch dates.
Then offer, and wait for a yes: the `/commit-changes` commit of the post and of the new row in
`data/schools_programs.csv`. A dry run stops here with nothing committed.

## Files in this skill

- `assets/report.qmd` — the post template.
- `references/layer1.md` — school-site research guide, vocabulary, relocation cues, community
  and parent links, CSV schema.
- `references/listings.md` — the Layer 3 procedure and wording.
- `references/interview.md` — pre-filled answers for the quarto-writeup interview.

Scripts live in the repo's `scripts/` folder, not here: `school_info.py`, `imse.py`,
`zone_stats.py`, `report_tables.py`, `zone_map.py`, `geocode.py`.
