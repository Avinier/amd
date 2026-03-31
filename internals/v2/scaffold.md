# AMD v2 Scaffold

## Status

This document is the source-backed scaffold for AMD v2.

- It absorbs and extends the work in [internals/research/alternatives_research.md](../research/alternatives_research.md).
- It uses primary product docs and repo docs where possible.
- It adds foundational standards/papers where AMD needs stronger implementation ground: structured change detection, provenance, concurrency, and freshness.
- When a statement below is a design inference rather than something stated directly in a source, it is labeled as `Inference`.

## Executive Summary

AMD v2 should be a **provenance, policy, indexing, and derivation layer for agent-maintained Markdown**.

It should **not** primarily be a new Markdown filetype.

The central shift is:

- Keep source artifacts as normal `.md` files, optionally MyST-compatible.[1][2][7]
- Move machine state out of the document body into an **external, rebuildable index** plus **append-only journals**.[3][22]
- Treat inline timelines, status blocks, and rollups as **projections**, not the concurrency-critical source of truth.[11][12][13][14][21][22]
- Replace raw text hashing with **AST-aware structural fingerprinting**.[6][7][23][24][25]
- Separate cheap **refresh/indexing** from expensive **recompute/derivation**.[15][16][28]
- Adopt **safe multi-agent write discipline** before adding more metadata surface: lock files, atomic writes, append-only journals, and Git merge strategies for append-heavy files.[22][27]

If AMD follows this direction, it becomes worth building. If it stays as “Markdown plus inline metadata plus timeline plus raw hashes,” it will remain easy to replace.

## Research Questions

This scaffold answers:

1. What existing tools or systems already solve part of AMD's target problem?
2. What exact signals should AMD borrow from them?
3. Which of those signals belong in the source document, and which belong in an external index/journal?
4. What foundational literature/standards should guide AMD's design where product docs are not enough?
5. What architecture gives AMD the best chance of solving:
   - evolving agent-maintained context
   - provenance across multiple agents
   - structured derivation
   - stale-data and priority policy
   - report-scale change detection
   - heavy timeseries-informed context

## Current AMD Gaps To Fix First

These are not alternative-research findings; they are the practical gaps in the current repo that v2 must explicitly fix.

- The current implementation rewrites the same Markdown file on every event/refresh, which creates write contention and breaks the “multi-agent traceability” claim under concurrency. See [amd/core.py](../../amd/core.py) and [README.md](../../README.md).
- Fingerprinting is currently raw text hashing over extracted sections, so formatting-only changes trigger drift.
- The JSONL timeseries sidecar is rescanned in full on refresh, so heavy signal history does not scale operationally.
- `derive-skill` is currently copy-based, not a real provenance-rich transformation pipeline.
- The inline timeline is treated as the main trace surface, which is exactly the wrong place to put concurrent writes.

AMD v2 should be designed as if these flaws are the starting constraints.

## Core Thesis

AMD v2 should be:

- **Agent-native CLI** — the primary interface is for AI agents (Claude Code, Codex, etc.) invoking commands at machine speed; humans can use it, but agents are the first-class consumers
- **Git-native**
- **Markdown-first**
- **Index-backed**
- **Policy-driven**
- **Provenance-rich**
- **Derivation-capable**
- **Safe for multiple agents**
- **Metadata-only in `.amd/`** — `.amd/` stores identity, relations, temporal data, and context signals; zero document content

AMD v2 should not be:

- a note-taking app
- a real-time collaborative editor
- a general TSDB
- a giant inline metadata block
- a system that depends on agents manually maintaining changelog prose
- a content store — `.amd/` never holds copies of user documents

## What AMD Borrows, By Source

### 1. MyST Markdown

#### Signal: page-level and project-level metadata placement with override rules

MyST explicitly distinguishes fields that live at page level, project level, or page-with-project-override, with page values taking precedence.[1]

**AMD borrow**

- Project-level AMD policy should live in a project config file, not be repeated in every artifact.
- Artifact-level frontmatter should override project defaults selectively.
- Explicit `null` should mean “clear the inherited value,” following MyST and Org-like inheritance behavior.[1][20]

**Implementation implication**

- Add `.amd/config.yml` for project defaults.
- Keep artifact-local frontmatter small and stable:
  - `id`
  - `kind`
  - `title`
  - `labels`
  - `policy` overrides
  - `derive` declarations

#### Signal: labels and identifiers as first-class targets

MyST references resolve through label/identifier pairs in the AST, and targetable content can be labeled directly.[2][7]

**AMD borrow**

- Artifact sections need stable IDs that survive heading text changes, reordering, and file moves.
- Agent references should target `artifact_id + section_id`, not heading text or file position.

**Implementation implication**

- AMD should support both:
  - MyST-style explicit labels, where available
  - AMD HTML comment labels for Markdown compatibility, e.g. `<!-- amd:label risk-assessment -->`
- The external index should canonicalize both forms into one stable `section_id`.

#### Signal: machine-readable cross-reference and page JSON

MyST exposes site-wide references via `myst.xref.json`, and each page has a JSON representation with frontmatter, AST, and source location.[3]

**AMD borrow**

- Do not store all machine state inline in Markdown.
- Expose a machine-readable manifest and per-artifact JSON projection.

**Implementation implication**

- AMD should generate:
  - `.amd/export/amd.xref.json`
  - `.amd/export/artifacts/<artifact_id>.json`
- Each artifact JSON should include:
  - source path
  - frontmatter
  - section labels
  - fingerprints
  - freshness state
  - caveats
  - priority
  - derivation edges
  - signal rollups

