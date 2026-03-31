# AMD v2 Plan: Lightweight Context Graph In `.amd/`

## Goal

Let users keep Markdown files however they want:

- arbitrary paths
- arbitrary filenames
- messy local organization
- renamed or split documents over time

AMD should supply the missing structure in `.amd/`: a lightweight, rebuildable context graph that explains what each document is, how it evolved, and how it relates to other documents.

## Foundational Constraints

### `.amd/` is metadata plus small context

`.amd/` is not a full content store, but it is also not strictly metadata-only. It may keep small derived context that helps agents search, rank, and route updates. It stores:

- identity records (artifact IDs, section IDs, locators)
- relation edges (how artifacts/sections connect)
- temporal data (activity journals, event logs, signal rollups)
- context metadata (freshness state, fingerprints, policy resolution, caveats)
- lightweight derived context (headings, labels, short snippets, selected section text for retrieval)
- rebuildable index (SQLite cache) and exported manifests

It does **not** store:

- full copies of Markdown files
- canonical user-authored documents
- generated docs that compete with source files
- assets or template content as source of truth

The user's actual documents still live wherever the user puts them. `.amd/` knows *about* them and may keep a little derived context from them, but it is not the primary content home.

### AMD is an agent-native CLI

AMD is a CLI tool designed primarily for machine consumption. The primary users are AI agents — Claude Code, Codex, and similar — that invoke AMD commands at machine speed and volume to:

- create and evolve artifacts dynamically
- record events, caveats, and signals as they work
- query the graph to understand document relationships
- derive new artifacts from existing ones
- break and rebuild structure as understanding evolves

Humans can use the CLI directly, but the interface, output formats, and operational semantics are designed for agents operating autonomously within a codebase. The graph in `.amd/` is live working state that changes every session, not a static archive.

## Core And Agent Layers

### Core layer (what AMD itself owns)

AMD core owns the machine surfaces:

- parse Markdown and resolve artifact/section identity
- maintain journals and the SQLite index
- expose structured JSON read surfaces
- export snapshot manifests for wrappers and external tooling

AMD core does **not**:

- decide semantic relevance
- decide which docs should be edited
- rewrite user prose as part of normal graph maintenance

### Agent layer (what Claude/Codex wrappers own)

Agents consume AMD, not the other way around.

The agent layer owns:

- deciding which AMD commands to run
- interpreting returned candidates
- opening source files when full prose is needed
- making the actual content edits

The agent layer should prefer these consumption surfaces:

1. **Bootstrap surface**
   - read `.amd/export/amd.xref.json`
   - use it to quickly learn what artifacts exist, what kinds they are, how they relate, what sections/labels they expose, and which source path to open

2. **Live query surface**
   - call `amd prime --format json`
   - call `amd affected --format json`
   - call `amd query --format json`
   - call `amd agenda --format json`
   - these read from SQLite through AMD core; agents should not query SQLite directly during normal operation

3. **Source-of-truth surface**
   - open the Markdown file at the returned source path when the full section text or full document context is needed

This gives a clean split:

- `amd.xref.json` is the cheap map
- CLI JSON commands are the live interface
- source Markdown remains the canonical prose

## Core Conclusion

Do **not** model this as one big tree.

The right model is:

- a **forest of section trees** parsed from Markdown files
- plus **cross-tree relation edges** between artifacts, sections, and directives/assertions

That gives you both:

- local structure within a document
- global relations across documents

This is lighter than a graph database and more correct than a filesystem tree.

## Why A Tree Is Not Enough

Some relationships are hierarchical:

- artifact contains sections
- section contains child sections

But the important AMD relationships are not hierarchical:

- `plann.md` is a revision of `plan.md`
- a runbook is derived from an incident report
- an incident report feeds a postmortem
- two notes are alternate views of the same thing
- one note supersedes another

Those are graph edges, not parent/child tree edges.

## Recommended Mental Model

`.amd/` should maintain three layers:

1. **Identity layer**
   - stable artifact IDs independent of path
   - stable section IDs independent of heading text where possible

2. **Relation layer**
   - explicit and inferred edges between artifacts, sections, and metadata-native directives/assertions

3. **Projection layer**
   - a rebuildable SQLite index for fast queries plus exported JSON manifests for wrappers, agents, and external tooling

## Bottom-Up Types

### 1. Logical artifact

Represents the enduring thing, not the current filename.

Examples:

- `artifact:plan-auth-refresh`
- `artifact:payments-incident-2026-03-11`

Fields:

- `artifact_id`
- `kind`
- `title`
- `current_path`
- `state` (`active`, `archived`, `superseded`)
- `created_at`
- `updated_at`

Rule:

- path is a locator, not identity

### 2. Artifact locator

Represents where AMD last observed the artifact.

Fields:

- `artifact_id`
- `path`
- `observed_at`
- `content_fingerprint`
- optional local-only hints like inode/device

This lets AMD track moves and renames without making path the primary key.

### 3. Section node

Represents a stable, targetable unit inside an artifact.

Fields:

- `section_id`
- `artifact_id`
- `parent_section_id`
- `label`
- `heading`
- `ordinal`
- `structural_fingerprint`

### 4. Directive/assertion node

Represents a load-bearing project clarification stored in `.amd/` as machine-owned metadata/context.

Examples:

- `directive:amd-metadata-context`
- `directive:agent-cli-native`

Fields:

- `directive_id`
- `directive_type` (`clarification`, `constraint`, `decision`, `invariant`)
- `statement`
- `scope`
- `status` (`active`, `superseded`, `revoked`)
- `source_activity_id`
- `created_at`
- `updated_at`
- `superseded_by` nullable

Rule:

- directives/assertions are graph entities, not Markdown artifacts

