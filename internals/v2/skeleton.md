# AMD v2 Skeleton

This document restructures the scaffold's research into a buildable feature/requirement list.
Each feature states: what it is, why it matters, what v1 has, and how v2 achieves it.

## Foundational Constraints

**`.amd/` is metadata only.** It stores identity records, relation edges, temporal data (activity journals, event logs, signal rollups), and context signals. Zero document content. The user's Markdown files live wherever the user puts them. `.amd/` only knows *about* them.

**AMD is an agent-native CLI.** The primary consumers are AI agents — Claude Code, Codex, and similar — that invoke AMD commands at machine speed and volume. Agents dynamically create artifacts, record events, query the graph, derive new documents, and break/rebuild structure as understanding evolves. The graph in `.amd/` is live working state that changes every session. Humans can use the CLI directly, but the design optimizes for programmatic agent consumption.

**AMD has two layers of types: core types and per-artifact config.** Core types are internal data contracts defined in AMD's own source code (Pydantic models). They govern how AMD's journal, signal, index, and temporal systems operate. Examples: `JournalRecord`, `SignalPoint`, `SignalRollup`, `ArtifactTemporalState`, `SectionTemporalState`. Per-artifact config files live in `.amd/config/<artifact_id>.yml` and vary per project — they hold operational parameters like freshness policy, signal definitions, derive contracts, and required sections. Artifact frontmatter carries local one-off overrides. The same core/agent split that applies to behavior (core computes, agents decide) applies to types: core types are the fixed machinery, per-artifact config is the project-specific semantics that ride on top. Within core types, JSONL-backed records (`JournalRecord`, `SignalPoint`) have a further split: a thin mandatory core envelope (fields AMD needs for computation) and a flexible agent/user context layer (fields the agent shapes per domain). Core reads the envelope and stores the rest faithfully without validating it. Derived types like `SignalRollup` and `ArtifactTemporalState` are entirely core-owned — computed by core, read by agents.

---

## F1. Source Format: Plain Markdown With Minimal Frontmatter

### Goal
AMD artifacts should be normal Markdown files that render and read correctly without AMD installed.

### Why
V1 embeds a large JSON blob inside an HTML comment at the top of every file. This is fragile, unreadable, and hostile to manual editing. The scaffold calls this out as the first gap to fix.

### What V1 Has
- `<!-- amd:meta { ... } -->` block containing all machine state inline: fingerprints, freshness, priority, caveats, timeseries summary, agents, status.
- `.amd.md` file extension.
- Four hardcoded template bodies (task, report, mental-model, skill-derived).

### V2 Approach
- Replace the inline JSON comment with a small YAML frontmatter block under an `amd:` key.
- Frontmatter contains only identity and policy overrides: `id`, `kind`, `title`, `labels`, `policy`, `derive`.
- All computed state (fingerprints, freshness scores, priority, signal rollups) moves to the external index.
- Accept both `.md` and `.amd.md`. Prefer `.md` long-term.
- Section labels via `<!-- amd:label <name> -->` HTML comments or MyST-style labels.

### Frontmatter Shape

```yaml
---
amd:
  id: report.payments.incident-2026-03-11
  kind: report.incident
  title: Payments Incident Report
  labels:
    artifact: payments-incident
  policy:
    freshness_class: tactical
    refresh_mode: auto
---
```

### What Stays In The File
- Identity (id, kind, title, labels)
- Policy overrides (only if different from config/ defaults)
- Derive declarations (only if this artifact has derivation outputs)
- Section label comments in the body
- Optionally: materialized projection blocks (generated, clearly marked)

### What Leaves The File
- Fingerprints
- Freshness scores and timestamps
- Priority (manual baseline can stay in frontmatter; computed score is in index)
- Caveats (move to journal; summary can be materialized back)
- Timeseries summaries
- Agent contributor lists
- Status field (computed from freshness/caveats in index)

---

## F2. Stable Section Identity

### Goal
Sections should have IDs that survive heading renames, reordering, and file moves.

### Why
V1 identifies sections by `level:heading_text` keys. Renaming a heading looks like a deletion plus a new section, which triggers false drift. The structured-diff literature (Chawathe 1996, Dohrn & Riehle 2014, GumTree 2014) all argue that identity should be structural, not textual.