#### Signal: AST and transform pipeline

MyST is built around mdast plus transforms; plugins can modify AST during build/render.[5][6][7]

**AMD borrow**

- Fingerprinting should operate on parsed structure, not raw section text.
- Derivation should operate on labeled AST fragments, not substring copying.
- AMD should expose hook points and transform steps rather than baking all behavior into ad hoc commands.

**Implementation implication**

- Inference: if AMD stays in Python, the parser layer should use MyST-compatible parsing rather than heading regexes.
- AMD should treat parsing and transforms as a formal pipeline:
  1. parse source
  2. resolve labels/sections
  3. normalize AST
  4. fingerprint
  5. update index
  6. optionally materialize projections

#### Signal: executable and labeled code-cell directives

MyST `code-cell` directives support labels, captions, numbering, and execution metadata.[4]

**AMD borrow**

- Not for notebook parity.
- For AMD, the useful idea is that generated or executable content should be **labelable**, **referenceable**, and **separable from prose**.

**Implementation implication**

- Generated blocks in AMD should carry stable block IDs and provenance, whether or not AMD ever adopts executable directives directly.

### 2. Obsidian

#### Signal: structured frontmatter that remains human-editable

Obsidian properties are typed, YAML-backed, and stored at the top of the file.[8]

**AMD borrow**

- Prefer YAML frontmatter over inline JSON comment blocks for human-maintained artifact metadata.
- Keep the inline metadata minimal and typed.

**Implementation implication**

- AMD v2 should deprecate the large inline JSON metadata comment.
- Source docs should be valid normal Markdown with frontmatter, even when AMD is absent.

#### Signal: templates merge metadata into notes

Obsidian templates support variable expansion and merge properties into the destination note.[8][9]

**AMD borrow**

- Template ergonomics matter.
- Templates should inject the right fields/sections automatically based on kind.

**Implementation implication**

- `amd init --kind report.incident` should not ask the user to pick from random templates.
- The agent seeds config/ with required sections and policy for the kind.
- Template variables should include title, date, actor, project defaults, and label stubs.

#### Signal: views, filters, formulas, summaries

Obsidian Bases define views with filters, formulas, and summaries over structured note data.[10]

**AMD borrow**

- AMD needs a query layer over artifacts, not just single-file commands.
- The human-facing output should feel like “artifact agenda / priority board / stale queue.”

**Implementation implication**

- Add query commands such as:
  - `amd scan`
  - `amd query`
  - `amd agenda`
  - `amd prime`
- Support JSON output first; interactive UIs can be layered later.

#### Signal: history, snapshots, diff, recovery are first-class

Obsidian's file recovery stores snapshots outside the vault, supports diffing, and CLI history/diff operations exist.[11][12][14]

**AMD borrow**

- History should be externally sourced.
- Diff/recovery should not depend on inline timelines.

**Implementation implication**

- The source of truth for history should be:
  - Git
  - append-only AMD journals
  - local rebuildable index
- Inline timeline sections can be rendered summaries, not the primary log.

#### Signal: collaboration exists, but not live editing of one file

Obsidian shared vault docs explicitly say there is no collaborative live editing on the same file; concurrent edits are merged after sync.[13]

**AMD borrow**

- Do not assume live collaborative editing semantics.
- Design for serialized writes and mergeable journals, not shared-cursor editing.

**Implementation implication**

- Same-worktree multi-agent safety should use locks.
- Cross-branch safety should use append-only journals with Git merge rules.

### 3. Quarto

#### Signal: refresh modes and freeze semantics

Quarto supports `freeze: true` and `freeze: auto` so expensive computational documents are not blindly re-executed during global renders.[15]

**AMD borrow**

- AMD needs refresh policy modes.
- Heavy recomputation should be a policy decision, not default behavior.

**Implementation implication**

- AMD should support at least:
  - `live`: recompute eagerly
  - `auto`: recompute only when relevant source changes
  - `frozen`: never recompute unless forced
  - `manual`: recompute only via explicit command

#### Signal: incremental render vs full project render

Quarto distinguishes incremental render from global project render, while still keeping project semantics.[15]

**AMD borrow**

- Refreshing one artifact should not imply recomputing every derived artifact.
- Scanning the project should not imply materializing every inline projection.

**Implementation implication**

- Split AMD operations into:
  - `refresh`: parse, index, score, detect drift
  - `recompute`: update derived artifacts or rollups from source data
  - `materialize`: write projections back into Markdown
  - `build`: full project rebuild/export

#### Signal: pre-render and post-render hooks with environment variables

Quarto supports project `pre-render` and `post-render` scripts and provides environment variables describing input/output files.[16]

**AMD borrow**

- AMD should be automation-friendly without becoming an automation platform itself.

**Implementation implication**

- Add config-driven hooks:
  - `pre-refresh`
  - `post-refresh`
  - `pre-derive`
  - `post-derive`
  - `pre-build`
  - `post-build`
- Export machine-readable context to hooks, e.g.:
  - `AMD_PROJECT_ROOT`
  - `AMD_ACTIVITY_ID`
  - `AMD_CHANGED_ARTIFACTS_FILE`
  - `AMD_CHANGED_LABELS_FILE`
  - `AMD_OUTPUTS_FILE`

### 4. Dendron

#### Signal: kind-driven artifact creation

Dendron explicitly frames schemas and templates as a type system for general knowledge.[17]

**AMD borrow**

- Artifact kinds should be config-driven, not just template-named.
- Templates should be attached to kind definitions, not chosen independently.