Optional promotion path:

- if a directive needs durable human rationale, derive or create a `decision_record` artifact from it

### 5. Relation edge

Represents a connection between graph entities.

Fields:

- `edge_id`
- `src_entity_type` (`artifact`, `section`, `directive`)
- `src_entity_id`
- `dst_entity_type` (`artifact`, `section`, `directive`)
- `dst_entity_id`
- `edge_type`
- `origin`
- `confidence`
- `activity_id` nullable
- `created_at`
- `ended_at` nullable

Suggested `edge_type` set:

- `contains`
- `references`
- `applies_to`
- `reflected_in`
- `revision_of`
- `alternate_of`
- `derived_from`
- `supersedes`
- `contradicted_by`
- `split_from`
- `merged_from`
- `relates_to`

Suggested `origin` set:

- `declared`
- `derived`
- `observed`
- `heuristic`

#### Edge ending rules

The `ended_at` field on edges marks when a relationship ceased to be active. Ended edges are never deleted from the index — they remain for history and provenance. Active queries filter them out by default; `amd history` shows them.

Rules for when `ended_at` is set:

- **Artifact archived**: all edges where the archived artifact is `src_entity_id` or `dst_entity_id` get `ended_at = now`. This applies to all edge types — `contains`, `references`, `derived_from`, `reflected_in`, etc.
- **Section removed**: when a labeled section disappears and cannot be confidently matched on refresh, edges targeting that section get `ended_at = now`. The section record itself is retained with a terminal state.
- **Derivation re-run**: when `amd derive` re-derives a target from a source, old `derived_from` edges between that source-target pair get `ended_at = now`, and new edges are created. This ensures provenance tracks each derivation pass separately.
- **Directive superseded or revoked**: when a directive transitions to `superseded` or `revoked`, its `reflected_in` edges get `ended_at = now`.
- **Explicit unlinking**: `amd link --remove` (if supported) sets `ended_at` on the specified edge.

Edges are never hard-deleted because:

- provenance chains must remain traceable
- `amd history` needs to show what relationships existed and when they ended
- `amd reindex` must be able to reconstruct edge history from journals

### 6. Journal record

Represents the operation that created or changed graph state. Fully defined in temporal-context-handling.md § `JournalRecord`.

Core envelope (mandatory):

- `activity_id`
- `activity_type` (see temporal plan for the full activity type reference)
- `artifact_id`
- `occurred_at`
- `recorded_at`

Agent/user context (agent-authored, core stores but does not validate):

- `target_entity_type` (`artifact`, `section`, `directive`)
- `target_entity_id`
- `section_ids` nullable
- `actor`
- `summary`
- `detail_json`

This keeps provenance lightweight without forcing full graph-DB semantics.

## Identity Rules

This is the key design point.

AMD cannot safely infer semantics like “`plann.md` is the successor to `plan.md`” from filenames alone.

Use these rules:

### Case A: same logical doc, just moved or renamed

Keep the same `artifact_id`.

What changes:

- locator path
- maybe title
- maybe content fingerprint

What AMD records:

- updated locator
- optional `observed_move` activity

No `revision_of` edge is needed because it is still the same logical artifact.

### Case B: new doc that evolves or supersedes an old doc

Create a new `artifact_id` and add a relation:

- `revision_of`
- or `supersedes`

This is the right model for “v2 plan” that is intentionally a separate artifact.

### Case C: same thing, different representation

Use:

- `alternate_of`

This matches cases like concise note vs long note, or desktop/mobile style alternates. W3C PROV explicitly models both `Revision` and `AlternateOf` relationships.[1]

## Where To Store Graph State

### Source of truth

Use:

- append-only journals for graph-changing actions
- rebuildable SQLite index for current graph state

Recommended layout:

```text
.amd/
  config/
    <artifact_id>.yml           # Per-artifact operational config (freshness, signals, derive)
  journal/
    <artifact_id>.jsonl         # Per-artifact JournalRecords
    _project.jsonl              # Project-level records (refresh_run, etc.)
  signals/
    <artifact_id>.jsonl         # Per-artifact SignalPoint timeseries
  cache/
    index.sqlite
  export/
    amd.xref.json
    artifacts/
      <artifact_id>.json
```

### Why this layout

- config, journals, and signals are all flat-by-type, per-artifact — O(1) single-artifact lookup and efficient cross-artifact grepping
- config/ holds the operational parameters AMD reads on refresh to evaluate each artifact (freshness policy, signal thresholds, derive contracts)
- journals are safe for append-heavy multi-agent writes
- SQLite is fast for read-heavy traversal and ranking
- export files give agents and wrappers a cheap bootstrap map without reparsing Markdown
- source Markdown stays out of the query path until an agent explicitly needs full prose

## Why SQLite Is Enough

SQLite already supports recursive graph and tree traversal through recursive CTEs.[2]

Inference:

- AMD does not need Neo4j or another graph database for this use case
- an adjacency-list schema in SQLite is enough
- recursive CTEs cover ancestor/descendant and neighborhood walks

SQLite also fits the rest of v2 well:

- WAL mode supports concurrent readers with one writer.[3]
- foreign keys help keep edges and node references consistent.[4]
- FTS5 provides the required full-text retrieval layer over titles, headings, labels, and section text for propagation and context discovery.[5]

## Recommended SQLite Shape

Keep it minimal.

### `artifacts`

- `artifact_id TEXT PRIMARY KEY`
- `kind TEXT`
- `title TEXT`
- `current_path TEXT`
- `state TEXT`
- `created_at TEXT`
- `updated_at TEXT`

### `artifact_locators`

- `artifact_id TEXT`
- `path TEXT`
- `observed_at TEXT`
- `content_fingerprint TEXT`
- `is_current INTEGER`

