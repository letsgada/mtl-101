# Pre-filled answers for the quarto-writeup interview

`quarto-writeup` asks six questions before drafting. The skill runs the interview every time
but pre-fills each answer with the project's conventions; show the pre-filled value and let the
user override it. Everything not listed here is decided by the writeup skill's own rules and
the host project's CLAUDE.md (no per-post `format:` block; `author` from `posts/_metadata.yml`;
numbers in tables; IMSE caveat; renovations flagged).

| Interview question | Pre-filled answer | Override allowed |
|---|---|---|
| 1. Destination and filename | `posts/<school-slug>-report.qmd`, where the slug is the school's short name in lowercase ASCII with hyphens (e.g. `ecole-laurier-report`); date = today | yes |
| 2. Where the data comes from | `data/derived/report_<slug>.csv` from `zone_stats.py` (canonical for every zone number), `imse.py` output for the deciles, `data/derived/zone_stats_all.parquet` for deciles and medians, the pages listed in the Layer 1 notes for school facts, the listings recorded in Layer 3 | yes |
| 3. Framing and allowed claims | "Report plus cautious reading": no ground truth, no ranking, no composite; prose explains deciles and differences, never says better or worse; IMSE is socioeconomic, not academic | yes, but "interpret freely" contradicts the brief's stance and must be an explicit user decision |
| 4. Scope | Three layers: the school, the zone (six tables + map), living there now (listings). Out: childcare, transit, heat, rents by CMHC zone, secondary feeder (not built yet; list under next steps) | yes |
| 5. Example selection | The school plus the comparators chosen in step 3; zero comparators means one column plus the island median | yes |
| 6. Anything to add | open | — |

Assumptions the skill states in the same message (from the writeup skill's step 3): categories
`[school-report, <borough-slug>]` plus `layer-1`, `layer-2`; `toc: true`; `code-annotations: hover`;
English prose with French names kept; one Leaflet map block; render after lint unless the user
says otherwise; nothing committed without a yes.

Slug rule: strip "École ", lowercase, replace accents and non-alphanumerics with hyphens,
collapse repeats, append `-report`.