**Implementation implication**

- Per-artifact config files in `.amd/config/<artifact_id>.yml` define:
  - kind ID
  - required sections
  - optional sections
  - freshness policy
  - signal definitions
  - derivation contracts

#### Signal: namespace-based organization and hierarchy

Dendron schemas use IDs, patterns, parents, children, and `namespace: true` to define structured note hierarchies.[18]

**AMD borrow**

- Artifact identity can double as organization and query surface.

**Implementation implication**

- Use namespaced kinds and/or artifact IDs such as:
  - `report.incident.payments`
  - `mental_model.payments.authorization`
  - `skill.payments.oncall`
- Inference: namespace-based IDs are more robust query keys than path-only identity.

#### Signal: kind-driven template injection

Dendron schema docs support template application when notes match a schema pattern.[18]

**AMD borrow**

- `amd init` should be deterministic from the kind.

**Implementation implication**

- `amd init --kind mental_model.payments` should always inject the same scaffold — the agent seeds config/ with the kind's required sections and policy.
- No extra user choice is needed for the happy path.

#### Signal: ideas good, product not safe as a hard dependency

Dendron's own March 26, 2023 GitHub discussion says the project moved into maintenance mode.[19]

**AMD borrow**

- Borrow the concepts, not the dependency.

### 5. Org Mode

#### Signal: properties as structured metadata tied to entries, trees, or whole files

Org properties are key-value pairs that can apply to one entry, a tree, or a whole buffer, and they live in a dedicated `PROPERTIES` drawer.[20]

**AMD borrow**

- Narrative, metadata, and logs should be clearly separated.

**Implementation implication**

- AMD source files should keep prose clean.
- Machine-managed fields belong in frontmatter or external state, not mixed arbitrarily into the body.

#### Signal: property inheritance with explicit clearing

Org property inheritance allows parent properties to flow downward; `nil` explicitly stops inheritance.[20]

**AMD borrow**

- AMD project defaults should cascade to artifacts and optionally sections.
- Explicit `null` should stop inheritance.

**Implementation implication**

- Policy resolution order:
  1. artifact frontmatter
  2. per-artifact config/
  3. AMD hardcoded defaults

#### Signal: LOGBOOK-style timestamped state change notes

Org can record timestamped state changes and notes, optionally in a `LOGBOOK` drawer.[21]

**AMD borrow**

- AMD audit records should have a compact, regular event shape:
  - timestamp
  - activity
  - agent
  - event kind
  - summary
  - optional details

**Implementation implication**

- AMD journals should be append-only structured events, not prose changelogs.
- Inline timeline projections can render a LOGBOOK-like view from the journal.

### 6. Mulch

#### Signal: storage != delivery

Mulch stores expertise as typed JSONL and then emits agent-facing “prime” output separately.[22]

**AMD borrow**

- The human artifact and the machine index should not be the same thing.

**Implementation implication**

- Markdown files remain authoring surfaces.
- `.amd/` journals and config are machine state.
- SQLite/JSON exports are rebuildable views over that state.

#### Signal: record types and classification tiers

Mulch uses six record types and three classification tiers (`foundational`, `tactical`, `observational`) to govern shelf life and pruning.[22]

**AMD borrow**

- AMD should classify sections, caveats, and signals by freshness class, not just by artifact kind.

**Implementation implication**

- Suggested AMD freshness classes:
  - `foundational`: rarely stale; mostly mental models, invariants
  - `tactical`: medium shelf life; plans, working context, current strategies
  - `observational`: short shelf life; metrics, run status, live report slices

#### Signal: advisory locking, atomic writes, Git merge strategy

Mulch documents advisory lock files, atomic temp-file writes, and `merge=union` for append-heavy JSONL workflows.[22]

**AMD borrow**

- This is the minimum concurrency discipline AMD needs.

**Implementation implication**

- Same-worktree writes:
  - acquire lock with `O_CREAT|O_EXCL`
  - retry briefly
  - clear stale lock
  - write temp file
  - atomic rename
- Cross-branch merges:
  - use append-only journals
  - set `merge=union` only for those journal files

#### Signal: command safety tiers

Mulch distinguishes read-only commands, locked-write commands, and serialized setup operations.[22]

**AMD borrow**

- AMD CLI should make concurrency safety visible, not implicit.

**Implementation implication**

- AMD command classes:
  - read-only: `scan`, `query`, `prime`, `export`
  - locked writes: `event`, `caveat`, `signal`, `derive`, `recompute`, `materialize`
  - setup ops: `init`, `config edit`, `hook install`

## Foundational Standards And Literature

### 1. Structured change detection in hierarchical documents

Chawathe et al. (1996) is the classic reference for change detection in hierarchically structured information.[23]

**Why it matters**

- AMD is dealing with structured documents, not flat text blobs.
- Change identity should survive tree edits better than line diff.

**AMD implication**

- Section identity and diffing should be tree-aware.
- Moves should not always be treated as deletion-plus-addition.

### 2. Fine-grained change detection in structured text documents

Dohrn and Riehle (2014) explicitly argue that purely textual change detection is too weak for structured text, and tree-to-tree methods alone are too coarse if text nodes are treated as black boxes.[24]

**Why it matters**

- Markdown reports are structured text, not source code.
- AMD needs both structure sensitivity and text sensitivity.

**AMD implication**

- Fingerprinting should combine:
  - AST structure
  - normalized text content
  - move-aware section identity

### 3. AST differencing focused on developer intent