### What V1 Has
- `extract_sections(body)` parses headings by regex and keys them as `"2:Current Context"`.
- No stable IDs. No move detection.

### V2 Approach
- Three-tier resolution for section identity:
  1. Explicit AMD label comment: `<!-- amd:label risk-assessment -->`
  2. MyST-style label (if present)
  3. Auto-generated stable ID seeded from first-seen heading text + artifact ID, persisted in the index on first encounter
- Section moves (same label, different position or file) are tracked as moves, not delete+create.
- The index maps `artifact_id + section_id` as the canonical reference target.

---

## F3. Project Config

### Goal
Project-wide defaults, kind definitions, and hook declarations live in one place, not repeated per artifact.

### Why
V1 has no project config. Every artifact carries its own full metadata. Policy like `stale_after_hours` is per-file with no inheritance. The scaffold borrows MyST's project/page override model and Org's property inheritance.

### What V1 Has
- Nothing. All defaults are hardcoded in `core.py`.

### V2 Approach
- Per-artifact config in `.amd/config/<artifact_id>.yml` holds operational parameters.
- Policy resolution order: artifact frontmatter > per-artifact config/ > AMD hardcoded defaults.
- Explicit `null` in frontmatter means "clear the inherited value back to hardcoded default."
- No global config file. No schemas. Hardcode what doesn't need tuning in v2.

### Config Shape

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

---

## F4. Per-Artifact Config And Section Validation

### Goal
Each artifact's operational parameters — freshness policy, required sections, signal definitions, derive contracts — should live in a per-artifact config file. Section validation uses the section tree already in SQLite.

### Why
V1 has four hardcoded kinds in `templates.py` with no validation, no required sections, and no connection between kind and policy. The original v2 scaffold proposed a schema-as-type-system model, but per-artifact config plus SQLite covers everything schemas would have done without a separate subsystem.

### What V1 Has
- `templates.py` with four render functions: `render_task_template`, `render_report_template`, `render_mental_model_template`, `render_skill_derived_template`.
- Kind is a string field in metadata. No enforcement.

### V2 Approach
- Per-artifact config files live in `.amd/config/<artifact_id>.yml`.
- Config defines: kind, freshness policy, required/optional sections, signal definitions, derive contracts.
- `amd init --kind report.incident` — the agent seeds the config file with kind-appropriate values.
- Validation: `amd doctor` compares `required_sections` from config/ against the section tree in SQLite.
- No separate schema files. No global config.

### Config Shape

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

---

## F5. Journal Layer (Append-Only Machine History)

### Goal
All machine-generated events, caveats, and derivation records are append-only structured logs, not inline Markdown edits.

### Why
V1 appends timeline entries directly into the Markdown body between `<!-- amd:timeline:start -->` and `<!-- amd:timeline:end -->` markers. This means every `event`, `caveat`, or `signal` call rewrites the entire file, creating write contention under concurrency. The scaffold identifies this as the core architectural flaw.

### What V1 Has
- Timeline entries are plain text lines appended inside the Markdown body.
- Caveats are stored in the inline JSON metadata block.
- Timeseries signals go to `.amd/data/<artifact_id>.jsonl` — this is already the right shape, just not generalized.

### V2 Approach
- All machine writes go to append-only JSONL files under `.amd/journal/`.
- Layout:
  ```
  .amd/
    journal/
      <artifact_id>.jsonl     # JournalRecords, per-artifact
      _project.jsonl          # Project-level records (e.g. refresh_run)
    signals/
      <artifact_id>.jsonl     # SignalPoint records, per-artifact
  ```
- Journals are git-tracked.
- Journals use `merge=union` in `.gitattributes` for safe cross-branch merges.
- The inline Markdown timeline becomes a materialized projection from journal data, not the source of truth.

### JournalRecord Shape

```json
{
  "activity_id": "act_01",
  "activity_type": "derivation_updated",
  "artifact_id": "skill.payments.oncall",
  "occurred_at": "2026-03-11T12:00:00Z",
  "recorded_at": "2026-03-11T12:00:01Z",
  "actor": "codex",
  "summary": "Re-derived workflow from latest mental model",
  "detail_json": {
    "source_artifact_id": "mental_model.payments.authorization",
    "source_section_ids": ["decision-rules", "failure-modes"],
    "target_section_ids": ["workflow"]
  }
}
```

