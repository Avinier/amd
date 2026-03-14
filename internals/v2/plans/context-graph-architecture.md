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
- a runbook is derived from a mental model
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

### 6. Activity record

Represents the operation that created or changed graph state.

Fields:

- `activity_id`
- `activity_type` (`refresh`, `link`, `derive`, `materialize`, `doctor`)
- `agent`
- `timestamp`
- `payload_json`

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
  journal/
    activities/
      2026-03.jsonl
    relations/
      2026-03.jsonl
    derivations/
      2026-03.jsonl
  cache/
    index.sqlite
  export/
    amd.xref.json
    artifacts/
      <artifact_id>.json
```

### Why this split

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

### `activities`

- `activity_id TEXT PRIMARY KEY`
- `activity_type TEXT`
- `agent TEXT`
- `timestamp TEXT`
- `payload_json TEXT`

### `artifact_search`

FTS5 virtual table for:

- titles
- labels
- headings
- selected section text

This is required. Topic-based discovery depends on it.

## Update Strategy

### On `amd refresh`

1. Scan configured Markdown roots.
2. Parse frontmatter and Markdown AST.
3. Build section tree for each file.
4. Resolve stable artifact identity:
   - explicit `amd.id` wins
   - otherwise treat as unmanaged/candidate
5. Resolve stable section IDs:
   - explicit label wins
   - otherwise generated stable ID from local structure
6. Compute structural fingerprints.
7. Update locator table.
8. Recompute `contains` edges from the AST.
9. Rebuild explicit relation edges from journal records.
10. Rebuild directive/assertion nodes from journals.
11. Add heuristic candidate edges only as suggestions, not as authoritative facts.

### On `amd link`

Append a relation record to `journal/relations/*.jsonl`, then update the index.

Example:

```json
{
  "activity_id": "act_01",
  "timestamp": "2026-03-11T13:00:00Z",
  "agent": "codex",
  "src_entity_type": "artifact",
  "src_entity_id": "artifact:plann-auth-v2",
  "dst_entity_type": "artifact",
  "dst_entity_id": "artifact:plan-auth-v1",
  "edge_type": "revision_of",
  "origin": "declared"
}
```

### On `amd derive`

Append:

- derivation activity
- one or more `derived_from` edges
- optional section-to-section edges for provenance

### On `amd capture`

Append a directive/assertion record to the journal, then update the index.

Example:

```json
{
  "activity_id": "act_02",
  "timestamp": "2026-03-11T13:05:00Z",
  "agent": "codex",
  "directive_id": "directive:amd-metadata-context",
  "directive_type": "clarification",
  "statement": ".amd/ stores metadata plus a small amount of derived context, but never full user-authored documents",
  "scope": "project",
  "status": "active"
}
```

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