Falleri et al. (GumTree, 2014) argues that AST differencing should aim to reflect developer intent rather than only line additions/deletions, and should include move/update actions.[25]

**Why it matters**

- This is the right mental model for AMD fingerprinting:
  - detect changes that matter
  - avoid noise from formatting or relocation

**AMD implication**

- AMD should classify document changes as:
  - lexical only
  - structural
  - moved/reordered
  - derivation-relevant
  - policy-relevant

### 4. Provenance as entity + activity + agent

W3C PROV-DM defines provenance in terms of entities, activities, and agents, plus relations like attribution, association, and derivation.[26]

**Why it matters**

- AMD is fundamentally about traceability.
- PROV gives a standard conceptual model instead of inventing ad hoc metadata.

**AMD implication**

- Model AMD events and derivations as provenance records.
- Suggested mapping:
  - artifact or section = entity
  - refresh / derive / recompute / signal-ingest = activity
  - user / model / tool / automation = agent
  - template / transform plan = plan

### 5. Concurrency beyond ad hoc merge behavior

Shapiro et al. (2011) formalizes CRDTs as a way to allow replica updates without coordination while still guaranteeing convergence under strong eventual consistency.[27]

**Why it matters**

- AMD is a multi-agent system.
- If AMD eventually wants branchless, simultaneous multi-agent editing of shared state, CRDT thinking is relevant.

**AMD implication**

- `Inference`: AMD should **not** start with CRDTs for all document writes.
- AMD should first use lock-based serialized writes plus mergeable append-only journals.
- CRDTs are a later-stage option for specialized replicated state, not the first implementation target.

### 6. Freshness should be modeled, not guessed from file modification time

Sun et al. define age-of-information as how old the freshest received update is since it was generated, and show that “always update immediately” is not always optimal.[28]

**Why it matters**

- AMD's stale-data problem is not just “last file modified.”
- Different artifacts and signals have different useful ages and different penalties for staleness.

**AMD implication**

- Use section-level freshness with class-specific thresholds.
- Model freshness as age plus penalty, not only timestamps.
- Heavy timeseries should update rollups incrementally; refresh should not blindly recompute everything.

## Design Principles For AMD v2

1. **Source documents remain readable without AMD.**
2. **Machine state is external and rebuildable.**
3. **Write amplification to Markdown must be minimized.**
4. **Stable IDs matter more than heading text.**
5. **Fingerprints must be structural, not purely lexical.**
6. **History belongs in Git plus journals, not only inline.**
7. **Refresh and recomputation are separate operations.**
8. **Derivations must be reproducible and provenance-linked.**
9. **Policy is hierarchical and inheritable.**
10. **Concurrency safety is a prerequisite, not an enhancement.**

## Proposed Architecture

### 1. Source Layer

The authoring surface is normal Markdown, optionally MyST-compatible.

Recommended source shape:

```md
---
amd:
  id: report.payments.incident-2026-03-11
  kind: report.incident.payments
  title: Payments Incident Report
  labels:
    artifact: payments-incident
  policy:
    freshness_class: tactical
    refresh_mode: auto
---

# Payments Incident Report

<!-- amd:label executive-summary -->
## Executive Summary

...

<!-- amd:label risk-assessment -->
## Risk Assessment

...
```

Notes:

- AMD should accept plain `.md` and `.amd.md`.
- Long term, `.md` plus AMD frontmatter is the cleaner direction.
- AMD should understand MyST labels when present.[2][7]

### 2. Project Config Layer

Project defaults live in `.amd/config.yml`.

Suggested contents:

```yaml
defaults:
  refresh_mode: auto
  freshness_class: tactical
  stale_after: 24h
  priority:
    manual: 50
  timeseries:
    windows: [1h, 24h, 7d]

kinds:
  report.incident:
    freshness_class: observational
    stale_after: 4h
  mental_model:
    freshness_class: foundational
    stale_after: 168h

hooks:
  pre-refresh: scripts/pre_refresh.py
  post-derive: scripts/post_derive.py
```

### 3. Journal Layer

The concurrency-safe source of machine truth should be append-only journals in `.amd/`. All `.amd/` contents are metadata — identity, relations, temporal data, context signals — never document content.

Suggested layout:

```text
.amd/
  config/
    report.payments.incident-2026-03-11.yml   # Per-artifact config
  journal/
    report.payments.incident-2026-03-11.jsonl   # Per-artifact JournalRecords
    _project.jsonl                               # Project-level records
  signals/
    report.payments.incident-2026-03-11.jsonl   # Per-artifact SignalPoints
  cache/
    index.sqlite
  export/
    amd.xref.json
    artifacts/
```

Rules:

- Journals are git-tracked.
- `index.sqlite` is rebuildable and should usually be gitignored.
- Signals can be local JSONL by default, with external-store references for heavy workloads.

### 4. Index Layer

AMD needs a local query/index layer.

Recommended design:

- SQLite as the local index/cache
- Rebuildable from source docs plus journals
- Exportable to JSON manifests for external tools

Suggested tables:

- `artifacts`
- `sections`
- `section_fingerprints`
- `activities`
- `agents`
- `caveats`
- `signals_rollup`
- `derivations`
- `policy_resolution`

`Inference`: SQLite is the best default because AMD needs local joins, sorting, filtering, and rebuildable state. It is a better fit than keeping all computed state inline in Markdown, and a better git story than treating SQLite itself as the shared source of truth.

### 5. Projection Layer

Inline timeline sections and status summaries should be generated projections.

Examples:

- `amd materialize path/to/report.md`
- `amd materialize --all`