### `sections`

- `section_id TEXT PRIMARY KEY`
- `artifact_id TEXT`
- `parent_section_id TEXT`
- `label TEXT`
- `heading TEXT`
- `ordinal INTEGER`
- `structural_fingerprint TEXT`
- `content_fingerprint TEXT`
- `snippet TEXT` — eagerly stored first paragraph or first ~200 characters of normalized plain text, computed on refresh. Used by `amd affected` to return cheap candidate previews without reopening source files.
- `plain_text TEXT` — normalized plain-text section content, fed into the `artifact_search` FTS5 table alongside headings and labels. Not the full Markdown source — whitespace-collapsed, markers stripped, generated blocks excluded.

### `edges`

- `edge_id TEXT PRIMARY KEY`
- `src_entity_type TEXT`
- `src_entity_id TEXT`
- `dst_entity_type TEXT`
- `dst_entity_id TEXT`
- `edge_type TEXT`
- `origin TEXT`
- `confidence REAL`
- `activity_id TEXT`
- `created_at TEXT`
- `ended_at TEXT`

### `directives`

- `directive_id TEXT PRIMARY KEY`
- `directive_type TEXT`
- `statement TEXT`
- `scope TEXT`
- `status TEXT`
- `source_activity_id TEXT`
- `created_at TEXT`
- `updated_at TEXT`
- `superseded_by TEXT`

### `journal_records`

- `activity_id TEXT PRIMARY KEY`
- `activity_type TEXT`
- `artifact_id TEXT`
- `occurred_at TEXT`
- `recorded_at TEXT`
- `actor TEXT`
- `summary TEXT`
- `detail_json TEXT`

### `artifact_temporal`

Per-artifact temporal facts. Written on refresh from journals, signals, and config/ files. Read at query time by `amd agenda`, `amd prime`, and `amd query --stale`.

- `artifact_id TEXT PRIMARY KEY`
- `freshness_class TEXT` — resolved via 3-layer precedence (hardcoded -> config/ -> frontmatter)
- `stale_after_seconds INTEGER` — resolved via 3-layer precedence (hardcoded -> config/ -> frontmatter)
- `refresh_mode TEXT` — resolved via 3-layer precedence (hardcoded -> config/ -> frontmatter) (`auto`, `manual`, `frozen`, `live`). Gates which refresh steps apply.
- `freshness_anchor_at TEXT` — `max(last_changed_at, last_reviewed_at)`
- `stale_state TEXT` — snapshot from last refresh: `fresh`, `aging`, or `stale`. Stored for transition detection.
- `last_changed_at TEXT` — from `content_changed` journal events
- `last_observed_at TEXT` — from most recent refresh that parsed this artifact
- `last_reviewed_at TEXT` — from `review_recorded` journal events
- `last_signal_at TEXT` — from most recent signal point `observed_at`
- `first_seen_at TEXT` — from `artifact_created` journal event
- `active_caveat_count INTEGER` — maintained on caveat add/mitigate/expire events
- `signal_breach_count INTEGER` — maintained on breach enter/clear events
- `signal_silence_count INTEGER` — maintained on silence enter/clear events
- `derivation_drift_count INTEGER` — maintained on drift enter/clear events

### `section_temporal`

Per-section temporal facts. Same pattern as artifact_temporal but scoped to sections.

- `section_id TEXT PRIMARY KEY`
- `artifact_id TEXT`
- `last_changed_at TEXT`
- `last_observed_at TEXT`
- `last_reviewed_at TEXT`
- `freshness_anchor_at TEXT` — `max(last_changed_at, last_reviewed_at)`
- `active_caveat_count INTEGER`

### `signal_rollups`

Derived windowed summary for one metric. Computed incrementally from raw `SignalPoint` records in `.amd/signals/` on refresh. Rebuildable from JSONL if the index is deleted.

- `artifact_id TEXT`
- `metric TEXT`
- `window TEXT` — one of the configured windows (default: `15m`, `1h`, `6h`, `24h`, `7d`)
- `window_end_at TEXT`
- `count INTEGER`
- `min REAL`
- `max REAL`
- `mean REAL`
- `latest_observed_at TEXT`
- `latest_value REAL`
- `slope REAL` — nullable, requires count >= 2
- `cadence_health REAL` — nullable, requires expected_cadence configured
- `source_offset INTEGER` — byte offset into JSONL for incremental reads
- `PRIMARY KEY (artifact_id, metric, window)`

### `artifact_search`

FTS5 virtual table for:

- titles
- labels
- headings
- selected section text

This is required. Topic-based discovery depends on it.

## Write-Time vs Query-Time Computation

This is a critical design detail. SQLite has no sense of time on its own. The right model is: store temporal facts on refresh, compute time-dependent values at query time using `unixepoch('now')`.

### Stored facts (written on refresh)

These are stable between refreshes. They change only when something actually happens.

| Column | Written when | Source |
|---|---|---|
| `freshness_anchor_at` | content_changed or review_recorded | journals |
| `last_changed_at` | content_changed | journals |
| `last_reviewed_at` | review_recorded | journals |
| `last_signal_at` | signal_ingested | signals/ |
| `last_observed_at` | every refresh that parses this file | refresh |
| `stale_after_seconds` | refresh reads config/ | config/ |
| `freshness_class` | refresh reads config/ | config/ |
| `active_caveat_count` | caveat_added / caveat_mitigated / caveat_expired | journals |
| `signal_breach_count` | signal_breach_entered / signal_breach_cleared | journals |
| `signal_silence_count` | signal_silence_entered / signal_silence_cleared | journals |
| `derivation_drift_count` | derivation_drift_entered / derivation_drift_cleared | journals |
| Signal rollup values | refresh processes new signal points | signals/ |

