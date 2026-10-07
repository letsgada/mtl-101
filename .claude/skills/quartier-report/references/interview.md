# Pre-filled answers for the quarto-writeup interview (quartier report)

The skill runs the full interview every time; each answer is pre-filled and shown so the user
can override it. Everything else follows the host project's CLAUDE.md (no per-post `format:`
block; `author` from `posts/_metadata.yml`; numbers in tables; IMSE caveat; no composite).

| Interview question | Pre-filled answer | Override allowed |
|---|---|---|
| 1. Destination and filename | `posts/<quartier-slug>-schools.qmd`, slug from `area_info.py` (lowercase ASCII, hyphens, e.g. `villeray-schools`); date = today | yes |
| 2. Where the data comes from | `data/derived/area_<slug>.csv` from `zone_stats.py` (canonical for every zone number), `data/derived/area_<slug>_schools.csv` from `area_info.py` (program, admission, IMSE/SFR, pupils, report links), `data/derived/zone_stats_all.parquet` for deciles and medians, `data/derived/area_<slug>_listings.csv` for Layer 3 | yes |
| 3. Framing and allowed claims | "Report plus cautious reading": no ranking, no composite, no verdict on any school; prose explains deciles and differences between schools; IMSE is socioeconomic, not academic | yes, but "interpret freely" contradicts the brief's stance and must be an explicit user decision |
| 4. Scope | Three layers: the schools (files only, no per-school web research), the kilometres compared (overview + six group tables + map), living there now (listings per school). Out: per-school renovation research, childcare, transit frequency, heat, CMHC rents, secondary feeders (next steps) | yes |
| 5. Example selection | Every in-scope school in the confirmed set, inside and edge; specialised and out-of-scope schools in the note only | yes |
| 6. Anything to add | open | — |

Assumptions the skill states in the same message: categories `[quartier-report, <borough-slug>,
layer-1, layer-2]`; `toc: true`; `code-annotations: hover`; English prose with French names
kept; one MapLibre map block; render after lint unless the user says otherwise; nothing
committed without a yes.