Materialization should update:

- status badge block
- inline timeline summary
- latest caveats summary
- signal rollup summary
- derivation provenance block

But the source of truth remains journals + index, not the inline projection.

## Provenance Model

AMD should adopt a PROV-like internal vocabulary.[26]

### Entities

- artifact
- section
- generated block
- signal window
- template


### Activities

- init
- refresh
- recompute
- materialize
- derive
- caveat.create
- caveat.resolve
- signal.ingest
- policy.evaluate

### Agents

- user
- assistant/model
- tool
- automation

### Relations

- `wasDerivedFrom`
- `wasAttributedTo`
- `wasAssociatedWith`
- `used`
- `wasGeneratedBy`

### Why this matters

This lets AMD answer questions like:

- Which model/user/tool last changed this derived skill?
- Which source sections did this runbook come from?
- What signal or caveat caused this artifact's priority to jump?
- Was this summary refreshed or only materialized from cached results?

## Per-Artifact Config And Template System

### Config shape

Per-artifact config files hold operational parameters and structural expectations. Borrowing the kind-driven creation idea from Dendron,[17][18] but using per-artifact config instead of a separate schema subsystem.

Suggested config fields:

```yaml
kind: report.incident
freshness_class: observational
stale_after: 4h
required_sections:
  - executive-summary
  - current-context
  - risk-assessment
  - caveats
optional_sections:
  - timeline
  - appendices
derive:
  targets:
    report.postmortem:
      mappings:
        - from: executive-summary
          to: incident-summary
```

### Template rules

- Templates are chosen by kind, not by user whim.
- Templates may contain label stubs.
- Templates may contain generated-block placeholders.
- Templates may contain policy hints, but those are resolved in config/index, not trusted as final truth.

### Mental model to skill derivation

AMD's current `derive-skill` behavior is too weak.

V2 derivation should:

- require labeled source inputs
- use a declared transform spec
- emit provenance
- preserve user-authored target sections
- support re-derivation without clobbering local edits

Recommended target model:

- generated sections are marked as generated
- user-owned sections stay separate
- re-derivation updates only generated blocks unless `--force` is used

## Stable Labels And Identity

### Artifact identity

Artifact IDs should not depend only on file paths.

Recommended:

- explicit frontmatter `amd.id`
- if absent, AMD generates one once and preserves it

### Section identity

Section IDs should not depend only on heading text or ordinal position.

Recommended resolution order:

1. explicit AMD label comment
2. MyST label
3. generated stable ID seeded from first-seen heading + artifact ID and then persisted in the index

### Move behavior

`Inference`: if a section is reordered or moved to a different file but keeps its stable label, AMD should treat it as the same logical section with a move, not a deletion-plus-new-section event.

This is the entire reason to avoid heading-text-only identity.

## Fingerprinting Design

### Objective

Fingerprinting should detect meaningful changes in a 500-line report without firing on every reflow.

### Borrowed principles

- hierarchical change detection matters for structured data.[23]
- structured text diff needs both tree sensitivity and text sensitivity.[24]
- AST differencing should better reflect intent and support move/update, not just delete/add.[25]
- MyST provides mdast-based structure and transform hooks.[5][6][7]

### Proposed pipeline

1. Parse Markdown to AST.
2. Resolve labels and section boundaries.
3. Normalize the AST:
   - remove source positions
   - normalize whitespace-only text nodes
   - ignore generated numbering/enumerators
   - strip rendered timeline projections
   - strip computed status blocks
4. Hash:
   - artifact AST
   - labeled section ASTs
   - generated-block ASTs
5. Compare against prior indexed fingerprints.
6. Classify the change:
   - `none`
   - `lexical`
   - `structural`
   - `move`
   - `derivation_relevant`
   - `policy_relevant`

### Why AST-aware matters

Raw text hashing confuses:

- whitespace change
- heading reflow
- numbering changes
- section reorder
- generated block refresh

with substantive change.

AST-aware normalization reduces that noise.

### Stretch goal

`Inference`: later AMD can add a secondary semantic layer on top of the structural fingerprint, but the first improvement should be structural normalization, not LLM-based semantic diff.

## Freshness, Staleness, And Priority

### Freshness model

AMD should treat freshness as a policy problem, not a file timestamp.

Borrowed signals:

- Mulch classification tiers for shelf life.[22]
- Quarto freeze modes for recomputation control.[15]
- Age-of-information for measuring how old the freshest useful update is.[28]

### Suggested freshness classes

- `foundational`
  - mental models
  - core invariants
  - architecture overviews
  - low decay rate
- `tactical`
  - work plans
  - live context
  - current hypotheses
  - medium decay rate
- `observational`
  - metrics
  - status summaries
  - rolling incident notes
  - short decay rate

### Suggested freshness fields

At artifact, section, and generated-block level:

- `freshness_class`
- `refresh_mode`
- `last_verified_at`
- `last_source_change_at`
- `last_signal_at`
- `stale_after`
- `age_penalty`
- `is_stale`
- `stale_reason`

### Refresh modes

- `live`
- `auto`
- `frozen`
- `manual`

### Priority scoring

Priority should be computed in the index, not hand-maintained in Markdown.

Suggested components:

- manual baseline
- staleness penalty
- active caveat penalty
- unseen-signal penalty
- derivation-drift penalty
- user pin/boost

Illustrative formula:

```text
priority =
  manual
  + freshness_penalty
  + caveat_penalty
  + signal_penalty
  + derivation_penalty
  + pin_bonus
```