### Computed at query time (using `unixepoch('now')`)

These are always current because they are evaluated on every read.

| Value | Formula |
|---|---|
| `staleness_ratio` | `CASE WHEN stale_after_seconds IS NULL THEN NULL ELSE (unixepoch('now') - unixepoch(freshness_anchor_at)) * 1.0 / stale_after_seconds END` |
| `stale_state` | `CASE WHEN staleness_ratio IS NULL THEN 'exempt' WHEN staleness_ratio < 0.5 THEN 'fresh' WHEN staleness_ratio < 1.0 THEN 'aging' ELSE 'stale' END` |
| `signal_silent` (per metric) | `unixepoch('now') - unixepoch(latest_observed_at) > expected_cadence_seconds * 6` |
| `priority_score` | Composite formula over staleness_ratio + count penalties (see below) |

**Null staleness semantics:** When `stale_after_seconds` is `NULL` (the config plan allows `stale_after: null` to mean "this artifact has no staleness policy"), `staleness_ratio` is `NULL` and `stale_state` is `'exempt'`. These artifacts never appear in `amd query --stale` results. They still appear in `amd agenda` if they have active caveats, signal breaches, signal silences, or derivation drift — their freshness penalty is simply zero.

### Priority score formula (evaluated in SQL)

```sql
CAST(
  10.0 * MIN(COALESCE(staleness_ratio, 0.0), 5.0)  -- freshness penalty (capped; 0 when exempt)
  + 5.0 * active_caveat_count                        -- caveat penalty
  + 10.0 * signal_breach_count                       -- signal warn penalty
  + 20.0 * (CASE WHEN signal_breach_count > 2
             THEN signal_breach_count - 2 ELSE 0 END)  -- signal critical escalation
  + 10.0 * derivation_drift_count                    -- derivation drift penalty
AS REAL) AS priority_score
```

The coefficients (10, 5, 10, 20, 10) are hardcoded in AMD core. They are not user-configurable in v2.

## Key Query Patterns

### `amd agenda` — ranked list of artifacts needing attention

```sql
WITH temporal AS (
  SELECT
    t.artifact_id,
    a.title,
    a.kind,
    a.current_path,
    CASE WHEN t.stale_after_seconds IS NULL THEN NULL
         ELSE (unixepoch('now') - unixepoch(t.freshness_anchor_at)) * 1.0
              / t.stale_after_seconds
    END AS staleness_ratio,
    CASE
      WHEN t.stale_after_seconds IS NULL THEN 'exempt'
      WHEN (unixepoch('now') - unixepoch(t.freshness_anchor_at)) * 1.0
           / t.stale_after_seconds < 0.5 THEN 'fresh'
      WHEN (unixepoch('now') - unixepoch(t.freshness_anchor_at)) * 1.0
           / t.stale_after_seconds < 1.0 THEN 'aging'
      ELSE 'stale'
    END AS stale_state,
    t.active_caveat_count,
    t.signal_breach_count,
    t.signal_silence_count,
    t.derivation_drift_count
  FROM artifact_temporal t
  JOIN artifacts a USING (artifact_id)
  WHERE a.state = 'active'
)
SELECT *,
  10.0 * MIN(COALESCE(staleness_ratio, 0.0), 5.0)
  + 5.0 * active_caveat_count
  + 10.0 * signal_breach_count
  + 10.0 * derivation_drift_count AS priority_score
FROM temporal
WHERE COALESCE(staleness_ratio, 0.0) > 0.5
   OR active_caveat_count > 0
   OR signal_breach_count > 0
   OR signal_silence_count > 0
   OR derivation_drift_count > 0
ORDER BY priority_score DESC;
```

### `amd prime` — full context for one artifact

```sql
SELECT
  a.artifact_id, a.kind, a.title, a.current_path, a.state,
  t.freshness_class, t.stale_after_seconds,
  t.freshness_anchor_at, t.last_changed_at, t.last_reviewed_at,
  t.last_signal_at, t.first_seen_at,
  CASE WHEN t.stale_after_seconds IS NULL THEN NULL
       ELSE (unixepoch('now') - unixepoch(t.freshness_anchor_at)) * 1.0
            / t.stale_after_seconds
  END AS staleness_ratio,
  CASE
    WHEN t.stale_after_seconds IS NULL THEN 'exempt'
    WHEN (unixepoch('now') - unixepoch(t.freshness_anchor_at)) * 1.0
         / t.stale_after_seconds < 0.5 THEN 'fresh'
    WHEN (unixepoch('now') - unixepoch(t.freshness_anchor_at)) * 1.0
         / t.stale_after_seconds < 1.0 THEN 'aging'
    ELSE 'stale'
  END AS stale_state,
  t.active_caveat_count,
  t.signal_breach_count,
  t.signal_silence_count,
  t.derivation_drift_count
FROM artifacts a
JOIN artifact_temporal t USING (artifact_id)
WHERE a.artifact_id = ?;

-- Plus: sections, edges, recent journal entries, signal rollups
-- (separate queries joined in application code)
```

### `amd query --stale` — artifacts past staleness threshold

```sql
SELECT a.artifact_id, a.title, a.kind, a.current_path,
  (unixepoch('now') - unixepoch(t.freshness_anchor_at)) * 1.0
    / t.stale_after_seconds AS staleness_ratio
FROM artifacts a
JOIN artifact_temporal t USING (artifact_id)
WHERE a.state = 'active'
  AND t.stale_after_seconds IS NOT NULL
  AND (unixepoch('now') - unixepoch(t.freshness_anchor_at)) * 1.0
      / t.stale_after_seconds > 1.0
ORDER BY staleness_ratio DESC;
```

### `amd affected` — FTS5 search + relation edge follow

