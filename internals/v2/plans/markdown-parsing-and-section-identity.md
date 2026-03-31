# AMD v2 Plan: Markdown Parsing And Section Identity

## Executive Summary

AMD v2 should use a real Markdown parser, not heading regexes. The best v2 fit is `markdown-it-py` as the parser foundation, with AMD-specific handling for label comments and generated blocks, plus tolerant read support for MyST targets and heading-ID syntaxes.[1][2][3][8][9]

The recommended architecture is:

- parse Markdown with `markdown-it-py`
- build a synthetic-root section tree from heading tokens
- prefer explicit labels for stable section identity
- use opaque persisted section IDs for unlabeled sections
- compute AST-aware content and subtree fingerprints
- skip unchanged files by whole-file hashing rather than chasing incremental region parsing

Tree-sitter is attractive for incremental parsing, but the current Markdown grammar explicitly says it is not recommended where correctness matters.[5][6] That makes it the wrong default for AMD v2, where section identity and drift detection have to be trustworthy.

## Key Findings

- **`markdown-it-py` is the best parser foundation for v2**: it is Python-native, exposes tokens and a syntax tree, supports plugins, and is the parser family MyST already builds on.[1][2]
- **AMD should be MyST-compatible without becoming MyST-dependent everywhere**: MyST’s parser is a `markdown-it-py` parser with additional rules enabled, which means AMD can stay on the same conceptual stack without making the whole product a docs-site tool.[2][3]
- **Tree-sitter should not be the v2 default**: tree-sitter itself is incremental and fast, but the tree-sitter Markdown grammar warns that it is not recommended where correctness matters.[5][6]
- **Section identity must be label-first**: generated IDs can be made stable enough for local continuity, but only explicit labels truly survive heading renames, reordering, and cross-file movement.[3][8][9]
- **The section tree should use a synthetic artifact root**: treating the first `#` heading as the root creates special cases around multiple H1s and pre-heading content. A synthetic root keeps the tree consistent.
- **Fingerprinting should be Merkle-like**: one fingerprint for the section’s own normalized content and one recursive fingerprint for the section plus children. That supports both local diffing and whole-document drift rollups.
- **File-level incremental refresh is enough for v2**: hashing the full file and reparsing only changed files delivers most of the performance gain without the complexity of incremental AST parsing.[5]

## Detailed Analysis

### 1. Parser choice

#### Option A: `markdown-it-py`

Pros:

- proper token stream
- syntax-tree support via `SyntaxTreeNode`[1]
- plugin model for parser extensions and custom rules[1]
- Python-native and already aligned with the AMD codebase
- directly compatible with MyST’s parser strategy[2]

Cons:

- AMD still has to build its own section tree and identity layer on top
- MyST target syntax is not free unless AMD enables MyST rules or implements tolerant support

#### Option B: `mistune`

Pros:

- Python-native
- exposes AST tokens directly[4]
- relatively simple embedding model

Cons:

- less aligned with MyST and the existing v2 direction
- smaller ecosystem for AMD’s specific compatibility goals

#### Option C: `tree-sitter`

Pros:

- incremental parsing
- fast editor-oriented update model[5]

Cons:

- Markdown grammar is a separate project
- the current Markdown grammar says it is not recommended where correctness matters[6]
- Markdown parsing requires block and inline passes, which adds more machinery than AMD needs for v2[6]

#### Recommendation

Use `markdown-it-py` as the v2 parser backend.[1]

Design the parser layer as a small AMD abstraction:

- `parse_markdown(source) -> token stream + line map`
- `build_section_tree(tokens, markers) -> artifact root + sections`
- `fingerprint_sections(tree) -> content/subtree hashes`

If AMD later wants deeper MyST support, it can switch parser construction to a MyST-enabled `markdown-it-py` parser without rewriting the section-tree and fingerprint layers.[2]

### 2. Parsing pipeline

AMD should split parsing into two phases:

1. **AMD marker pre-pass**
   - strip frontmatter into structured metadata
   - detect AMD-generated block fences
   - detect AMD HTML comment labels
   - record marker line ranges

2. **Markdown parse**
   - parse the remaining body with `markdown-it-py`
   - walk tokens or `SyntaxTreeNode`
   - build the section tree using heading tokens and recorded marker metadata

Important note:

- using small regex or line scanners for AMD-owned markers is fine
- using regex to parse Markdown structure is the dead end

### 3. Section tree construction

AMD should always create a synthetic artifact root:

- `artifact_root(level=0, section_id=<artifact-root>)`

Then reconstruct heading nesting from heading levels.

Recommended algorithm:

```python
stack = [artifact_root]

for block in parsed_blocks:
    if block.is_heading():
        while stack[-1].level >= block.level:
            stack.pop()

        section = Section(
            parent=stack[-1],
            level=block.level,
            heading=block.heading_text,
            ordinal=next_child_ordinal(stack[-1]),
        )
        stack[-1].children.append(section)
        stack.append(section)
    else:
        stack[-1].content.append(block)
```

Recommended edge-case rules:

- pre-heading content belongs to the synthetic root
- multiple H1 headings are legal and become sibling top-level sections
- skipped heading levels do not create phantom nodes
- duplicate headings are allowed and disambiguated by explicit labels or persisted IDs

### 4. Label syntax

AMD should distinguish between:

- **write syntax**: what AMD itself emits by default
- **read syntax**: what AMD is willing to recognize

#### Write default

Use AMD HTML comments:

```md
<!-- amd:label overview -->
## Overview
```

Why:

- invisible in normal rendered Markdown
- works in plain Markdown everywhere
- easy for agents to insert mechanically

#### Read support

Support, in this order:

1. AMD HTML label comments
2. MyST header targets, e.g. `(my-section)=` before a heading[3]
3. Heading identifier attributes such as `{#id}` from kramdown/Pandoc-style Markdown[8][9]
4. generated IDs

AMD should **not** use frontmatter label maps for section identity. They are too easy to drift out of sync with the actual document.

### 5. Stable section IDs

The section ID should not be a slug.

For unlabeled sections, AMD should generate an opaque stable ID on first encounter and persist it in the index, for example:

- `section:01jabc...`

This is better than making the canonical ID equal to the current heading slug, because heading-slug IDs are guaranteed to churn on rename.

Recommended resolution order:

1. explicit AMD label comment
2. MyST target label
3. heading attribute ID
4. persisted unlabeled-section match from prior refresh
5. new opaque generated ID

For persisted unlabeled-section matching, keep v2 conservative and deterministic.

Only treat an unlabeled section as the same prior section if all of these hold:

- same artifact
- exact `content_fingerprint` match
- same heading level
- same nearest labeled ancestor, if one exists

Use ordinal position only as a tie-breaker when more than one prior candidate satisfies the hard rules.

If AMD cannot identify exactly one match, create a new section ID and let `doctor` flag the ambiguous rename/move.

Practical rule:

- if an agent creates cross-section edges, it should ensure both sections have explicit labels first
- unlabeled sections get continuity best-effort only; labels are the actual stability mechanism

### 6. Fingerprinting model

AMD should compute two hashes per section:

1. **content fingerprint**
   - normalized content owned directly by this section
   - excludes child sections

2. **subtree fingerprint**
   - hash of:
     - normalized heading text
     - section block structure
     - content fingerprint
     - child subtree fingerprints

This makes the tree Merkle-like:

- local changes stay local in `content_fingerprint`
- parent drift propagates through `subtree_fingerprint`
- artifact root subtree fingerprint acts as a whole-document structural fingerprint

### 7. Normalization rules

Recommended normalization before hashing:

- strip frontmatter
- strip AMD label comments
- strip AMD generated blocks entirely
- collapse internal whitespace in normal text nodes
- trim surrounding whitespace in text nodes
- normalize unordered list markers to one form
- normalize ordered list numbering to structure rather than literal numeral
- preserve code block content verbatim
- preserve block types and ordering

Recommended non-normalization:

- do **not** normalize heading text case
- do **not** normalize code fences into plain text

Rationale:

- heading renames are meaningful enough that AMD should notice them
- code formatting often matters operationally

### 8. What goes into `.amd/` for retrieval

This must stay within the “metadata plus a little context” boundary from the other plans.

Recommended storage:

- in FTS:
  - heading text
  - labels
  - normalized plain-text section content
- in `sections` table:
  - a short eagerly stored snippet, such as first paragraph or first ~200 characters
- in `amd.xref.json`:
  - section IDs
  - labels
  - headings
  - relation summary
  - source path

Do **not** put full section text into `amd.xref.json`.

That file is the bootstrap map, not the content payload.

Snippets should be stored eagerly during refresh, not computed lazily at query time. `amd affected` is supposed to return cheap candidate previews from the index without reopening source files unless the agent decides a section needs deeper review.

### 9. Incremental strategy

For v2, use **file-level** incremental behavior:

1. hash file bytes
2. compare to prior file hash
3. if unchanged, skip parse
4. if changed, reparse the whole file

This is the right compromise:

- simple
- deterministic
- cheap enough for normal repos
- no dependence on editor-style incremental parsing

### 10. What happens when a section ID disappears

If an unlabeled section cannot be matched confidently and receives a new section ID on refresh:

- edges pointing at the old section ID remain part of history but are marked ended in the index
- `doctor` should flag those old section references as stale/dangling
- agents may relink them after review, but AMD should not silently retarget section edges through a heuristic match

This keeps the graph conservative. AMD may fail closed on ambiguous continuity, but it should not rewrite provenance into a possibly wrong shape.

### 11. Edge cases AMD must explicitly test

- ATX headings and Setext headings[7]
- headings inside fenced code blocks should not become sections[7]
- content before first heading
- multiple H1s
- skipped heading levels
- duplicate headings
- unclosed fences[7]
- generated block stripping
- label comments immediately before headings
- MyST targets immediately before headings[3]
- heading attributes after headings[8][9]
- duplicate explicit labels
- rename of labeled section vs rename of unlabeled section