The exact coefficients should be configurable.

### Expected-cadence freshness

`Inference`: for timeseries-backed artifacts, freshness should consider expected update cadence.

Example:

- if a signal normally arrives every 5 minutes, 30 minutes of silence may be stale
- if a model changes monthly, 48 hours is irrelevant

This is better than one global `stale_after_hours`.

## Caveat System

AMD already has the right intuition here. V2 needs a stronger model.

Suggested caveat fields:

- `id`
- `applies_to`
  - artifact
  - section
  - derivation
  - signal
- `severity`
  - low / medium / high / critical
- `text`
- `created_at`
- `created_by`
- `expires_at`
- `state`
  - active / mitigated / expired / superseded
- `evidence_refs`
- `invalidates_labels`
- `resolution_activity_id`

Why:

- caveats are policy inputs
- caveats affect scan/prime output
- caveats should be queryable and expirable
- caveats should be provenance-linked

## Timeseries Strategy

### What AMD should do

AMD should be **timeseries-informed**, not a full TSDB.

### Default strategy

- Keep low-to-medium volume signals as append-only JSONL, git-tracked.
- Maintain incremental rollups in the local index.
- Materialize only summaries into docs.

### Heavy-data strategy

For truly heavy signal streams:

- store only references and rollup checkpoints in AMD journals
- allow adapters to external stores such as DuckDB/Parquet/data warehouse
- keep artifact-local summaries in the index

`Inference`: the default git-native format should stay append-friendly. Parquet is better for analytics than git merges, so it should be optional or external-facing, not the default shared source format.

### Rollup windows

Suggested standard windows:

- 15m
- 1h
- 6h
- 24h
- 7d

### Required rollup fields

- `latest_at`
- `latest_value`
- `count`
- `min`
- `max`
- `mean`
- `slope` or trend direction
- `cadence_health`
- `source_offset` or checkpoint

### Refresh rule

Never rescan the full signal history on every refresh when incremental checkpoints are available.

## Audit And Timeline Design

### Source of truth

Audit should live in:

- Git
- append-only AMD journals

### Projection

The Markdown file may include a rendered timeline section, but it is generated from the journal.

Suggested event shape:

```json
{
  "id": "evt_...",
  "timestamp": "2026-03-11T12:00:00Z",
  "activity": "derive",
  "agent": "codex",
  "artifact_id": "skill.payments.oncall",
  "section_id": "workflow",
  "summary": "Re-derived workflow from latest mental model",
  "details": {
    "source_artifact_id": "mental_model.payments.authorization",
    "changed_labels": ["decision-rules", "failure-modes"]
  }
}
```

### Why this is better than inline-only timelines

- safer multi-agent writes
- queryable without parsing prose
- renderable in different formats
- usable by `scan`, `query`, `prime`, and exports

## Concurrency And Write Discipline

### Required baseline

Borrow directly from Mulch's documented safety model for append-heavy multi-agent writes.[22]

### Same-worktree write protocol

1. acquire per-target lock file using `O_CREAT|O_EXCL`
2. retry briefly
3. clean stale locks
4. write temp file
5. atomically rename into place
6. release lock

### Cross-branch protocol

- journal files use `merge=union`
- artifact Markdown files do not
- after merge, AMD can deduplicate or reconcile journal events

### Command safety classes

- read-only:
  - `scan`
  - `query`
  - `prime`
  - `export`
- locked write:
  - `event`
  - `caveat`
  - `signal`
  - `derive`
  - `recompute`
  - `materialize`
- serialized setup:
  - `init`

  - `hook install`
  - `config edit`

### Why not CRDT first

CRDTs matter when you truly need concurrent, coordination-free updates to replicated shared state.[27]

AMD does not need that first.

The first problem is simpler:

- safe journal writes
- safe projection writes
- stable IDs
- replayable index rebuilds

Solve that before replicated collaborative editing.

## User/Agent Ownership Boundaries

This is essential because “only the user knows the context” is true more often than not.

Recommended rule:

- user-owned prose stays user-owned
- machine-owned blocks are clearly marked
- agent-suggested edits should be explicit

Suggested ownership categories:

- `user`
- `agent`
- `generated`
- `mixed`

Practical implication:

- AMD should not silently rewrite arbitrary prose sections during routine refresh
- AMD should only auto-update:
  - generated projections
  - generated blocks
  - index/journal state

## Command Surface

AMD is an agent-native CLI. The primary consumers are AI agents (Claude Code, Codex, etc.) that invoke these commands programmatically. Agents dynamically create artifacts, record events, query the graph, derive new documents, and rebuild structure as understanding evolves. The graph in `.amd/` is live working state, not a static archive.

Suggested v2 command model:

- `amd init`
- `amd refresh`
- `amd recompute`
- `amd materialize`
- `amd derive`
- `amd event`
- `amd caveat`
- `amd signal`
- `amd scan`
- `amd query`
- `amd agenda`
- `amd prime`
- `amd export`
- `amd doctor`
- `amd reindex`

### Semantics

- `refresh`: parse, fingerprint, re-evaluate policy, update local index
- `recompute`: perform expensive derivation or signal-rollup work
- `materialize`: write projections into Markdown
- `derive`: perform declared transforms between artifacts
- `prime`: emit agent-facing context pack from the index
- `doctor`: validate journals, required sections, labels, and projections

## Prime / Context Delivery

Mulch's `prime` concept is directly relevant.[22]

AMD should have an `amd prime` command that emits context optimized for agents:

- highest-priority artifacts
- only relevant sections
- active caveats first
- freshness notes
- recent derivation changes
- recent signals

This is how AMD solves “more than just read/write Markdown” without inventing a closed file format.

## Machine-Readable Export

AMD should export a site/project manifest analogous to MyST's metadata exposure.[3]

Suggested files:

- `.amd/export/amd.xref.json`
- `.amd/export/artifacts/<artifact_id>.json`

Suggested `amd.xref.json` entries:

- `artifact_id`
- `kind`
- `path`
- `title`
- `labels`
- `priority`
- `is_stale`
- `data`

Suggested per-artifact JSON:

- frontmatter
- source location
- parsed section list
- fingerprints
- caveats
- rollups
- derivation edges
- provenance activity summary

## Testing And Verification Plan

### 1. Parser and label tests

- label recognition for AMD comments and MyST labels
- heading move with stable identity preserved
- unlabeled section gets stable generated ID

### 2. Fingerprint tests

- whitespace-only edits do not trigger structural drift
- numbering-only changes do not trigger structural drift
- heading rename with same label is an update, not a delete/add
- section move registers as move

### 3. Concurrency tests

- concurrent journal appends do not corrupt data
- projection materialization serializes safely
- crash during write leaves previous file intact
- stale locks are detected and cleared correctly

### 4. Policy tests

- inheritance resolution
- explicit `null` override
- freshness calculation by class
- priority scoring with caveats and signal cadence

### 5. Derivation tests

- deterministic outputs from the same inputs
- provenance edges emitted correctly
- re-derive preserves user-owned blocks
- frozen derivation does not recompute unless forced

### 6. Rebuild tests

- delete local SQLite index and rebuild from source docs + journals
- export manifest matches rebuilt index

## Recommended Rollout Phases

### Phase 0: Parser spike and file model decision

Goal:

- prove AMD can parse normal Markdown / MyST-compatible Markdown into a stable AST and labeled section graph

Exit criteria:

- sample artifacts parse reliably
- stable labels work
- fingerprint normalization prototype exists

### Phase 1: Externalize machine state

Goal:

- stop treating inline Markdown metadata as the main machine state

Work:

- journals
- rebuildable local index
- export manifest
- frontmatter migration

Exit criteria:

- `refresh` no longer needs to rewrite body text by default

### Phase 2: Safe writes and projection model

Goal:

- eliminate P1 concurrency failures

Work:

- lock files
- atomic writes
- `merge=union` for journals
- materialized timeline projection

Exit criteria:

- concurrent write stress test passes

### Phase 3: Config and derivation system

Goal:

- real artifact kinds and reproducible transforms

Work:

- per-artifact config with required sections
- template binding
- derivation rules
- generated block ownership

Exit criteria:

- mental model -> skill derivation is provenance-backed and re-runnable

### Phase 4: Freshness, priority, caveats, signals

Goal:

- make AMD genuinely policy-driven

Work:

- freshness classes
- cadence-aware signal freshness
- caveat rules
- rollups
- agenda/scan ranking

Exit criteria:

- `scan` and `prime` surface meaningful ranked outputs

### Phase 5: Hooks, exports, integrations

Goal:

- make AMD fit real workflows

Work:

- pre/post hooks
- JSON exports
- editor integration
- scheduled automation

Exit criteria:

- AMD integrates cleanly into repo workflows without requiring a bespoke UI

## Risks And Tradeoffs

### 1. MyST compatibility vs plain-Markdown purity

Risk:

- richer labels and structure often imply syntax beyond pure CommonMark

Mitigation:

- support both AMD label comments and MyST labels
- keep documents valid Markdown

### 2. Too much inline automation

Risk:

- agents rewriting prose sections create noise and trust problems

Mitigation:

- keep auto-writes to generated blocks and projections

### 3. SQLite as shared truth

Risk:

- git-hostile

Mitigation:

- SQLite is local cache only
- journals are shared truth

### 4. CRDT temptation too early

Risk:

- complexity explosion

Mitigation:

- use lock-based writes first

### 5. Overfitting to one editor or product

Risk:

- AMD becomes “Obsidian but worse” or “MyST wrapper”

Mitigation:

- borrow patterns, not dependencies

## Final Recommendation

AMD v2 should be built around this formula:

```text
Markdown/MyST-compatible source
+ project-level policy config
+ append-only journals
+ rebuildable local index
+ structural fingerprints
+ provenance model
+ config-driven derivation
+ Quarto-style refresh modes and hooks
= AMD
```

The highest-value borrowings are:

1. MyST's AST/labels/machine-readable index model.[1][2][3][5][6][7]
2. Mulch's write safety, classification tiers, and storage-vs-delivery discipline.[22]
3. Quarto's refresh/recompute split and hook model.[15][16]
4. Dendron's kind-driven creation model.[17][18]
5. Org's inheritance and LOGBOOK-like audit ideas.[20][21]
6. PROV's entity/activity/agent model for traceability.[26]
7. Structured-diff literature instead of raw hashes.[23][24][25]

If AMD implements those well, it becomes a real product category.

If it does not, it remains a wrapper around Markdown that other tools already approximate.

## Annotated Sources

[1] MyST Markdown, “Content frontmatter options.” Official docs. Page/project field placement, page overrides, labels, and field behavior. <https://mystmd.org/guide/frontmatter>

[2] MyST Markdown, “Cross-references.” Official docs. Labels, identifiers, reference targets, and label-anything behavior. <https://mystmd.org/guide/cross-references>

