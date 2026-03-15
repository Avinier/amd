# AMD v2 Plan: Source Format And Agent-Readable Surfaces

## Executive Summary

AMD v2 should not force one format to optimize equally for human authoring, Markdown portability, and machine consumption. The best design is a layered one:

- **source-of-truth authoring format**: plain `.md` with small YAML frontmatter
- **live agent-readable format**: structured JSON emitted by AMD commands
- **snapshot/bootstrap format**: exported JSON manifests such as `amd.xref.json` and per-artifact JSON
- **append-only machine history format**: JSONL for journals and signals
- **validation format**: JSON Schema over parsed frontmatter and JSON exports

The best source format is therefore **Markdown with minimal YAML frontmatter**, but the best agent-readable format is **JSON**, not raw Markdown or YAML. This matches the dominant patterns in Jekyll, Quarto, MyST, GitHub Docs, Pandoc, and Hugo for authoring metadata, while also matching how systems like MyST expose machine-readable site/page data for downstream tooling.[1][2][3][4][5][6][7]

The strongest refinement to the existing skeleton is this:

- keep **generic document metadata** like `title` at the top level when it helps portability
- keep **AMD-specific metadata** under a dedicated `amd:` namespace

That is more interoperable than placing every field under `amd:`.

## Key Findings

- **YAML frontmatter is the best authoring convention for Markdown artifacts**: Jekyll, Quarto, MyST, GitHub Docs, and Pandoc all use or explicitly document YAML metadata blocks at the top of Markdown files.[1][2][3][4][5]
- **YAML beats JSON and TOML for AMD’s author-facing source format**: Hugo supports all three frontmatter formats, but the broader Markdown tooling ecosystem standardizes mostly on YAML, and AMD’s nested metadata shape is easier to author in YAML than JSON.[1][2][3][4][6]
- **JSON is the right agent-readable surface**: MyST exposes both a project-level cross-reference manifest and per-page JSON data, which is exactly the split AMD wants for bootstrap plus detailed machine access.[7]
- **One format should not do every job**: append-only activity streams are better as JSONL than as YAML or Markdown because concatenation and streaming are simple.[8]
- **Validation should happen after parsing, not by inventing a custom YAML validator**: parse frontmatter YAML into normal data structures, then validate with JSON Schema.[4][9][10]
- **The skeleton’s `amd.title` shape is probably too AMD-centric**: putting document-generic fields like `title` at the top level improves compatibility with existing Markdown ecosystems, while `amd:` can hold AMD-specific fields.

## Detailed Analysis

### 1. The format problem AMD is solving

AMD has at least four distinct format needs:

1. **Human authoring**
   - should be comfortable in normal editors
   - should render as normal Markdown anywhere
   - should not look machine-owned

2. **Machine retrieval**
   - agents need deterministic structured data
   - should not require reparsing the whole repo every time

3. **Append-only machine state**
   - events, caveats, derivations, and signals must be merge-friendly and stream-friendly

4. **Validation and interoperability**
   - metadata should be typed and validated
   - other tools should not be broken by AMD metadata

No single format is best for all four.

### 2. Options for the source-of-truth document format

#### Option A: inline JSON comment block in Markdown

Example:

```md
<!-- amd:meta { ... } -->
```

Pros:

- machine-friendly
- self-contained

Cons:

- poor human ergonomics
- visually hostile in normal Markdown
- easy to clobber or reflow
- weak interoperability with normal Markdown tooling

Verdict:

- reject as the v2 source format

This is the main v1 problem the skeleton is trying to escape.

#### Option B: YAML frontmatter in Markdown

Example:

```yaml
---
title: Payments Incident Report
amd:
  id: report.payments.incident-2026-03-11
  kind: report.incident
  policy:
    freshness_class: observational
    stale_after: 4h
---
```

Pros:

- dominant convention across Markdown publishing/documentation systems[1][2][3][4][5]
- good human readability
- natural nested structure for `amd.policy`, `amd.derive`, and labels
- easy to preserve in plain `.md`
- familiar to technical users and agents alike

