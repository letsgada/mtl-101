# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this repo is

MTL-101 helps a parent pick a Montreal neighbourhood by working backwards from school quality:
"which francophone public elementary school do I want, and therefore where should I live?"
Scope is the island of Montreal only (CSSDM, CSS Marguerite-Bourgeoys, CSS Pointe-de-l'Île);
the West Island, South Shore and Laval are excluded. `project_brief.md` is the domain source of
truth: data sources (MEQ IMSE/SFR indices on Données Québec, CGTSIM PDFs, per-school program
pages), admission models, known schools for seed data, and the open questions. Read it before
touching anything that claims a fact about a school, zone or index.

The brief recommends building the tool as a skill plus a few narrow scripts (CSV/GeoJSON fetch,
geocoding), not a standalone app, and reusing the government finders rather than rebuilding
zone-boundary lookups. Nothing of that tool exists yet; the repo currently holds the Quarto site
that will document it.

## Repo layout

```
_quarto.yml            site config: render glob, navbar, theme stack, GoatCounter include
index.qmd              prose landing page (what MTL-101 is, scope, how it works)
posts.qmd              listing over posts/ (date desc, categories, RSS feed)
posts/*.qmd            hand-written posts; posts/_metadata.yml sets freeze, no banner, author
pages/                 machine-generated pages (empty for now; keep generated output out of posts/)
about.qmd, profile.jpg About page (jolla template, GitHub link only)
design.md              the design brief; design.tokens.json the values (see Design tokens)
theme-light.scss       generated from the tokens: do not edit
theme-dark.scss        generated from the tokens: do not edit
site.scss              hand-maintained: applies tokens to Quarto components
styles.css             empty scaffold stub, still wired; put styling in site.scss instead
project_brief.md       domain brief (renders nowhere: only *.qmd render)
.github/workflows/publish.yml   renders and deploys to GitHub Pages on push to main
```

Published at https://letsgada.github.io/mtl-101. Only `*.qmd` files render
(`render: "**/*.qmd"`), so markdown files like this one never become pages; a page wanted from
markdown is renamed to `.qmd`. Navbar: Posts · About · GitHub.

## Commands

```bash
quarto preview          # live-reload dev server
quarto render           # builds to _site/ (gitignored, as is .quarto/)
```

Posts freeze computational output (`posts/_metadata.yml`), so a changed code cell needs
`quarto render posts/<name>.qmd` to refresh its cache. If a post gains executable cells, render
locally and commit `_freeze/` (it is deliberately not gitignored): the publish workflow installs
no Python or R. There are no tests or linters; `quarto render` exiting 0 is the check.

## Writing posts

New posts go in `posts/` as flat `posts/<slug>.qmd` files (a post with its own images may use a
`posts/<slug>/index.qmd` folder). Front matter: `title`, `date`, `categories`, `description`,
optional `toc`; `author` comes from `posts/_metadata.yml`. Never add a per-post `format:` block:
it replaces the site's `format.html` and drops the theme and the tracker. Use the `quarto-writeup`
skill to turn research into a post; it recomputes numbers from the data and lints the draft.

Keep numbers in tables, not prose. The IMSE is a socioeconomic index, not an academic ranking;
say so whenever it appears. Flag renovations and relocations for any school mentioned.

## Design tokens

The site's look is derived, not picked: `design.md` is the brief (keystone: one red pin on a paper
map; the chosen school is the only emphasis colour) and `design.tokens.json` holds the values.
`theme-light.scss` and `theme-dark.scss` are generated from the JSON and wired in `_quarto.yml`;
`site.scss` applies the tokens to Quarto components and is hand-maintained. To change a colour or
font, edit the JSON, then:

```bash
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py check design.tokens.json
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render md   design.tokens.json --into design.md
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render scss design.tokens.json --theme light -o theme-light.scss
uv run https://ohjho.github.io/dotfiles/scripts/design_tokens.py render scss design.tokens.json --theme dark  -o theme-dark.scss
```

Posts use the helper classes in `site.scss` (`.pin`, `.zone`, `.zone-soft`, `.decile-low`,
`.decile-mid`, `.decile-high`) rather than inline colours, never a title banner, and never a
second accent. For charts, `decile-low → decile-mid → decile-high` is the sequential ramp, `zone`
the boundary colour, `accent` the single highlighted school (see `dataviz`).

## Analytics and publishing

GoatCounter reports to `https://jho.goatcounter.com` from the `include-in-header` block under
`format.html` in `_quarto.yml`; the recorded path is prefixed with the hostname because several
sites share that dashboard. Exactly one `count.js` tag per page; do not add another.

`.github/workflows/publish.yml` renders with Quarto 1.10.18 and deploys the `_site/` artifact on
every push to `main`, ignoring `.claude/**`, `CLAUDE.md`, `.gitignore`, `design.md` and
`design.tokens.json`. One-time repo setting before the first deploy: Settings → Pages → Build
and deployment → Source: "GitHub Actions". Regenerate the workflow with the
`quarto-gh-publish-action` skill rather than editing it by hand.

## Skills and commands

`quarto-site-setup`, `design-derivation`, `goatcounter-tracking`, `quarto-gh-publish-action`,
`quarto-writeup` and `surge-artifacts` under `.claude/skills/`, and `commit-changes` under
`.claude/commands/`, are symlinks into `../dotfiles/.claude/` on the author's machine, not repo
content; they resolve only there. `/quarto-site-setup` step 0 recreates them.

## Conventions

- Commit with `/commit-changes`: one commit per logical change, only the files that changed,
  never `git add -A`. The site was built one stage per commit (structure, theme, tracking,
  workflow); keep that granularity.
- Do not push, publish or enable Pages without being asked.
- Do not edit `theme-*.scss` or the token tables between `<!-- tokens:start -->` and
  `<!-- tokens:end -->` in `design.md`; both are regenerated from the JSON.
