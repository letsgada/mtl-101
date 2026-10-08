# Layer 1: researching the school

What to open, what to extract, how to classify it, and how to record it. Every fact in the
post's "The school" section points to a URL you opened in this run; anything else is
`unverified`.

## Pages to open, in order

1. **The school's own site** (from `school_info.py`, field `website`). CSSDM schools follow
   `https://<slug>.cssdm.gouv.qc.ca/`; CSSMB schools mostly `https://<slug>.ecoleoutremont.com/`
   or `https://<slug>.cssmb.gouv.qc.ca/`; CSSPI schools `https://<slug>.cssp-i.gouv.qc.ca/` or
   similar. Open, when they exist: the home page; "École" / "Notre école" / "Notre projet
   éducatif"; "Admission" / "Inscription"; "Nouvelles" and its "Travaux" or "Info-travaux"
   category (`/archives/nouvelles/travaux/` on CSSDM sites).
2. **The service centre's establishment page**: CSSDM `https://www.cssdm.gouv.qc.ca/a-propos/etablissements/`
   and the news search on `cssdm.gouv.qc.ca`; CSSMB `https://www.cssmb.gouv.qc.ca/etablissements/<slug>/`
   (note the "Zone grise" pages that describe shared catchments); CSSPI `https://www.cssp-i.gouv.qc.ca/`.
3. **Program pages when the school has a volet**: CSSDM
   `https://www.cssdm.gouv.qc.ca/prescolaire-primaire/programmes-volets-particuliers/` and
   `https://cybersavoir.cssdm.gouv.qc.ca/alternatif/nos-ecoles-et-volets/`.