Cons:

- YAML has quoting/typing footguns[5]
- must be kept small or it becomes a config dump

Verdict:

- best default source format for AMD artifacts

#### Option C: TOML frontmatter in Markdown

Pros:

- cleaner scalar typing than YAML in some cases
- less indentation-sensitive

Cons:

- much less common than YAML in Markdown authoring ecosystems
- nested structures are more awkward for the kind of metadata AMD needs
- weaker fit with MyST/Quarto/GitHub Docs/Jekyll conventions

Verdict:

- acceptable in theory, not the best default for AMD

#### Option D: JSON frontmatter in Markdown

Pros:

- deterministic for machines
- validates naturally

Cons:

- unpleasant for human editing
- too noisy for normal Markdown files
- weaker ecosystem convention for frontmatter specifically

Verdict:

- good for exports, bad for author-facing source

#### Option E: separate sidecar metadata file

Examples:

- `doc.md` + `doc.meta.yml`
- `doc.md` + `.amd/artifacts/<id>.json`

Pros:

- keeps source Markdown visually clean
- metadata can be machine-optimized

Cons:

- document stops being self-describing
- source and metadata can drift
- moving/renaming files becomes more complicated
- authoring experience becomes split-brain

Verdict:

- useful for exports and cache/index state
- not the best primary authoring model

### 3. Recommended source format

The best AMD v2 source format is:

- normal `.md` files
- YAML frontmatter at the top
- CommonMark/MyST-friendly Markdown body
- optional sparse AMD markers in the body only where needed

#### Recommended frontmatter shape

Use a hybrid frontmatter model:

- **top-level keys** for generic document metadata that other tools may understand
- **`amd:` namespace** for AMD-specific metadata

Recommended example:

```yaml
---
title: Payments Incident Report
date: 2026-03-11
amd:
  id: report.payments.incident-2026-03-11
  kind: report.incident
  labels:
    team: payments
  policy:
    freshness_class: observational
    stale_after: 4h
    refresh_mode: auto
  derive:
    outputs:
      - report.postmortem
---
```

This is better than:

```yaml
---
amd:
  title: Payments Incident Report
  ...
---
```

because `title` is a generic document concept, not AMD-specific state.

#### What should stay in source frontmatter

- generic page metadata like `title`, optionally `date`
- `amd.id`
- `amd.kind`
- `amd.labels`
- `amd.policy` overrides only
- `amd.derive` declarations only when needed

#### What should not stay in source frontmatter

- computed freshness state
- priority score
- signal rollups
- caveat lists
- contributor history
- provenance graph state
- fingerprints

Those belong in `.amd/` and JSON exports, not in the Markdown source.

### 4. Recommended inline AMD markers

The body should stay mostly normal Markdown. Inline AMD syntax should be sparse and purpose-specific.

#### Section labels

Preferred AMD write syntax:

```md
<!-- amd:label risk-assessment -->
## Risk Assessment
```

AMD should also read MyST targets and heading IDs, but it should not require them.[3][7]

#### Generated blocks

Preferred materialization fence:

```md
<!-- amd:generated:start timeline-summary -->
...
<!-- amd:generated:end -->
```

These fences are the only machine-owned body regions AMD should rewrite.

### 5. Best agent-readable format

The best agent-readable format is **not Markdown** and **not YAML**. It is JSON, delivered through two surfaces.

#### Live surface: CLI JSON

For active agent work:

- `amd prime --format json`
- `amd query --format json`
- `amd affected --format json`
- `amd history --format json`

Why:

- deterministic
- compact
- schema-able
- no repo-wide reparse required

#### Snapshot/bootstrap surface: exported JSON

For cheap discovery or offline/tooling access:

- `.amd/export/amd.xref.json`
- `.amd/export/artifacts/<artifact_id>.json`

This is directly analogous to MyST’s split between `myst.xref.json` and page JSON data.[7]

#### Why not make agents read raw Markdown first

Because agents usually want:

- what artifacts exist
- what kind each is
- what sections exist
- where the file lives
- what freshness/caveat/provenance state applies now

That is exactly what JSON should provide.

Markdown should be opened only when the agent needs full prose context or needs to edit the source of truth.

### 6. Best append-only machine format

For events, caveats, derivations, and signals, use JSON Lines (`.jsonl`).

Why:

- one record per line
- concatenation is easy
- append is easy
- stream processing is easy
- merge-friendly compared with one giant JSON array

JSON Lines explicitly recommends a newline terminator after each value and `.jsonl` as the extension.[8]

### 7. Best validation format

Use JSON Schema for:

- parsed frontmatter validation
- export contract validation
- CLI JSON output contract tests

Why:

- YAML frontmatter can be parsed into ordinary data
- JSON Schema is built for structural validation[9][10]
- GitHub Docs uses schema-based validation for frontmatter in its test suite, which is a strong real-world precedent.[4]

Practical rule:

- author in YAML
- parse to data
- validate as JSON using JSON Schema

### 8. Best “single-file agent-readable” format

If you want one file that an agent can cheaply read to understand the project, it should be:

- `amd.xref.json`

Its job is not full fidelity. Its job is cheap routing.

Recommended contents:

- artifact id
- kind
- source path
- title
- section ids / headings / labels
- lightweight freshness/caveat summary
- relation edges summary

Recommended exclusions:

- full section text
- full AST
- full journal history

If an agent needs more than the map, it should:

1. call a live JSON command, or
2. open the source Markdown file

### 9. Best per-artifact machine-readable format

Per-artifact JSON should be richer than `amd.xref.json`, but still not become a competing content store.

Recommended contents:

- parsed frontmatter
- normalized AMD metadata
- source path
- section list and stable IDs
- ownership flags
- fingerprints
- freshness summary
- active caveats summary
- signal rollup summary
- derivation/provenance summary

Recommended default exclusion:

- full Markdown body

Optional debug mode:

- `--include-ast`
- `--include-snippets`

This keeps default exports lightweight while still leaving room for introspection when debugging AMD itself.

### 10. Core And Agent Layers

The YAML shape should **not** be invented by the agent on a per-file basis.

The right split is:

- **core/spec layer**
  - defines the canonical frontmatter shape
  - defines allowed top-level keys
  - defines allowed `amd:` keys
  - defines which fields belong in source frontmatter versus `.amd/`
  - validates the parsed result

- **agent layer**
  - decides how to populate the canonical shape for a particular artifact
  - infers `kind`, policy overrides, and labels when needed
  - preserves unrelated user metadata
  - avoids writing unnecessary fields when schema/config defaults already cover the case

Short rule:

- core defines the slots
- agent fills the slots

#### What the agent should actively do

1. Prefer schema/project defaults over explicit frontmatter overrides.
2. Only write AMD metadata that is actually needed for this artifact.
3. Infer `kind` and minimal `amd.policy` overrides from the document’s purpose.
4. Keep generic document metadata such as `title` at top level when present.
5. Add section labels only when section-level targeting, derivation, or propagation is likely.
6. Preserve unrelated user frontmatter keys and document style.
7. Never move computed machine state into source frontmatter.

#### What the agent should not do

- invent new frontmatter keys outside the spec
- reshape the YAML ad hoc from file to file
- dump index state, caveats, rollups, or provenance into the Markdown source
- treat YAML frontmatter as the primary runtime machine API

#### Agent consumption discipline

The agent layer should follow this format discipline:

1. Prefer CLI JSON outputs for live work.
2. Use `amd.xref.json` as the cheap bootstrap map.
3. Open Markdown only when full prose is needed or when editing.
4. Treat YAML frontmatter as an authoring surface, not the primary machine API.
5. Never treat exported JSON as the canonical prose source.

This gives a clean division:

- Markdown = authoring
- YAML frontmatter = minimal human-editable metadata
- JSON = agent-facing structured state
- JSONL = append-only machine history

### 11. What this means for the skeleton