```sql
-- Step 1: FTS5 search for matching sections
SELECT s.section_id, s.artifact_id, s.label, s.heading,
       snippet(artifact_search, 3, '<mark>', '</mark>', '...', 32) AS snippet
FROM artifact_search
JOIN sections s ON artifact_search.rowid = s.rowid
WHERE artifact_search MATCH ?
  AND (SELECT state FROM artifacts WHERE artifact_id = s.artifact_id) = 'active';

-- Step 2: follow relation edges from matched artifacts (in application code)
SELECT e.dst_entity_type, e.dst_entity_id, e.edge_type
FROM edges e
WHERE e.src_entity_id IN (/* matched artifact_ids */)
  AND e.ended_at IS NULL;
```

## How Config Files Feed SQLite On Refresh

During `amd refresh`, AMD resolves temporal policy for each known artifact using the 3-layer resolution chain (hardcoded -> config/ -> frontmatter) and uses it to populate SQLite:

1. **Resolve temporal policy** — for each artifact, resolve `freshness_class`, `stale_after`, and `refresh_mode` through the 3-layer precedence: AMD hardcoded defaults -> `.amd/config/<artifact_id>.yml` -> frontmatter `amd.policy` overrides. Convert duration strings to seconds.
2. **Write to `artifact_temporal`** — upsert `freshness_class`, `stale_after_seconds`, and `refresh_mode`
3. **Gate on refresh_mode** — subsequent temporal steps (4–6) are skipped for `frozen` and unforced `manual` artifacts. `live` artifacts skip content-based staleness but run signal steps.
4. **Read signal thresholds** — parse `signals.<metric>.thresholds` from resolved config
5. **Evaluate against rollups** — compare `signal_rollups.latest_value` against thresholds, detect breaches/clears, update `signal_breach_count`
6. **Read derive contracts** — parse `derive.targets` from resolved config
7. **Check source fingerprints** — compare current source artifact fingerprint against fingerprint at last derivation, detect drift, update `derivation_drift_count`

This means temporal policy is resolved once per refresh per artifact, and the resolved values are cached in SQLite for query-time use. Changing a config/ file or frontmatter policy takes effect on the next refresh.

## Update Strategy

### On `amd refresh`

1. Scan configured Markdown roots.
2. Compare known artifact paths against found files. For each known active artifact whose file no longer exists at its `current_path`:
   - transition artifact state to `archived`
   - set `ended_at` on all active edges involving this artifact
   - run archival cascade: emit `derivation_drift_entered` on downstream targets, auto-create caveat on downstream artifacts (see temporal-context-handling plan for cascade rules)
3. Detect re-appeared files: if a scanned file contains an `amd.id` matching an archived artifact, transition that artifact back to `active` and reconnect edges where possible.
4. Parse frontmatter and Markdown AST for all current files.
5. Build section tree for each file.
6. Resolve stable artifact identity:
   - explicit `amd.id` wins
   - otherwise treat as unmanaged/candidate