The first five fields (`activity_id` through `recorded_at`) are the core envelope — AMD core requires these. Everything else is agent/user context — core stores it but does not validate or interpret it. See the temporal-context-handling plan for the full `JournalRecord` spec and activity type reference.

### What V1's Timeseries Sidecar Becomes
- V1's `.amd/data/<id>.jsonl` moves to `.amd/signals/<id>.jsonl`.
- Same append-only JSONL shape.
- Signal rollups are computed incrementally in the index, not by rescanning full history.

---

## F6. Rebuildable Local Index

### Goal
A local SQLite database serves as the query/join/ranking layer. It is cache, not shared truth.

### Why
V1 has no index. Every `scan` or priority check reparses files. The scaffold argues that freshness scoring, priority ranking, cross-artifact queries, and derivation-edge tracking all need joins and sorting that are expensive to do by reparsing Markdown on every call.

### What V1 Has
- `scan_artifact(path)` reads and parses one file at a time.
- `refresh_tree(root)` walks the filesystem and refreshes sequentially.
- No persistent query state between commands.

### V2 Approach
- `.amd/cache/index.sqlite` is the local index.
- Gitignored (rebuildable from source files + journals).
- `amd reindex` rebuilds it from scratch.
- `amd refresh` updates it incrementally.
- All read commands (`scan`, `query`, `agenda`, `prime`, `export`) read from the index.

### Suggested Tables

| Table | Purpose |
|-------|---------|
| `artifacts` | ID, kind, path, title, labels, policy |
| `sections` | artifact_id, section_id, heading, position, ownership |
| `section_fingerprints` | section_id, structural hash, last_changed_at |
| `activities` | Event journal records indexed for query |
| `agents` | Known agents and their roles |
| `caveats` | Active/resolved caveats with scope and expiry |
| `signals_rollup` | Per-artifact, per-metric windowed rollups |
| `derivations` | Source->target edges with activity links |
| `policy_resolution` | Resolved policy per artifact/section (cached) |

---

## F7. Structural Fingerprinting

### Goal
Detect meaningful content changes without false positives from whitespace, reflow, numbering, or reordering.

### Why
V1 hashes raw extracted section text with SHA256. Any whitespace change, list renumbering, or heading reflow triggers drift. The scaffold draws on three papers (Chawathe 1996, Dohrn & Riehle 2014, GumTree/Falleri 2014) to argue for AST-aware fingerprinting.

### What V1 Has
- `extract_sections(body)` splits by heading regex, hashes each section's raw text.
- `refresh_artifact()` compares current hashes to stored hashes. Any mismatch = drift.

### V2 Approach
- Pipeline:
  1. Parse Markdown to AST (use a MyST-compatible parser or markdown-it)
  2. Resolve labels and section boundaries
  3. Normalize: strip source positions, normalize whitespace-only text nodes, ignore generated numbering, strip materialized projection blocks
  4. Hash normalized AST per section and per artifact
  5. Compare against prior indexed fingerprints
  6. Classify change: `none` | `lexical` | `structural` | `move` | `derivation_relevant` | `policy_relevant`

### What This Fixes
- Whitespace edits stop triggering drift
- Heading renames with stable labels are updates, not delete+create
- Section reorder is a move, not mutation
- Generated projection blocks are excluded from fingerprint

---

## F8. Freshness, Staleness, And Priority

### Goal
Freshness is a policy problem with class-specific thresholds, not just "hours since last file write."

### Why
V1 uses a single `stale_after_hours` per section and a simple additive priority formula. The scaffold borrows Mulch's classification tiers, Quarto's freeze modes, and age-of-information theory to argue for richer freshness modeling.

### What V1 Has
- Per-section `updated_at` + `stale_after_hours` comparison.
- Computed priority: manual + stale_penalty(+5/section, max 20) + caveat_penalty(+5/each, max 20) + signal_penalty(+15 if newer signals).
- No freshness classes. No refresh modes. No cadence awareness.