The core F1 direction in [skeleton.md](/Users/avinier/Projects.py/amd/internals/v2/skeleton.md) is right, but I would refine it in two ways:

1. **Keep `title` top-level, not inside `amd:`**
   - this improves portability to existing Markdown ecosystems

2. **Be explicit that JSON is the agent-readable surface**
   - YAML frontmatter is for authoring
   - JSON exports and CLI JSON are for agents

That keeps AMD aligned with the rest of the v2 plans:

- parsing plan for section identity
- context-graph plan for xref/export
- temporal plan for freshness state
- changes-propagation plan for agent use of machine surfaces

## Areas Of Consensus

- source Markdown should stay plain and portable
- inline machine metadata should be minimal
- YAML frontmatter is the best author-facing metadata convention
- agents should prefer JSON over reparsing Markdown
- append-only machine streams should use JSONL
- validation should be schema-based

## Areas Of Debate

- whether AMD should allow `.amd.md` long-term or only as a migration path
- whether `date` and other generic page metadata should be first-class AMD concerns or left entirely to user/frontmatter conventions
- whether label comments should be inserted by default or only when section-level references are needed
- whether per-artifact JSON should include optional snippets by default

## Recommendation

Adopt this layered format strategy:

1. `.md` as the primary artifact extension
2. YAML frontmatter for source metadata
3. generic keys like `title` at top level
4. AMD-specific keys under `amd:`
5. CLI JSON and export JSON as the main agent-readable surfaces
6. JSONL for journals and signals
7. JSON Schema for validation

That is the best fit for AMD because it preserves Markdown portability for humans while giving agents deterministic structured surfaces that are better than reparsing raw files.

## Sources

[1] Jekyll, “Front Matter.” Official docs. YAML front matter at the top of Markdown files. <https://jekyllrb.com/docs/front-matter/>

[2] Quarto, “Front Matter.” Official docs. YAML metadata at the top of Quarto Markdown documents. <https://quarto.org/docs/authoring/front-matter.html>

[3] MyST Markdown, “Configuration and content frontmatter.” Official docs. YAML header in Markdown and project/page configuration split. <https://mystmd.org/guide/configuration>

[4] GitHub Docs, “Using YAML frontmatter.” Official docs. YAML frontmatter plus schema-based validation in tests. <https://docs.github.com/en/contributing/writing-for-github-docs/using-yaml-frontmatter>

[5] Pandoc, “Metadata blocks” and User’s Guide. Official docs. YAML metadata blocks at the top of Markdown and YAML parsing caveats. <https://pandoc.org/demo/example33/8.10-metadata-blocks.html> and <https://pandoc.org/MANUAL.pdf>

[6] Hugo, “Front matter.” Official docs. Supports JSON, TOML, or YAML front matter; useful comparison point. <https://gohugo.io/content-management/front-matter/>

[7] MyST Markdown, “Exposing MyST and Document Metadata.” Official docs. `myst.xref.json` plus per-page JSON data as machine-readable surfaces. <https://mystmd.org/guide/website-metadata>

[8] JSON Lines, format reference. One JSON value per line, `.jsonl` convention, newline terminator guidance. <https://jsonlines.org/>

[9] JSON Schema, documentation and specification. Official docs. JSON Schema is for annotating and validating JSON documents; validation defined in the spec. <https://json-schema.org/docs> and <https://json-schema.org/specification>

[10] JSON Schema Validation 2020-12. Official validation vocabulary. <https://json-schema.org/draft/2020-12/json-schema-validation>

[11] Swagger / OpenAPI docs, “Basic Structure.” Official docs. OpenAPI can be written in YAML or JSON; useful analogy for human-authored YAML and machine-friendly JSON equivalence. <https://swagger.io/docs/specification/v3_0/basic-structure/>

## Gaps And Further Research

- decide the exact top-level keys AMD wants to reserve beyond `title`
- decide whether `.amd.md` remains accepted indefinitely or only during migration
- define the exact JSON contract for per-artifact exports
- define whether AST export is debug-only or part of the normal machine surface