7. Resolve stable section IDs (per the parsing plan's identity model):
   - explicit AMD label comment wins
   - then MyST target label
   - then heading attribute ID
   - then persisted unlabeled-section match from prior refresh (requires same artifact, exact content fingerprint, same heading level, same nearest labeled ancestor)
   - otherwise assign a new opaque persisted ID (e.g. `section:01jabc...`)
   - if AMD cannot identify exactly one match for an unlabeled section, create a new section ID and let `doctor` flag the ambiguous rename/move
8. Compute content and subtree fingerprints (per the parsing plan's Merkle-like model).
9. Resolve temporal policy for each known artifact via the 3-layer chain (hardcoded -> config/ -> frontmatter):
   - write resolved `freshness_class`, `stale_after_seconds`, and `refresh_mode` into `artifact_temporal`
   - read signal thresholds for breach/silence evaluation
   - read derive contracts for drift detection
10. Gate per-artifact temporal steps on `refresh_mode` (see temporal-context-handling plan for mode semantics).
11. Update locator table.
12. Recompute `contains` edges from the AST.
13. Rebuild explicit relation edges from journal records.
14. Rebuild directive/assertion nodes from journals.
15. Add heuristic candidate edges only as suggestions, not as authoritative facts.

### On `amd link`

Append a `relation_created` JournalRecord, then update the index. The record uses the canonical `JournalRecord` envelope from the temporal plan: core envelope fields (`activity_id`, `activity_type`, `artifact_id`, `occurred_at`, `recorded_at`) plus agent context fields (`target_entity_type`, `target_entity_id`, `actor`, `summary`, `detail_json`).

**Journal partition rule:** The record is appended based on the source entity type:

- `src_entity_type: artifact` or `section` — append to `journal/<src_artifact_id>.jsonl` (the envelope `artifact_id` is the source artifact)
- `src_entity_type: directive` — the directive has no artifact file, so append to `journal/_project.jsonl` with `artifact_id: null`. Additionally, append a copy to `journal/<dst_artifact_id>.jsonl` for each destination artifact so that per-artifact history includes the edge. (The destination copy uses the destination artifact as its envelope `artifact_id`.)

Example:

```json
{
  "activity_id": "act_01",
  "activity_type": "relation_created",
  "artifact_id": "artifact:plann-auth-v2",
  "occurred_at": "2026-03-11T13:00:00Z",
  "recorded_at": "2026-03-11T13:00:01Z",
  "target_entity_type": "artifact",
  "target_entity_id": "artifact:plan-auth-v1",
  "actor": "codex",
  "summary": "Linked plann-auth-v2 as revision of plan-auth-v1",
  "detail_json": {
    "src_entity_type": "artifact",
    "src_entity_id": "artifact:plann-auth-v2",
    "dst_entity_type": "artifact",
    "dst_entity_id": "artifact:plan-auth-v1",
    "edge_type": "revision_of",
    "origin": "declared"
  }
}
```

### On `amd derive`

Append a `derivation_updated` JournalRecord to `journal/<target_artifact_id>.jsonl`, plus one or more `relation_created` records for `derived_from` edges and optional section-to-section provenance edges. All records use the canonical `JournalRecord` envelope. See the temporal plan's `derivation_updated` activity type for the required and optional `detail_json` fields.

### On `amd capture`

Append a JournalRecord to `journal/_project.jsonl` (directives are project-level entities, not scoped to a single artifact), then update the index. The `artifact_id` envelope field is null for directive creation. The directive's own fields (`directive_id`, `directive_type`, `statement`, `scope`, `status`) go into `detail_json`.

Example:

```json
{
  "activity_id": "act_02",
  "activity_type": "directive_created",
  "artifact_id": null,
  "occurred_at": "2026-03-11T13:05:00Z",
  "recorded_at": "2026-03-11T13:05:01Z",
  "target_entity_type": "directive",
  "target_entity_id": "directive:amd-metadata-context",
  "actor": "codex",
  "summary": "Captured clarification: .amd/ stores metadata plus small derived context, not full documents",
  "detail_json": {
    "directive_id": "directive:amd-metadata-context",
    "directive_type": "clarification",
    "statement": ".amd/ stores metadata plus a small amount of derived context, but never full user-authored documents",
    "scope": "project",
    "status": "active"
  }
}
```

When a directive is later linked to specific artifacts via `amd link`, the resulting `relation_created` and `directive_propagated` records land in the respective target artifacts' journal files.

## End-To-End Pipeline: How The Pieces Fit Together

The six v2 plans each describe one subsystem. This section shows how they combine into a single pipeline during `amd refresh` and normal operation.

### The full flow

```text
USER'S MARKDOWN FILES (.md)
        │
        ▼
┌─────────────────────────────────────────────────┐
│  1. PARSE                                       │
│     markdown-it-py → token stream → AST         │
│     Owner: markdown-parsing-and-section-identity │
│     Output: tokens, line map                    │
│     Lifecycle: EPHEMERAL — discarded after step 2│
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  2. BUILD SECTION TREE + FINGERPRINTS           │
│     AST → section nodes with stable IDs         │
│     Content hash + subtree hash per section     │
│     Owner: markdown-parsing-and-section-identity │
│     Output: section IDs, fingerprints           │
│     Lifecycle: IDs and fingerprints PERSIST      │
│                in cache/index.sqlite             │
│                AST is DISCARDED here             │
└────────────────────┬────────────────────────────┘
                     │
        ┌────────────┴────────────────────┐
        │                                 │
        ▼                                 ▼
┌──────────────┐              ┌──────────────────┐
│ 3a. COMPARE  │              │ 3b. UPDATE       │
│ FINGERPRINTS │              │ GRAPH EDGES      │
│              │              │                  │
│ Old vs new   │              │ contains,        │
│ from sqlite  │              │ derives_from,    │
│              │              │ revision_of      │
│ Changed?     │              │ etc.             │
│ Same?        │              │                  │
│              │              │ Owner:           │
│ Owner:       │              │ context-graph-   │
│ temporal-    │              │ architecture     │
│ context      │              │ (this plan)      │
└──────┬───────┘              └──────────────────┘
       │
       │ fingerprint changed?
       │
       ├─── YES ──────────────────────────┐
       │                                  │
       ▼                                  ▼
┌──────────────────┐           ┌─────────────────────┐
│ 4a. JOURNAL      │           │ 4b. TEMPORAL STATE  │
│                  │           │                     │
│ Append event:    │           │ Write facts:        │
│ content_changed, │           │ last_changed_at,    │
│ caveat_expired,  │           │ freshness_anchor_at,│
│ derivation_drift │           │ caveat/breach/drift │
│ _entered, etc.   │           │ counts              │
│                  │           │                     │
│                  │           │ Read config/:       │
│ Owner: context-  │           │ stale_after_seconds,│
│ graph (storage)  │           │ freshness_class     │
│ + temporal-      │           │                     │
│ context (types)  │           │ Query-time:         │
│                  │           │ staleness_ratio,    │
│ Stored in:       │           │ priority_score      │
│ .amd/journal/    │           │ (computed via NOW)  │
│ (APPEND-ONLY)    │           │                     │
└──────────────────┘           │ Owner: temporal-    │
                               │ context-handling    │
                               │                     │
                               │ Stored in:          │
                               │ .amd/cache/         │
                               │ index.sqlite        │
                               │ (REBUILDABLE)       │
                               └──────────┬──────────┘
                                          │
              ┌───────────────────────────┐│
              │                           ││
              ▼                           ▼│
   ┌─────────────────────┐    ┌──────────────────────┐
   │ 5. SIGNALS (async)  │    │ 6. EXPORT            │
   │                     │    │                      │
   │ External metrics    │    │ amd.xref.json        │
   │ ingested into       │──► │ per-artifact JSON    │
   │ sqlite rollups      │    │                      │
   │                     │    │ Owner: source-format- │
   │ Owner: temporal-    │    │ and-agent-readable-  │
   │ context-handling    │    │ surfaces             │
   │                     │    │                      │
   │ Raw stored in:      │    │ Stored in:           │
   │ .amd/signals/       │    │ .amd/export/         │
   │ (APPEND-ONLY)       │    │ (REBUILDABLE)        │
   └─────────────────────┘    └──────────┬───────────┘
                                         │
                                         ▼
                              ┌──────────────────────┐
                              │ 7. CLI COMMANDS      │
                              │                      │
                              │ amd prime            │
                              │ amd agenda           │
                              │ amd history          │
                              │ amd query --stale    │
                              │ amd scan             │
                              │ amd affected         │
                              │                      │
                              │ All read from sqlite │
                              │ Agents consume these │
                              └──────────────────────┘
```

### What is ephemeral versus persisted

| Data | Lifecycle | Where |
|------|-----------|-------|
| Raw AST / token stream | Ephemeral — discarded after section tree is built | Memory only |
| Section IDs | Persisted | `cache/index.sqlite` `sections` table |
| Content fingerprints | Persisted — needed for next refresh comparison | `cache/index.sqlite` `artifact_locators` + `sections` tables |
| Subtree fingerprints | Persisted — for Merkle-like drift rollups | `cache/index.sqlite` `sections` table |
| Per-artifact config | Persisted — source of truth for evaluation parameters | `.amd/config/` YAML files |
| Activity events | Persisted — append-only, never rewritten | `.amd/journal/` JSONL files |
| Signal points | Persisted — append-only, never rewritten | `.amd/signals/` JSONL files |
| Signal rollups | Persisted but rebuildable from raw points | `cache/index.sqlite` `signal_rollups` table |
| Temporal facts (clocks, counts) | Persisted but rebuildable from journals + signals + config + markdown | `cache/index.sqlite` `artifact_temporal` + `section_temporal` tables |
| Temporal evaluations (staleness_ratio, priority) | Ephemeral — computed at query time using `unixepoch('now')` | SQL expressions, not stored |
| Graph edges | Persisted but rebuildable from journals + markdown | `cache/index.sqlite` |
| Export manifests | Persisted but rebuildable from sqlite | `.amd/export/` JSON files |

### Which plan owns which refresh step

| Refresh step | Owner plan |
|-------------|------------|
| 1. Detect missing files and archive absent artifacts | context-graph-architecture + temporal-context-handling |
| 2. Detect re-appeared files and reclaim archived artifacts | context-graph-architecture + temporal-context-handling |
| 3. Parse Markdown into tokens and AST | markdown-parsing-and-section-identity |
| 4. Build section tree and assign stable IDs | markdown-parsing-and-section-identity |
| 5. Compute content and subtree fingerprints | markdown-parsing-and-section-identity |
| 6. Resolve artifact identity from frontmatter | source-format-and-agent-readable-surfaces |
| 7. Resolve temporal policy via 3-layer chain (hardcoded -> config/ -> frontmatter) for each artifact | per-artifact-config + temporal-context-handling |
| 8. Write resolved freshness_class, stale_after_seconds, and refresh_mode into artifact_temporal | per-artifact-config + context-graph-architecture |
| 9. Gate per-artifact temporal steps on refresh_mode | temporal-context-handling |
| 10. Compare fingerprints against previous run | temporal-context-handling |
| 11. Update temporal clocks (`last_changed_at`, `last_observed_at`) | temporal-context-handling |
| 12. Validate sections against required_sections from resolved config | per-artifact-config |
| 13. Update locator table and `contains` edges | context-graph-architecture |
| 14. Rebuild relation and directive edges from journals | context-graph-architecture |
| 15. Process new signal points from checkpoints (skip archived, frozen, unforced manual) | temporal-context-handling |
| 16. Evaluate signal thresholds from resolved config against rollups, update breach/silence counts | temporal-context-handling + per-artifact-config |
| 17. Recompute caveat lifecycle and freshness_anchor_at (skip archived, frozen, live) | temporal-context-handling |
| 18. Detect stale state transitions, emit stale_entered/stale_cleared (skip frozen, live, unforced manual) | temporal-context-handling |
| 19. Read derive contracts from resolved config, detect derivation drift | changes-propagation + per-artifact-config |
| 20. Append material transition events to journals | context-graph-architecture + temporal-context-handling |
| 21. Regenerate export manifests | source-format-and-agent-readable-surfaces |

### Key integration rules

1. **The AST never leaves the parser boundary.** Every downstream system works from section IDs, fingerprints, and frontmatter — never from raw tokens.
2. **Fingerprints are the bridge between parsing and temporal state.** Without them, AMD cannot distinguish "content changed" from "AMD looked at it again."
3. **Journals are the bridge between temporal events and the rebuildable index.** The index can be deleted and reconstructed from journals + signals + current Markdown.
4. **Signals enter independently of refresh.** They are ingested from external sources on their own schedule and merged into the temporal state during refresh.
5. **Temporal policy resolves via the 3-layer chain.** AMD resolves `freshness_class`, `stale_after`, and `refresh_mode` through hardcoded defaults -> `.amd/config/<artifact_id>.yml` -> frontmatter `amd.policy`. Signal thresholds, derive contracts, and required sections come from the same resolution. Resolved values are written into `artifact_temporal` in SQLite so queries can use them without re-reading YAML. Section validation (`amd doctor`) compares `required_sections` from config against the section tree already in SQLite — no separate schema system needed.
6. **Export is the last step.** It snapshots current sqlite state into static JSON for fast agent bootstrap. It is always rebuildable.

## Explicit Beats Heuristic

This is important.

For relation semantics, AMD should prefer:

1. explicit frontmatter declarations
2. explicit `amd link` commands
3. derivation outputs from AMD itself
4. observed moves/renames from stable IDs
5. heuristics

Heuristics should only create:

- candidate links
- agenda items
- `doctor` warnings

They should not silently rewrite the canonical graph.

## Minimal Heuristics Worth Keeping

Only use heuristics for suggestions:

- same old artifact disappeared and near-identical content appeared elsewhere
- title similarity is high
- section-label overlap is high
- structural fingerprint overlap is high

Inference:

This can borrow the spirit of Git rename detection, but AMD should not rely on it as identity truth. Git itself treats rename detection as similarity-based inference during diffing, not as a stored canonical fact.[6]

## Export Shape

AMD should export a lightweight manifest similar to MyST’s `myst.xref.json` pattern.[7]

### What agents use it for

An agent or wrapper can read `amd.xref.json` and immediately know:

- what documents exist and what kinds they are
- how they relate to each other
- what sections/labels each contains
- which file path to open if full content is needed

This avoids the agent having to:

- parse every Markdown file
- rebuild section trees itself
- query SQLite directly

This is a bootstrap/snapshot surface, not the only runtime API. For live ranked or filtered work, the agent should still call `amd prime`, `amd affected`, or `amd query`.

Suggested `amd.xref.json` entry:

```json
{
  "artifact_id": "artifact:plann-auth-v2",
  "kind": "plan",
  "path": "docs/plann.md",
  "title": "Auth Refresh Plan v2",
  "sections": [
    {
      "section_id": "section:overview",
      "label": "overview",
      "heading": "Overview"
    },
    {
      "section_id": "section:execution",
      "label": "execution",
      "heading": "Execution"
    }
  ],
  "relations": [
    {
      "type": "revision_of",
      "target": "artifact:plan-auth-v1"
    }
  ],
  "labels": ["overview", "execution", "risks"]
}
```

### Agent instructions

When acting as a wrapper or skill around AMD:

1. Read `amd.xref.json` first if you need a fast map of the project.
2. Use the manifest to identify relevant artifact IDs, section labels, and source paths.
3. Call `amd affected` or `amd prime` for live ranked context before making decisions.
4. Open the source Markdown file only for the specific artifacts/sections you actually need to read or edit.
5. Do not parse the whole repository or query SQLite directly unless debugging AMD itself.

## Direct Answer To The User Vision

If the user keeps:

- `docs/plan.md`
- `docs/execution.md`
- `docs/plann.md`

AMD should not try to force filesystem cleanliness.

Instead:

- each file gets or resolves to a stable artifact ID
- each file yields a section tree
- `.amd/` records cross-file edges
- agents consume the graph, not filenames

That is the right scope for AMD.

## Doctor Checks For Graph Integrity

`amd doctor` should validate graph-level consistency. These checks run against the index, not by reparsing Markdown.

| Check | Severity | Description |
|---|---|---|
| Active artifact, missing file | ERROR | Artifact in index with `state: active` but source file does not exist at `current_path`. Suggests running `amd refresh` to detect and archive. |
| Live edge to archived artifact | ERROR | Edge with `ended_at = null` pointing at an artifact with `state: archived`. Indicates archival cascade did not complete. |
| Orphaned signal file | WARNING | Signal file in `.amd/signals/` with no corresponding artifact in index. Historical data — not harmful, but should be flagged. |
| Directive with all targets archived | WARNING | Directive with `status: active` but every `reflected_in` edge is ended. The directive may be stale or need revocation. |
| Missing archival cascade | ERROR | Derivation edge where source is archived but downstream target has no `derivation_drift_entered` activity and no caveat referencing the archived source. |
| Dangling section edge | WARNING | Edge targeting a section ID that no longer exists in any current artifact's section tree. Expected after section removal; flagged for cleanup awareness. |

## Reindex Behavior With Missing Artifacts

When `amd reindex` rebuilds the index from scratch:

1. Scan configured Markdown roots for current files.
2. Replay all journal entries to reconstruct activity history, edges, and directives.
3. For artifacts referenced in journals but with no current source file:
   - create an artifact record in the index with `state: archived` and `reason: file_missing`
   - set `ended_at` on all edges involving that artifact
4. For signal files in `.amd/signals/` with no matching artifact in the index:
   - keep the signal files (they are historical data, not garbage)
   - create an archived artifact stub in the index so rollups and history remain queryable
5. Validate all edges: any edge referencing an archived artifact should have `ended_at` set.

This ensures reindex produces the same result as a fresh start followed by incremental refreshes — no orphaned state, no dangling edges, and full history preserved.

## Recommendation

Implement the graph layer as:

- append-only relation/activity journals
- a rebuildable SQLite adjacency-list index
- metadata-native directive/assertion nodes in `.amd/`
- small derived context caches for retrieval and ranking
- stable artifact IDs plus stable section IDs
- explicit relation commands and declarations
- required FTS5-backed section retrieval
- heuristic candidate detection only for suggestions

Do **not**:

- make path the identity
- make a giant nested YAML/JSON graph file
- introduce a dedicated graph database
- turn every project clarification into a fake Markdown artifact
- turn `.amd/` into a mirror of the user's document tree
- pretend the model is a tree when it is actually a graph

## Sources

[1] W3C PROV-DM. `Revision`, `specializationOf`, and `alternateOf` relations. https://www.w3.org/TR/2013/PR-prov-dm-20130312/

[2] SQLite documentation, `WITH RECURSIVE`: recursive CTEs can walk a tree or graph. https://www.sqlite.org/lang_with.html

[3] SQLite WAL documentation: readers do not block writers and a writer does not block readers; checkpoint behavior matters. https://sqlite.org/wal.html

[4] SQLite foreign key documentation. https://www.sqlite.org/foreignkeys.html

[5] SQLite FTS5 documentation. https://sqlite.org/fts5.html

[6] Git documentation on merge and diff behavior. Similarity-based merge/rename handling is useful as a heuristic, not a durable semantic relation model. https://git-scm.com/docs/gitattributes and https://www.kernel.org/pub/software/scm/git/docs/gitdiffcore.html

[7] MyST project metadata and `myst.xref.json` pattern. https://mystmd.org/guide/configuration and https://mystmd.org/guide/website-metadata