### V2 Approach

**Freshness classes** (applied to artifacts, sections, or generated blocks):
- `foundational`: mental models, invariants. Low decay. Long `stale_after`.
- `tactical`: plans, working context, hypotheses. Medium decay.
- `observational`: metrics, status summaries, incident notes. Short decay.

**Refresh modes** (control recomputation behavior):
- `live`: recompute eagerly on any change
- `auto`: recompute only when relevant source changes (default)
- `frozen`: never recompute unless forced
- `manual`: recompute only via explicit command

**Priority scoring** (computed in index, not hand-maintained):
```
priority =
  manual_baseline
  + freshness_penalty
  + caveat_penalty
  + signal_penalty
  + derivation_drift_penalty
  + pin_bonus
```
Coefficients configurable in project config.

**Cadence-aware freshness**: for timeseries-backed artifacts, silence beyond expected cadence triggers staleness (e.g., a signal that normally arrives every 5m is stale after 30m of silence).

---

## F9. Caveat System

### Goal
First-class structured caveats with scope, severity, expiry, provenance, and policy impact.

### Why
V1 caveats are objects in the inline JSON metadata — they work, but they have no scope granularity, no provenance links, no lifecycle beyond active/expired, and they live in the wrong place (inline metadata that gets rewritten).

### What V1 Has
- Caveats stored as list in metadata: `{text, severity, created_at, created_by, expires_at, status}`.
- Auto-expiry on refresh.
- Active count feeds priority (+5 each, max +20).

### V2 Approach
- Caveats are recorded as `JournalRecord` entries (activity types `caveat_added`, `caveat_mitigated`, `caveat_expired`) in the single journal stream `.amd/journal/`.
- Indexed in SQLite for query.
- Fields:
  - `id`, `applies_to` (artifact / section / derivation / signal)
  - `severity` (low / medium / high / critical)
  - `text`, `created_at`, `created_by`, `expires_at`
  - `state` (active / mitigated / expired / superseded)
  - `evidence_refs`, `invalidates_labels`
  - `resolution_activity_id`
- Caveats are queryable, expirable, and provenance-linked.
- Active caveats affect priority scoring and surface in `scan`/`prime` output.

---

## F10. Timeseries Strategy

### Goal
AMD is timeseries-informed, not a TSDB. Incremental rollups replace full-history rescans.

### Why
V1 rescans the full JSONL sidecar on every refresh via `summarize_timeseries()`. This does not scale. The scaffold argues for incremental checkpoint-based rollups.

### What V1 Has
- `.amd/data/<artifact_id>.jsonl` sidecar with metric/value/timestamp records.
- `summarize_timeseries()` parses the entire file, counts points, tracks latest values per metric.
- Summary written into inline metadata on every refresh.

### V2 Approach

**Default (git-native)**:
- Signals stay as append-only JSONL in `.amd/signals/`.
- Index maintains incremental rollups with checkpoints (source offset).
- Refresh reads only new records since last checkpoint.

**Heavy-data path** (optional):
- Store only references and rollup checkpoints in journals.
- Adapter interface to external stores (DuckDB, Parquet, data warehouse).

**Standard rollup windows**: 15m, 1h, 6h, 24h, 7d.

**Rollup fields**: `latest_at`, `latest_value`, `count`, `min`, `max`, `mean`, `slope`/trend, `cadence_health`, `source_offset`.

---

## F11. Concurrency And Write Safety

### Goal
Multiple agents can safely write to the same project without data corruption or lost writes.

### Why
V1 rewrites the entire Markdown file on every operation (`save_document` writes the full rendered content). Two agents refreshing or adding events simultaneously will clobber each other. The scaffold borrows Mulch's documented safety model.

### What V1 Has
- No locking. No atomic writes. `save_document()` is a plain `path.write_text()`.
- No merge strategy for any file.

### V2 Approach

**Same-worktree protocol**:
1. Acquire per-target lock file using `O_CREAT|O_EXCL`
2. Retry briefly (configurable timeout)
3. Detect and clear stale locks (e.g., process died)
4. Write to temp file
5. Atomic rename into place
6. Release lock