[3] MyST Markdown, “Exposing MyST and Document Metadata.” Official docs. `myst.xref.json`, per-page JSON, AST/frontmatter/source location exposure. <https://mystmd.org/guide/website-metadata>

[4] MyST Markdown, “Directives.” Official docs. `code-cell` labels, captions, numbering, and executable content metadata. <https://mystmd.org/guide/directives>

[5] MyST Markdown, “Plugins.” Official docs. AST transforms and plugin extension points. <https://mystmd.org/guide/plugins>

[6] MyST Transforms, “Enumeration.” Official docs. Target enumeration and reference-resolution transform stages. <https://mystmd.org/myst-transforms/enumeration>

[7] MyST Specification, “CommonMark.” Official docs. mdast support and AST fields such as `identifier` and `label`. <https://mystmd.org/spec/commonmark>

[8] Obsidian Help, “Properties.” Official docs. Typed YAML-backed properties, template property merge, and explicit limitations. <https://help.obsidian.md/properties>

[9] Obsidian Help, “Templates.” Official docs. Template variables and note/template behavior. <https://help.obsidian.md/Plugins/Templates>

[10] Obsidian Help, “Bases syntax.” Official docs. YAML-defined views, filters, formulas, and summaries. <https://help.obsidian.md/bases/syntax>

[11] Obsidian Help, “CLI.” Official docs. Diff/history/sync-history commands and file operations. <https://help.obsidian.md/cli>

[12] Obsidian Help, “File recovery.” Official docs. Snapshotting outside the vault, restore behavior, and diffs between snapshots. <https://help.obsidian.md/plugins/file-recovery>

[13] Obsidian Help, “Collaborate on a shared vault.” Official docs. Collaboration limits, no live editing on same file, and merge-after-sync behavior. <https://help.obsidian.md/sync/collaborate>

[14] Obsidian Help, “Version history.” Official help page/search snippet. Sync history, version retention, restore workflow, and collaboration visibility. <https://help.obsidian.md/Obsidian%2BSync/Version%2Bhistory>

[15] Quarto Docs, “Managing Execution.” Official docs. Incremental render and `freeze: true` / `freeze: auto` semantics. <https://quarto.org/docs/projects/code-execution.html>

[16] Quarto Docs, “Project Scripts.” Official docs. `pre-render`, `post-render`, and render-related environment variables. <https://quarto.org/docs/projects/scripts.html>

[17] Dendron homepage. Product framing for schemas/templates as a type system and structured knowledge hierarchy. <https://www.dendron.so/>

[18] Dendron Wiki, “Schemas.” Official docs. YAML schema anatomy, parents, children, namespace, patterns, and template binding. <https://wiki.dendron.so/notes/c5e5adde-5459-409b-b34d-a0d75cbb1052/>

[19] GitHub Discussion, “Development stopped?” in `dendronhq/dendron`. Official project discussion stating maintenance mode moving forward. <https://github.com/dendronhq/dendron/discussions/3890>

[20] The Org Manual. Official docs for properties, property syntax, and property inheritance. Relevant sections: properties can apply to entries/trees/buffers; inheritance can be enabled and explicitly stopped with `nil`. <https://orgmode.org/org.html> and <https://orgmode.org/manual/Property-Inheritance.html>

[21] The Org Manual, “Tracking TODO state changes.” Official docs. Timestamped change notes, drawer use, and recommended `LOGBOOK` behavior. <https://orgmode.org/manual/Tracking-TODO-state-changes.html>

[22] Jaymin West, “Mulch README.” Primary repo documentation. Typed JSONL, classification tiers, storage-vs-delivery, advisory locking, atomic writes, `merge=union`, and command safety tiers. <https://raw.githubusercontent.com/jayminwest/mulch/main/README.md>

[23] Sudarshan S. Chawathe, Anand Rajaraman, Hector Garcia-Molina, Jennifer Widom, “Change Detection in Hierarchically Structured Information” (1996). Foundational structured change-detection reference. <https://sigmodrecord.org/1996/06/24/change-detection-in-hierarchically-structured-information/>

[24] Hannes Dohrn and Dirk Riehle, “Fine-grained Change Detection in Structured Text Documents” (DocEng 2014). Structured-text diff work directly relevant to report-scale Markdown. <https://dirkriehle.com/2014/09/16/fine-grained-change-detection-in-structured-text-documents-doceng-2014/>

[25] Jean-Remy Falleri, Floreal Morandat, Xavier Blanc, Matias Martinez, Martin Monperrus, “Fine-grained and Accurate Source Code Differencing” (ASE 2014). AST differencing, move/update awareness, and edit scripts closer to developer intent. <https://www.labri.fr/perso/xblanc/data/papers/ASE14.pdf>

[26] W3C, “PROV-DM: The PROV Data Model.” W3C provenance standard defining entities, activities, agents, attribution, association, and derivation. <https://www.w3.org/TR/2013/PR-prov-dm-20130312/>

[27] Marc Shapiro, Nuno Preguica, Carlos Baquero, Marek Zawirski, “Conflict-free Replicated Data Types” (2011). Foundational CRDT reference for strong eventual consistency and convergence. <https://people.eecs.berkeley.edu/~kubitron/courses/cs262a-F19/handouts/papers/Shapiro-CRDT.pdf>

[28] Yin Sun, Elif Uysal-Biyikoglu, Roy D. Yates, C. Emre Koksal, Ness B. Shroff, “Update or Wait: How to Keep Your Data Fresh” (2017). Age-of-information and age-penalty model for freshness beyond naive timestamping. <https://arxiv.org/abs/1601.02284>
