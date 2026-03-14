## Executive Summary

There is still no single product that cleanly replaces AMD's target surface: agent-maintained context, provenance, stale-data policy, update priority, derivation, and report-heavy automation. The closest substitutes are combinations of existing tools, not one tool.

After checking the official docs for each candidate, the strongest conclusion is:

- `Obsidian` is the best human-facing Markdown workspace with structured properties, templating, query views, history, and a real CLI. It is strong inspiration for UX and automation surfaces, not a complete AMD replacement. [1][2][3][4][5][6]
- `MyST Markdown` is the strongest technical substrate if AMD wants structure, labels, directives, AST-aware processing, and machine-readable cross-project metadata. It is the best source of implementation ideas for AMD's document model. [7][8][9][10][11][12]
- `Quarto` is the best model for heavy report execution, pre/post hooks, and freeze semantics. It is less relevant for ongoing agent context, but very relevant for report generation and stale-snapshot policy. [13][14]
- `Logseq` has useful ideas around queries and journaling, but its August 31, 2024 Sync guide explicitly said Sync did not support multiple people using the same graph at once, with data-loss warnings; same-page simultaneous editing was described there only via an experimental Smart Merge feature. That makes it a weak base for AMD's multi-agent requirement. [15][16][17]
- `Dendron` is the closest conceptual precursor because it treats schemas and templates as a type system for knowledge. However, the official March 26, 2023 GitHub discussion said the project moved into maintenance mode. Its ideas are worth borrowing; the product itself is not a strong greenfield dependency. [18][19][20]
- `Org mode` is the richest conceptual precedent overall: property drawers, LOGBOOK-style change logs, executable documents, tangling, and batch processing. It proves the shape of the problem better than the Markdown tools do, but it breaks the Markdown constraint. [21][22]

So the opportunity is real, but the project thesis should tighten:

`AMD should be a policy/provenance/index layer for agent-maintained Markdown, not primarily a new filetype.`

## Evaluation Criteria

I evaluated each candidate against the needs AMD is actually trying to solve:

- structured metadata inside or alongside documents
- templating and schema guidance
- multi-user or multi-agent trace/history
- machine-readable querying and indexing
- derivation potential from one artifact to another
- support for large or executable reports
- suitability as an implementation substrate rather than just an authoring UI

## Tool-by-Tool Analysis

### Obsidian

What it clearly provides:

- Typed note properties stored in YAML, with property types including text, list, number, checkbox, date, and date-time. Property names become type-stable across a vault once a type is assigned. [1]
- Template insertion with date/time/title variables, and property merging when templates are inserted into notes. [1][2]
- `Bases`, which are YAML-defined views with filters, formulas, summaries, and views over vault data. [3]
- A real CLI for note creation, reading, appending, searching, history/diff, template access, and Sync history. [4]
- Shared vault collaboration through Obsidian Sync, with documented collaborator limits. [5]
- Official guidance for Git-based syncing, with the explicit caveat that Git syncing is manual. [6]

Important limitations:

- Obsidian properties are intentionally small and atomic; official docs explicitly call out limitations around nested properties, bulk editing, and Markdown inside property fields. [1]
- Shared vault collaboration exists, but it is a product collaboration model, not a general-purpose concurrent transaction system. The docs expose collaborator and file-size limits. [5]

AMD signals to borrow:

- Strong typed frontmatter instead of opaque JSON blobs in the document body.
- Query/dashboard UX similar to Bases for surfacing stale items, caveats, and priority.
- CLI verbs that operate on normal Markdown files instead of inventing a special artifact protocol first.
- History and diff as first-class operations, but with audit/history sourced externally rather than only inline in the note.

Bottom line:

Obsidian is the best reference for the human-facing side of AMD. It is not the full solution for AMD's policy engine, concurrency, or derivation problem.

### MyST Markdown

What it clearly provides:

- Clear separation between page frontmatter and project-level configuration in `myst.yml`, with inheritance and override behavior. [7]
- Directives, including executable `code-cell` directives with labels, captions, numbering, and execution metadata. [8]
- Cross-references built around labeled targets, where references resolve against `label` and `identifier` in the AST. [9]
- A developer-facing AST and transformation pipeline, including explicit cross-reference transforms. [10]
- Structured site metadata exposure via `myst.xref.json` and per-page JSON files containing frontmatter and the full MyST AST. [11][12]

Why this matters for AMD:

- MyST is the only option in this set that already thinks in terms of parse trees, labels, identifiers, transforms, and machine-readable exported metadata.
- That makes it the strongest base for real structural fingerprinting instead of naive text hashing.
- It also gives a path for derivation, because labeled sections and exported AST/JSON make it easier to compute downstream artifacts deterministically.

AMD signals to borrow:

- Use AST-aware parsing and transforms, not raw text hashing, for change detection.
- Support page-level and project-level metadata with inheritance, rather than packing every rule into one file.
- Give sections stable labels/identifiers so agents can refer to targets precisely.
- Expose a machine-readable index/API for artifacts the way MyST exposes cross-reference and page metadata.

Bottom line:

If AMD needs a document substrate rather than a note-taking app, MyST is the strongest reference point by far.

### Quarto

What it clearly provides:

- Project `pre-render` and `post-render` hooks, including arbitrary shell commands. [13]
- Hook execution in the project directory, with environment variables describing input and output file lists. [13]
- `freeze` semantics that prevent or limit re-execution during project renders, including `freeze: true` and `freeze: auto`. [14]
- Explicit documentation that freeze is useful when many collaborators or many long-lived computational documents make full re-execution impractical or fragile. [14]

Why this matters for AMD:

- AMD has a real need around "heavy timeseries based data" and long reports. Quarto is the clearest example in this comparison of how to formalize document refresh policy instead of making everything always live.
- The `freeze` concept is especially relevant. A report can be current enough for navigation while intentionally not recomputing expensive execution on every refresh.

AMD signals to borrow:

- Introduce refresh modes such as live, frozen, manual, or source-change-only.
- Separate "document refresh" from "heavy recomputation" explicitly.
- Add hook points around derivation and report rebuilds instead of mixing them into ad hoc CLI commands.

Bottom line:

Quarto is not a replacement for AMD's context layer, but it is the best model for AMD's report pipeline.

### Logseq

What it clearly provides:

- Query-oriented workflows, including a live query builder announced in March 2023. [16]
- Journal automation through default templates configured in `config.edn`. [17]
- Page history in the context of Sync. [15]

What matters more is what it does not clearly provide:

- In the official August 31, 2024 Sync guide, Logseq said Sync did "NOT support collaboration" for multiple people using the same graph at once and warned that data loss could occur. [15]
- The same guide described simultaneous editing on the same page only through an experimental Smart Merge feature. [15]

AMD signals to borrow:

- Journals/default-template ergonomics for recurring task artifacts.
- Query-builder ideas for non-technical users who still need dashboarding over artifacts.

What not to borrow:

- Any assumption that page-local text files are automatically sufficient for concurrent multi-agent coordination.

Bottom line:

Logseq is useful inspiration for journaling and querying, but its documented collaboration story is too weak for AMD's core traceability promise.

### Dendron

What it clearly provides:

- A schema system intended to apply consistent structure across notes, explicitly described as an optional type system for notes. [19]
- Automatic insertion of templates into new notes from schemas. [19]
- A public product framing around flexible structures, single source of truth, and schemas/templates as a type system for general knowledge. [18]

Status risk:

- In the GitHub discussion answered March 26, 2023, the team said Dendron had entered maintenance mode and would not be actively developing features. [20]

Why Dendron still matters:

- Conceptually, Dendron is the clearest precedent for AMD's "mental model -> operational artifact" and "schema-guided notes" ideas.
- It shows that hierarchy, namespace, and schema-driven creation are not overdesign; they solve a real organizational problem.

AMD signals to borrow:

- Schema inheritance and child constraints.
- Namespace-based artifact organization.
- Template injection tied to schema, not just generic snippet insertion.

Bottom line:

Dendron is the best conceptual ancestor, but not the best dependency.

### Org mode

What it clearly provides:

- A plain-text system for notes, authoring, computational notebooks, literate programming, planning, and project management. [21]
- Property drawers with commands for creating and editing structured properties. [22]
- LOGBOOK-oriented change tracking through TODO state logging and timestamped notes. [22]
- Source block execution, extraction, publishing, and tangling, with hooks and batch execution. [22]

Why this matters for AMD:

- Org mode is the most mature demonstration that text, metadata, logs, code, results, and automation can coexist in one artifact system.
- It also separates concerns better than the current AMD prototype does: property drawers for machine state, log drawers for change history, source/code blocks for execution, and batch tools for automation.

AMD signals to borrow:

- Separate narrative content from machine-managed state and logs.
- Use structured drawers/sections instead of letting metadata sprawl.
- Treat execution and extraction as explicit operations, not incidental side effects.

Bottom line:

Org mode is the strongest conceptual benchmark even though it is not Markdown.

## Requirement Mapping

### Dynamic evolving Markdown for agents

Best references:

- Obsidian properties/templates for author UX. [1][2]
- MyST frontmatter inheritance and AST model for machine structure. [7][10]

AMD implication:

Keep author-facing files close to normal Markdown with typed frontmatter and stable labels, then put richer state in an index.

### Timeline trace for large tasks and multiple agents

Best references:

- Git-style history and Obsidian CLI history/diff surfaces. [4][6]
- Org LOGBOOK-style logging. [22]

AMD implication:

Use append-only event journaling and Git-backed history as the source of truth. Inline timeline sections can remain as rendered summaries, but should not be the primary concurrency surface.

### Better templating and schema guidance

Best references:

- Obsidian templates. [2]
- Dendron schemas/templates as type system. [18][19]

AMD implication:

Templates should be schema-bound and artifact-kind-specific, not free-form starter text.

### Mental model docs derived into skills or operational artifacts

Best references:

- Dendron's schema mindset. [18][19]
- MyST labels, AST, and exported metadata for deterministic downstream transforms. [9][10][11]

AMD implication:

Derivation should be a structured transform pipeline over labeled sections, not just a few copied headings.

### 500-line nuanced report and fingerprint scanning

Best references:

- MyST AST/transforms and exported page JSON. [10][11][12]
- Quarto freeze/rebuild policy for heavy computational docs. [14]

AMD implication:

AMD should move from raw text hashes to normalized Markdown AST fingerprints, then optionally add model-based semantic checks on top.

### Persistent and non-persistent artifacts

Best references:

- MyST page/project metadata patterns. [7]
- Quarto execution policy distinctions. [14]

AMD implication:

This should be a metadata/index policy, not a new file format feature.

### Stale data, update priority, and caveat rules

Best references:

- Obsidian Bases for dashboard/query surface. [3]
- Quarto freeze semantics for "do not recompute blindly." [14]
- Org LOGBOOK/property separation for operational clarity. [22]

AMD implication:

The valuable product is the policy engine and query/index layer, not the metadata itself.

### Heavy timeseries data

Best references:

- Quarto for execution snapshots and render hooks. [13][14]
- Org for executable/source-linked document workflows. [22]

AMD implication:

Heavy data should live outside the Markdown source, with derived summaries rendered into documents and indexed separately.

## What This Means for AMD

AMD should not try to beat these tools at generic note-taking. It should do the part they do not already solve well:

- agent ownership boundaries
- stale-data policy
- priority policy
- caveat enforcement
- derivation from one artifact class to another
- structural fingerprinting
- safe automation and indexing across many artifacts

The current best direction is:

`Markdown or MyST source + Git history + external SQLite index + Quarto-style hooks/freeze + optional Obsidian-style UX`

That is materially different from the current prototype, which still treats one Markdown file as the main transactional surface.