**Cross-branch protocol**:
- Journal files: `merge=union` in `.gitattributes`
- Artifact Markdown files: normal merge (no special strategy)
- Post-merge: `amd reindex` reconciles

**Command safety classes**:
| Class | Commands |
|-------|----------|
| Read-only | `scan`, `query`, `prime`, `export`, `agenda` |
| Locked write | `event`, `caveat`, `signal`, `derive`, `recompute`, `materialize`, `refresh` |
| Serialized setup | `init`, `config edit` |

---

## F12. Provenance Model

### Goal
Every machine action records who did what, when, to which entity, using which inputs.

### Why
V1 tracks `agents.contributors` and `agents.last_actor` in metadata, and timeline entries have agent/kind fields. But there is no formal provenance model — you cannot trace a derived skill back to which source sections and which activity produced it. The scaffold adopts W3C PROV-DM's entity/activity/agent model.

### What V1 Has
- `add_event()` records agent, kind, summary, details in timeline.
- `derive_skill_artifact()` copies sections and records a single event.
- No formal entity/activity/agent vocabulary. No derivation edges.

### V2 Approach

**Entities**: artifact, section, generated block, signal window, template.

**Activities**: init, refresh, recompute, materialize, derive, caveat.create, caveat.resolve, signal.ingest, policy.evaluate.

**Agents**: user, assistant/model, tool, automation.

**Relations**: `wasDerivedFrom`, `wasAttributedTo`, `wasAssociatedWith`, `used`, `wasGeneratedBy`.

All activities are journal events. Derivation edges are indexed. This lets AMD answer:
- Which agent last changed this derived artifact?
- Which source sections fed this skill?
- What caveat or signal caused priority to jump?
- Was this summary refreshed or only materialized from cache?

---

## F13. Derivation System

### Goal
Declared, reproducible transforms between artifacts with provenance and ownership boundaries.

### Why
V1's `derive_skill_artifact()` is a copy operation: it extracts specific sections from a mental model and pastes them into a skill template. No transform spec, no provenance edges, no way to re-derive without clobbering user edits. The scaffold calls this out as too weak.

### V2 Approach
- Derivation rules declared in per-artifact config/ or artifact frontmatter.
- Inputs are labeled source sections.
- Transform spec describes what to extract, how to restructure.
- Output sections are marked as `generated` (machine-owned) vs `user` (human-owned).
- Re-derivation updates only generated blocks unless `--force`.
- Every derivation emits a provenance record to the journal.

---

## F14. Projection And Materialization

### Goal
Inline status blocks, timeline summaries, caveat summaries, and signal rollups are generated projections, not the source of truth.

### Why
V1 treats the inline timeline as the primary audit surface and writes computed metadata into the file body. This conflates human-readable rendering with machine state. The scaffold's central architectural shift is: journals and index are truth; inline blocks are optional rendered views.

### What V1 Has
- Timeline section with `<!-- amd:timeline:start/end -->` markers, written on every event.
- Metadata block rewritten on every refresh.
- No concept of "generated block" vs "user-owned block."

### V2 Approach
- `amd materialize <path>` writes projections into Markdown:
  - Status badge block
  - Timeline summary (from journal)
  - Active caveats summary
  - Signal rollup summary
  - Derivation provenance block
- Generated blocks are clearly delimited (e.g., `<!-- amd:generated:start timeline-summary -->` / `<!-- amd:generated:end -->`).
- `amd refresh` does NOT rewrite the Markdown body by default. It only updates the index.
- User-owned prose is never touched by routine operations.

---

## F15. Ownership Boundaries

### Goal
AMD distinguishes machine-owned content from human-owned content and respects the boundary.

### Why
V1 rewrites the entire file on every operation. There is no concept of which sections an agent may or may not touch. The scaffold argues this is essential for trust.

### What V1 Has
- `save_document()` writes the entire file. No ownership tracking.

### V2 Approach
- Ownership categories: `user`, `agent`, `generated`, `mixed`.
- AMD auto-updates only: generated projections, generated blocks, index/journal state.
- Agent-suggested edits to user-owned sections must be explicit (not silent rewrites).
- Per-artifact config/ can declare section ownership defaults.