`markdown-it-py` normalizes heading tokens with levels regardless of whether the source heading was ATX or Setext, so the section-tree algorithm only needs to operate on parser-reported heading levels.[1][7]

## Recommended Stack

### Parser/runtime

- `markdown-it-py` as the default parser backend[1]
- optional MyST-enabled parser construction if AMD wants full MyST target support without reimplementing it[2]
- simple AMD pre-pass for:
  - frontmatter extraction
  - AMD label comment detection
  - generated block range detection

### Identity model

- synthetic artifact root
- label-first section identity
- opaque persisted generated IDs for unlabeled sections
- deterministic unlabeled continuity matching with fail-closed behavior
- `doctor` warnings for ambiguous continuity

### Fingerprint model

- normalized content fingerprint
- recursive subtree fingerprint
- generated blocks excluded

### Refresh model

- whole-file hash for skip detection
- full parse only for changed files
- no tree-sitter incremental parsing in v2

## Areas of Consensus

- Regex heading extraction is not enough for v2.
- Explicit labels are the only truly stable section identity.
- AMD needs AST-aware normalization before hashing.
- Generated blocks must be excluded from normal fingerprinting.
- File-level skip is enough for the first real implementation.

## Areas of Debate

- Whether AMD should depend directly on `myst-parser` or stay on raw `markdown-it-py` plus tolerant compatibility support
- Whether heading attributes should be fully supported or only tolerated on read

## Recommendation

For v2, implement the parser layer this way:

1. Pre-scan raw source for frontmatter, AMD label comments, and generated block ranges.
2. Parse Markdown with `markdown-it-py`.
3. Reconstruct a synthetic-root section tree from heading tokens.
4. Resolve labels using AMD comments first, then MyST targets, then heading attributes.
5. Assign opaque persisted IDs to unlabeled sections and only preserve them automatically under strict exact-match rules.
6. Normalize section ASTs and compute content + subtree fingerprints.
7. Store headings, labels, eager snippets, and normalized plain text for FTS.
8. End stale section-targeted edges rather than silently retargeting them.
9. Skip unchanged files via whole-file hashing.

This is the best fit for the current AMD v2 direction: Python-native, Markdown-first, MyST-compatible, agent-friendly, and implementable without overengineering.

## Agent instructions

Agents do not call the parser layer directly, but they rely on it whenever they use AMD’s graph and retrieval surfaces.

### When this layer is used

This layer is exercised when an agent:

- runs `amd refresh` after editing Markdown
- runs `amd affected` and expects section-level candidates with stable IDs and snippets
- runs `amd prime` or reads `amd.xref.json` and expects accurate section and label metadata
- creates section-to-section edges for derivation, provenance, or references
- runs `amd doctor` to validate labels, continuity, and stale section references

### What agents should assume

- explicit labels are the only durable cross-edit section anchors
- unlabeled sections get best-effort continuity only
- generated blocks do not count as normal section content for drift or fingerprint purposes
- if a section was renamed without a label, AMD may assign a new section ID rather than guessing

### What agents should do

1. Run `amd refresh` after source edits before trusting section IDs, snippets, or fingerprints.
2. Add explicit labels before creating section-level links, derivations, or long-lived references.
3. Prefer AMD-returned section IDs over heading text when recording graph edges.
4. If `doctor` reports ambiguous continuity or stale section references, repair by labeling the section and relinking rather than expecting AMD to guess.
5. Do not parse the repository independently unless debugging AMD itself; rely on AMD’s parser output through `affected`, `prime`, `doctor`, and exports.

## Sources

[1] markdown-it-py documentation, token stream, syntax tree, and plugin model. Official docs. https://markdown-it-py.readthedocs.io/en/latest/using.html

[2] MyST parser docs: MyST parser is a `markdown-it-py` parser with extensions pre-enabled. Official docs. https://myst-parser.readthedocs.io/en/v0.17.2/api/parsers.html

[3] MyST cross-references docs: header targets use `(label)=` and targets require `label`/`identifier` pairs in the AST. Official docs. https://mystmd.org/guide/cross-references

[4] Mistune advanced guide: AST token access via `renderer='ast'`. Official docs. https://mistune.lepture.com/en/latest/advanced.html

[5] Tree-sitter README: incremental parsing system for programming tools. Official repository. https://github.com/tree-sitter/tree-sitter

[6] tree-sitter-markdown README: not recommended where correctness is important. Official repository. https://github.com/tree-sitter-grammars/tree-sitter-markdown

[7] CommonMark specification: heading and code-fence parsing behavior. Official spec. https://spec.commonmark.org/

[8] kramdown syntax docs: explicit header IDs via `{#id}`. Official docs. https://kramdown.gettalong.org/syntax.html

[9] Pandoc user guide: heading identifiers and implicit header references. Official docs. https://pandoc.org/MANUAL.pdf

## Gaps And Further Research

- Decide whether AMD wants full MyST parser dependency in v2 or only compatibility behavior
- Specify the exact canonical serialization format used before hashing
- Decide whether `amd doctor` should auto-suggest labels for referenced unlabeled sections