## Concrete Design Signals for AMD v2

1. Keep source documents plain Markdown or MyST-compatible Markdown.
2. Move machine state into an external index, not a large inline metadata blob.
3. Use Git and/or an append-only event journal for audit history.
4. Use AST-based section identifiers and fingerprints, not raw text hashes.
5. Add schema-bound templates inspired by Dendron.
6. Add query/dashboard surfaces inspired by Obsidian Bases.
7. Add report build hooks and freeze modes inspired by Quarto.
8. Render inline timelines as projections, not as the concurrency-critical truth source.
9. Treat derivation as labeled-section transforms with provenance records.

## Recommendation

If AMD continues, the strongest positioning is:

`AMD = provenance, policy, and derivation engine for agent-maintained Markdown artifacts`

not:

`AMD = a brand new Markdown filetype`

That narrower framing is easier to justify technically, easier to explain, and more defensible against the alternatives above.

## Sources

[1] [Obsidian Properties](https://help.obsidian.md/properties) - official help docs; typed YAML properties and limitations.  
[2] [Obsidian Templates](https://help.obsidian.md/Plugins/Templates) - official help docs; templates and variables.  
[3] [Obsidian Bases syntax](https://help.obsidian.md/bases/syntax) - official help docs; YAML views, filters, formulas, summaries.  
[4] [Obsidian CLI](https://help.obsidian.md/cli) - official help docs; automation, file commands, history, search, templates, sync.  
[5] [Obsidian shared vault collaboration](https://help.obsidian.md/sync/collaborate) - official help docs; shared vault model and collaborator limits.  
[6] [Obsidian sync methods, including Git](https://help.obsidian.md/sync-notes) - official help docs; Git and other sync guidance.  
[7] [MyST frontmatter](https://mystmd.org/guide/frontmatter) - official guide; page/project metadata placement and inheritance.  
[8] [MyST directives](https://mystmd.org/guide/directives) - official guide; executable directives and labels.  
[9] [MyST cross-references](https://mystmd.org/guide/cross-references) - official guide; labels, identifiers, and references.  
[10] [MyST Developer Guide](https://mystmd.org/guide/developer) - official guide; AST and transform pipeline.  
[11] [MyST website metadata](https://mystmd.org/guide/website-metadata) - official guide; `myst.xref.json`, page JSON, and AST export.  
[12] [MyST external references](https://mystmd.org/guide/external-references) - official guide; structured cross-project references.  
[13] [Quarto Project Scripts](https://quarto.org/docs/projects/scripts.html) - official docs; pre/post-render hooks and shell commands.  
[14] [Quarto Managing Execution](https://quarto.org/docs/projects/code-execution.html) - official docs; `freeze` modes and collaboration/execution rationale.  
[15] [Logseq Sync guide, August 31, 2024](https://blog.logseq.com/how-to-setup-and-use-logseq-sync/) - official Logseq blog; beta sync, no same-graph collaboration, experimental Smart Merge.  
[16] [Logseq live queries update](https://blog.logseq.com/whiteboards-and-queries-for-everybody/) - official Logseq blog; live query builder.  
[17] [Logseq automated daily template guide](https://blog.logseq.com/how-to-set-up-an-automated-daily-template-in-logseq/) - official Logseq blog; default journal templates.  
[18] [Dendron homepage](https://www.dendron.so/) - official product site; schemas/templates framing.  
[19] [Dendron schemas docs](https://wiki.dendron.so/notes/c5e5adde-5459-409b-b34d-a0d75cbb1052/) - official docs; schema-as-type-system details.  
[20] [Dendron maintenance-mode discussion](https://github.com/dendronhq/dendron/discussions/3890) - official GitHub discussion; maintenance-mode announcement, answered March 26, 2023.  
[21] [Org mode homepage](https://orgmode.org/) - official project site; plain-text notes, authoring, planning, computational notebooks.  
[22] [The Org Manual](https://orgmode.org/org.html) - official manual; property drawers, logging, execution, tangling, and batch processing.  