---

## F16. Command Surface

### Goal
Clear, well-separated commands with explicit read/write/setup semantics.

### Why
V1 has 9 commands that mostly do the right thing but blur the line between indexing and file writing. The scaffold proposes a cleaner split.

### What V1 Has
| V1 Command | What It Does |
|------------|-------------|
| `init` | Create artifact with template |
| `event` | Append to inline timeline + rewrite file |
| `caveat` | Add to inline metadata + rewrite file |
| `signal` | Append to JSONL sidecar + rewrite file metadata |
| `refresh` | Recompute all metadata + rewrite file |
| `refresh-all` | Refresh every artifact in tree |
| `scan` | Print metadata summary (read-only) |
| `derive-skill` | Copy sections into new artifact |
| `set-priority` | Update manual priority + rewrite file |
| `watch` | Poll + refresh-all at interval |

### V2 Commands

| Command | Semantics | Safety Class |
|---------|-----------|-------------|
| `init` | Create artifact from template, seed config/ | Setup |
| `refresh` | Parse, fingerprint, update index. Does NOT rewrite Markdown. | Locked write |
| `recompute` | Expensive derivation or signal-rollup work | Locked write |
| `materialize` | Write projections into Markdown | Locked write |
| `derive` | Declared transform between artifacts with provenance | Locked write |
| `event` | Append structured event to journal | Locked write |
| `caveat` | Append caveat record to journal | Locked write |
| `signal` | Append signal datapoint to sidecar | Locked write |
| `scan` | Query index, print ranked artifact summaries | Read-only |
| `query` | Structured query over index | Read-only |
| `agenda` | Priority-ranked work queue | Read-only |
| `prime` | Emit agent-facing context pack | Read-only |
| `export` | Write machine-readable JSON manifests | Read-only |
| `doctor` | Validate journals, required sections, labels, projections | Read-only |
| `reindex` | Rebuild SQLite from source + journals | Setup |

### Key Behavioral Changes From V1
- `refresh` no longer rewrites the Markdown body.
- `event` and `caveat` write to journals, not inline.
- `signal` still appends to JSONL but no longer rewrites file metadata.
- `materialize` is the only command that writes back into Markdown, and only to generated blocks.
- `scan` reads from the index, not by reparsing files.

---

## F17. Prime / Context Delivery

### Goal
`amd prime` emits a context pack optimized for agent consumption: highest-priority artifacts, relevant sections, active caveats, freshness notes, recent changes.

### Why
V1's `scan` prints human-readable metadata summaries. There is no agent-facing delivery format. The scaffold borrows Mulch's `prime` concept: storage is not delivery.

### What V1 Has
- `scan_artifact()` returns a dict with metadata fields, printed as formatted text.

### V2 Approach
- `amd prime` reads from the index and emits a structured context pack.
- Contents: highest-priority artifacts (configurable limit), only relevant sections, active caveats first, freshness annotations, recent derivation changes, recent signals.
- Output format: JSON by default, with optional Markdown rendering for human review.
- This is how an agent skill (Claude/Codex) consumes AMD state without reading raw files.

---

## F18. Machine-Readable Export

### Goal
AMD exposes a site manifest and per-artifact JSON for external tooling.

### Why
V1 has no export. External tools must parse Markdown files. The scaffold borrows MyST's `myst.xref.json` pattern.

### What V1 Has
- Nothing.

### V2 Approach
- `amd export` writes to `.amd/export/`.
- `amd.xref.json`: artifact ID, kind, path, title, labels, priority, is_stale.
- `artifacts/<artifact_id>.json`: frontmatter, source path, section list, fingerprints, caveats, rollups, derivation edges, provenance summary.

---

## F19. Hooks

### Goal
Pre/post hooks for refresh, derive, and build operations.

### Why
AMD should be automation-friendly without becoming an automation platform. The scaffold borrows Quarto's hook model with environment variables.

### What V1 Has
- `watch` command polls and refreshes. No hooks.

