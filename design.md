# Design: MTL-101

## Derivation

| Input | Read | Produces |
|---|---|---|
| Content | School zones and IMSE deciles on the island of Montreal; a parent picks a school and the neighbourhood is whatever lies inside its zone | The **map metaphor**: paper ground, ink lettering, one red pin for the chosen school, a quiet blue for the zone, a single-hue blue ramp for the deciles |
| Audience | Montreal parents deciding where to live; secondarily the author documenting data work | Serif headings and humanist sans body, the voice of a well-edited city guide; mono only where data is read out (deciles, code, category pills) |
| Goal | Scan, compare, decide: calm and trustworthy, not an instrument panel | Static, scannable pages; generous section spacing; tables for anything a reader compares; one emphasis colour so the eye is never pulled twice |
| Constraint | Quarto website on cosmo, light + dark, Google fonts allowed, GitHub Pages | Two colour sets; `theme-light.scss` / `theme-dark.scss` rendered from the tokens; `site.scss` applies them to Quarto components; Bootstrap breakpoints kept so the two systems agree |

## Keystone

**One red pin on a paper map.** The chosen school is the only emphasis colour on the page; everything else is the map's own paper, ink and hairlines.

It forbids: a second accent (so the cosmo title banner is off and the navbar sits on the paper, not cosmo's blue bar), decorative colour on headings or rules, and any red that is not the pin. Data colour is blue, and blue is never used for emphasis.

## Colour scheme

Proposed in round 2 and accepted as is: pin red `#B3261E` / `#EF7A70` as accent on warm paper `#F6F3EC` / night navy `#15191E`, blue-black ink, and five keystone extras (`zone`, `zone-soft`, `decile-low`, `decile-mid`, `decile-high`). The user supplied no brand or favourite colour. The pale end of the decile ramp is a fill colour and fails text contrast on purpose; `check` reports it as a warning, not an error.

## Tokens

Full system (colour roles and extras, three font roles, radius, spacing scale, type scale, measure, one shadow, two durations, Bootstrap breakpoints). `check` passes with 0 errors in both themes; warnings are limited to the decile fills.

<!-- tokens:start -->
| token | light | dark | from | note |
|---|---|---|---|---|
| bg | `#F6F3EC` | `#15191E` | content | the map paper: warm off-white by day, navy-black night map after dark |
| surface | `#FFFFFF` | `#1E242B` | content | cards, code blocks, table headers: a sheet laid on the paper |
| ink | `#1E2933` | `#E8E6E0` | audience | blue-black map lettering; calm, high contrast for long reading |
| muted | `#5B6670` | `#A3ABB4` | goal | dates, categories, captions: readable but recessive |
| line | `#DAD4C6` | `#333B45` | goal | hairlines and borders, the paper's own grid |
| accent | `#B3261E` | `#EF7A70` | content | the pin: the one chosen school; links and the single emphasis colour |
| accent-soft | `#F6E0DE` | `#4A2320` | content | tinted ground behind the pin colour for callouts |
| zone | `#3B6EA5` | `#7FA9D9` | content | the catchment boundary: a quiet map blue, never the pin |
| zone-soft | `#DCE7F3` | `#22364D` | content | the catchment fill |
| decile-low | `#A9C8E3` | `#3D5F80` | content | IMSE deciles 1-3, most advantaged: the pale end of the single-hue ramp (a fill, not text) |
| decile-mid | `#4F86B0` | `#6E9FCB` | content | IMSE deciles 4-7 |
| decile-high | `#1F4E79` | `#A9C8E3` | content | IMSE deciles 8-10, milieu defavorise: the intense end of the ramp |

| token | value | from | note |
|---|---|---|---|
| font-display | `"Source Serif 4", "Georgia", "Times New Roman", serif` | audience | serif headings: a well-edited city guide for parents, not a dashboard |
| font-body | `"Source Sans 3", system-ui, "-apple-system", "Segoe UI", sans-serif` | audience | humanist sans for long prose; pairs with the serif from the same family |
| font-mono | `"JetBrains Mono", ui-monospace, "SFMono-Regular", "Menlo", monospace` | content | data readouts, deciles, code cells and category pills |
| radius-md | `4px` | goal | tight corners: map furniture, not app chrome |
| space | `8px` | goal | the rhythm unit |
| space-xs | `4px` | goal |  |
| space-sm | `8px` | goal |  |
| space-md | `16px` | goal |  |
| space-lg | `32px` | goal |  |
| space-xl | `64px` | goal | section breathing room; the goal is scanning, so sections separate clearly |
| measure | `68ch` | goal | prose measure; tables and maps run full width |
| type-xs | `0.8rem` | goal | captions, category pills |
| type-sm | `0.9rem` | goal | table body, metadata |
| type-md | `1rem` | goal | body |
| type-lg | `1.25rem` | goal | h3, listing titles |
| type-xl | `1.75rem` | goal | h1, h2 |
| shadow-card | `0 1px 2px rgba(30, 41, 51, 0.08)` | constraint | barely-there lift for a surface on the paper; the map is flat |
| motion-duration-fast | `120ms` | goal | hover underline and colour changes |
| motion-duration-base | `200ms` | goal | theme toggle and reveals |
| breakpoint-sm | `576px` | constraint | Bootstrap/cosmo breakpoints, so site.scss and Quarto agree |
| breakpoint-md | `768px` | constraint |  |
| breakpoint-lg | `992px` | constraint |  |
| breakpoint-xl | `1200px` | constraint |  |
<!-- tokens:end -->

## Layout & rhythm

An 8px unit. Sections separated by `space.xl` and an `h2` hairline so a parent can jump between schools or boroughs by scanning. Prose sits in a 68ch measure; tables, maps and code run full width because they are the things being compared. Listing rows are separated by hairlines, not cards. Metadata (dates, categories, authors) is muted and small; category pills are bordered mono text on the paper, not filled chips.

## Signature move

The pin. Links, the active nav item, the one callout per page and the highlighted school in a table all use `accent`; nothing else does. Around it everything stays quiet: the zone blue is desaturated, the decile ramp is one hue, headings are ink, rules are hairlines. A chart with the ramp and a single red pin reads as the whole idea in one glance.

## Self-check

Same content for **school-board data staff** instead of parents: the serif would go (they live in spreadsheets and GIS tools), mono would carry headings and labels, density would rise, and the pin would become one of several status colours because their goal is auditing coverage rather than choosing one school. Same content with the goal **persuade a borough to fund a school**: one large number and a map would lead each page and the palette would narrow further to ink plus pin. Both re-derivations change the aesthetic, so the derivation is rooted in the brief.

## Handoff

Consumer: `quarto-site-setup` (this run), then `quarto-writeup` for posts and `dataviz` for any chart (use `decile-low → decile-mid → decile-high` as the sequential ramp, `zone` for boundaries, `accent` for the single highlighted school).

```bash
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py check design.tokens.json
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render md   design.tokens.json --into design.md
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render scss design.tokens.json --theme light -o theme-light.scss
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render scss design.tokens.json --theme dark  -o theme-dark.scss
```