4. **Local press for relocation timelines** when the school site is vague: search
   `"<school>" travaux relocalisation <year>`; neighbourhood outlets (monplateau.info, Journal
   d'Outremont, Journal Métro) often carry the dates the CSS does not.

If a page returns 403 or times out (some `cssdm.gouv.qc.ca` school sites do), do not retry more
than once; use web search results and mark the fact `unverified`.

## What to extract

| Field | Where it usually is | Record as |
|---|---|---|
| Program(s) | "École", "Projet éducatif", CSS program pages | `program_type` vocabulary below + free-text notes (e.g. "PEI/IB PYP", "Freinet", "volet musique-études") and whether it is the whole school or one stream |
| Admission model | "Admission" / "Inscription", CSS program page | `admission_model` vocabulary below; quote the sentence that says so |
| Buildings | MEQ list from `school_info.py`, confirmed on the site | name, address, which levels |
| Renovation / relocation | "Travaux", "Info-travaux", CSS news, local press | what is being done, where the pupils are now, the announced return date, the date of the notice |
| Enrolment | `imse.py` (`Nbre_Eleves`) | number and school year |
| IMSE / SFR | `imse.py` | value, decile, "milieu défavorisé" flag when decile ≥ 8 |
| Community links | the school site's "Fondation", "OPP", "Conseil d'établissement" or "Vie scolaire" pages; the CSS establishment page; Facebook and Instagram search | up to 5 links, each with who runs it, public or private, and whether the page loaded |

## Vocabulary

`program_type`: `regular`, `ib` (Programme d'éducation internationale, PEI, IB PYP), `alternative`
(Freinet, pédagogie alternative, école alternative), `arts` (musique, danse, arts-études, FACE),
`science`, `gifted` (douance), `specialised` (école spécialisée: a mandate for pupils with disabilities or
specific needs, usually supraregional intake; never a neighbourhood option, so the quartier report lists it in
its note and excludes it from the tables), `other` (sport-études, langues, anything else; say what in notes).
A school with no program row is **unknown**, never `regular` by default.

`admission_model` (from `project_brief.md`):
- `neighbourhood` — assignment by address; "libre choix" applications outside the zone if space remains.
- `selective` — dossier, grades, tests, teacher recommendation, parent questionnaire.
- `catchment-lottery` — no exam; a draw among applicants inside a defined zone (La Vérendrye;
  Saint-Nom-de-Jésus's 60/40 zone/CSS split is `catchment-lottery` with the split in notes).
- `css-wide-lottery` — a draw open to the whole service centre, sibling priority (FACE).
- `unknown` — the page does not say.

## Relocation cues (French)

"délocalisé", "délocalisation", "relocalisé", "relocalisation", "école transitoire", "site
transitoire", "bâtiment temporaire", "annexe temporaire", "retour à l'école de quartier",
"réintégrer", "modulaires", "travaux majeurs", "réhabilitation". A school with two permanent
pavilions (Saint-Barthélemy) is a **split site**, not a relocation; still ask which pavilion
anchors the zone if they are more than about 300 m apart.

When any cue is found: record the temporary address, geocode it
(`uv run scripts/geocode.py "<address>, Montréal"`), and **ask the user** whether the zone and
listings anchor on the permanent building, the temporary one, or both. Put the relocation in a
`callout-important` at the top of "The school", with the notice date and the announced return.

## Community and parent links

The post's `Community` row carries up to five links to the human layer around the school: the
fondation, the OPP, the conseil d'établissement, the parent Facebook group. Research them in
every run; a school with none is a finding, not a skipped step.

**Where to look, in order**

1. The school's own site: a `Fondation`, `OPP`, `Conseil d'établissement` or `Vie scolaire`
   page, usually under "École" or "Parents". These are the best links because they are
   self-identifying.
2. The service centre's establishment page for the school.
3. Web search: `"<school>" fondation OR OPP OR "conseil d'établissement"`, and
   `"<school>" <borough> facebook parents`.
4. Facebook and Instagram for the school name plus the borough. Expect most results to be
   unopenable; see below.
5. The Registraire des entreprises du Québec when a fondation's legal status is unclear.

**The French vocabulary that signals each**: *fondation* (a registered charity, often for the
schoolyard or equipment); *OPP*, organisme de participation des parents (the parent volunteer
body); *conseil d'établissement*, CE (the statutory governing board, whose minutes are often
public); *comité de parents* (the service-centre-level body); *amicale*; *service de garde*.

**Label each link** with who runs it — the school, the OPP, a fondation, parents, or unknown —
whether it is public or private, and whether the page actually loaded. The inline label in the
table stays to a few words; the detail goes in that link's footnote.

**Cap at five**, best first. Prefer official and school-run over informal, and one good parent
group over three overlapping ones. Quality of identification beats quantity.

**Disambiguation is the real failure mode here.** School names repeat across service centres on
the island — `École Marguerite-Bourgeoys` exists in both the CSSDM and the CSSMB, `Saint-Gérard`
likewise — and a Facebook group named only for the school is ambiguous. Tie a group to *this*
school's borough or address before including it; when you cannot, say so in the footnote rather
than dropping the link silently.

**Unopenable links**: Facebook groups and some fondation pages will not load for an automated
request. Include them anyway, marked `unverified`, exactly as this guide already treats a school
site that returns 403 — and say in the footnote that the link was found by search and not
confirmed.

**No scraping**, the same rule `references/listings.md` applies to Centris: find links by search,
open each at most once, and record nothing but the URL and its label. Never enumerate a group's
members, posts or content, and never join a private group.

**Zero results is a result.** Write `None found on <date>` in the row rather than deleting it, so
the reader can tell the search happened.

## The IMSE sentence

Use this wording, adapted: "The MEQ's IMSE places the school in decile *d* for 2025-2026 (1 =
most advantaged, 10 = most disadvantaged; 8 to 10 is the official *milieu défavorisé*). It is
a socioeconomic index of the pupils enrolled, built from parents' education and employment,
not a measure of academic performance, and it can differ from the census figures for the
residents of the zone." Quebec publishes no academic ranking of elementary schools; Fraser
ranks secondary schools only.

## Recording the row for `data/schools_programs.csv`

Columns: `code,school,css,program_type,admission_model,notes,source_url,checked_on`.
`css` is `CSSDM`, `CSSMB` or `CSSPI`; `checked_on` is today's date. One row per school; update
the row if it exists. Show the row to the user before writing it (step 8 of the skill). Absence
of a row means unknown, which `school_info.py` reports as such.