### V2 Approach
- Config-driven hooks in `.amd/config.yml`.
- Hook points: `pre-refresh`, `post-refresh`, `pre-derive`, `post-derive`, `pre-build`, `post-build`.
- Environment variables exported to hooks: `AMD_PROJECT_ROOT`, `AMD_ACTIVITY_ID`, `AMD_CHANGED_ARTIFACTS_FILE`, `AMD_CHANGED_LABELS_FILE`, `AMD_OUTPUTS_FILE`.

---

## Directory Layout

`.amd/` is metadata only: identity, relations, temporal data, context signals. No document content lives here.

```
project-root/
  .amd/                                   # Metadata only — zero document content
    config/
      report.payments.incident.yml      # Per-artifact operational config
      mental_model.payments.yml
    journal/
      report.payments.incident.jsonl    # Per-artifact JournalRecords
      mental_model.payments.jsonl
      _project.jsonl                    # Project-level records (refresh_run, etc.)
    signals/
      report.payments.incident.jsonl    # Per-artifact SignalPoint timeseries
      mental_model.payments.jsonl
    cache/
      index.sqlite                      # Rebuildable local index (gitignored)
    export/
      amd.xref.json                     # Site manifest
      artifacts/
        <artifact_id>.json              # Per-artifact detail
  artifacts/
    report.payments.incident.md         # Normal Markdown with AMD frontmatter
    mental_model.payments.md
```

---

## V1 -> V2 Migration Path

| V1 Concept | V2 Replacement |
|------------|---------------|
| `<!-- amd:meta {...} -->` | YAML frontmatter under `amd:` key |
| Inline timeline section | Journal events + materialized projection |
| Inline caveats in metadata | Journal caveats + materialized summary |
| `.amd/data/*.jsonl` signals | `.amd/signals/*.jsonl` (same shape, new location) |
| Raw SHA256 section hashes | AST-aware structural fingerprints |
| `stale_after_hours` per section | Freshness classes + policy inheritance |
| Hardcoded template functions | Per-artifact config in `.amd/config/` with required sections, policy, derive contracts |
| `scan` by reparsing files | `scan` from SQLite index |
| `derive-skill` copy operation | `derive` with declared transforms + provenance |
| `save_document()` full rewrite | Atomic writes with lock files |
| No project config | Per-artifact `.amd/config/<artifact_id>.yml` + hardcoded defaults |

---

## Rollout Phases

### Phase 0: Parser And File Model
- Parse Markdown to AST with label resolution
- Stable section IDs
- Structural fingerprint prototype
- Exit: sample artifacts parse reliably with stable labels

### Phase 1: Externalize Machine State
- Journals (events, caveats, derivations)
- Rebuildable SQLite index
- Frontmatter migration (inline JSON -> YAML)
- Export manifest
- Exit: `refresh` no longer rewrites body text

### Phase 2: Safe Writes And Projections
- Lock files + atomic writes
- `merge=union` for journals
- Materialized projection model
- Ownership boundaries
- Exit: concurrent write stress test passes

### Phase 3: Config And Derivation
- Per-artifact config with required/optional sections
- Template binding
- Derivation rules with provenance
- Generated block ownership
- Exit: mental model -> skill derivation is provenance-backed and re-runnable

### Phase 4: Freshness, Priority, Caveats, Signals
- Freshness classes and cadence awareness
- Priority scoring with configurable coefficients
- Caveat lifecycle and rules
- Signal rollups with incremental checkpoints
- Exit: `scan` and `prime` surface meaningful ranked outputs

### Phase 5: Hooks, Exports, Integrations
- Pre/post hooks
- JSON exports
- Agent skill integration (Claude/Codex consumes `prime` output)
- Exit: AMD integrates into repo workflows without bespoke UI

---

## Risks And Mitigations

| Risk | Mitigation |
|------|-----------|
| MyST syntax beyond CommonMark | Support both AMD label comments and MyST labels; keep files valid Markdown |
| Agents rewriting user prose | Auto-writes limited to generated blocks and projections only |
| SQLite as shared truth | SQLite is local cache; journals are shared truth |
| CRDT complexity too early | Lock-based writes first; CRDTs are a later-stage option |
| Overfitting to one editor | Borrow patterns, not dependencies |
| Migration friction from v1 | Provide `amd migrate` command; keep `.amd.md` accepted alongside `.md` |
