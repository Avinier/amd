# AMD v2 Plan: Clarification Propagation

## The Problem

A user is chatting with an agent. Mid-conversation, they say something like:

> ".amd/ should contain metadata plus a little derived context, not full content"

or

> "AMD is a CLI that agents invoke, not a human-first tool"

That clarification is now relevant to 3, 5, maybe 10 existing documents. The user should not have to say "now go update file X, Y, Z." The agent should know where it matters and go handle it.

This is the core AMD use case. Everything else — the graph, the index, the sections — exists to make this workflow possible.

## The Correct Mental Model

**The agent is the brain. AMD is the hands.**

AMD does not decide what needs updating. AMD does not understand the clarification. AMD does not judge relevance.

AMD does:

- Return candidates: "here are all artifacts and sections that mention X"
- Execute graph operations: create metadata-native directives/assertions, record edges, update the index
- Provide structured context: section text, relation edges, freshness state

The agent does:

- Understand the clarification semantically
- Judge which candidates actually need updating (AMD returns 10, maybe 3 are relevant)
- Decide how to edit each section
- Write the actual content changes

This is a strict separation. AMD is a tool the agent calls. The agent is the intelligence.

## The Two-Layer Architecture

### Core layer (what the CLI does)

These are pure operations. No judgment, no AI, no heuristics about what "should" be updated.

- `amd capture` — create a metadata-native directive/assertion in the graph
- `amd affected` — query the graph for candidate artifacts/sections related to a topic
- `amd refresh` — re-scan files and update the index after edits
- `amd link` — record a relation edge between graph entities
- All existing commands from the skeleton (event, caveat, signal, scan, query, etc.)

The core layer is deterministic. Given the same graph state and the same query, it returns the same candidates. It never silently rewrites content. It never decides which files to update.

### Agent layer (what the CLI-wrapper prompts)

This is the intelligence layer. It lives outside the core CLI, in a wrapper that provides instructions to external agents (Claude Code, Codex, etc.) on how to use AMD.

The agent layer handles:

- **Interpretation**: understanding what the user's clarification means
- **Filtering**: looking at AMD's candidate list and deciding which actually need changes
- **Editing**: writing the actual prose changes into each affected file
- **Judgment calls**: "this file mentions .amd/ but in a different context, skip it"
- **Ordering**: deciding which files to update first based on importance

The agent layer is delivered as:

- A skill definition / MCP tool description / system prompt fragment
- Instructions that tell the agent: "when a user clarifies something, here's how to use AMD"
- NOT as compiled code inside the CLI

This means the agent layer is swappable. Claude Code gets one prompt. Codex gets another. A future agent gets its own. The core CLI stays the same.

## The Flow

```
1. User says: "btw, .amd/ should contain metadata plus a little derived context, not full content"

2. Agent understands this is a clarification/directive

3. Agent calls AMD core:
   $ amd capture --type directive --directive-type clarification --statement ".amd stores metadata plus a little derived context, not full content" --scope project
   → creates directive directive:amd-metadata-context
   → returns directive_id

4. Agent calls AMD core:
   $ amd affected --query ".amd" --query "storage" --query "content"
   → returns candidate list:
     - context-graph-architecture.md § "Where To Store Graph State"
     - context-graph-architecture.md § "Export Shape"
     - scaffold.md § "Journal Layer"
     - scaffold.md § "Projection Layer"
     - skeleton.md § "F5. Journal Layer"
     - skeleton.md § "F6. Rebuildable Local Index"
     - skeleton.md § "F14. Projection And Materialization"
     - skeleton.md § "Directory Layout"
     - usecase.md § "The Flow Visualized"
     - usecase.md § "Why This Flow Works"

5. Agent (the brain) filters the list:
   - "context-graph-architecture.md § Where To Store Graph State" — YES, needs a note
     that .amd/ stores metadata plus small derived context
   - "scaffold.md § Journal Layer" — YES, should clarify journals are machine context, not full content
   - "skeleton.md § Directory Layout" — YES, add a note
   - "usecase.md § The Flow Visualized" — NO, the diagram already implies this, skip
   - ... etc.

6. Agent edits the files it selected (3 out of 10)

7. Agent calls AMD core:
   $ amd refresh
   → index catches content changes, updates fingerprints

8. Agent calls AMD core:
   $ amd link directive:amd-metadata-context --edge reflected_in --targets artifact:context-graph,artifact:scaffold,artifact:skeleton
   → records which artifacts were updated to reflect this directive
```

## What AMD Core Needs For This

### New metadata-native primitive: `directive` / `assertion`

A directive/assertion is a small, load-bearing metadata record. It fans out to many artifacts, but it is not itself a Markdown document.

Fields:

- `directive_id`
- `directive_type`: `clarification`, `constraint`, `decision`, `invariant`
- `statement`
- `scope`: what area this directive affects (freeform tag or namespace)
- `status`: `active`, `superseded`, `revoked`
- `source_activity_id`

Directives/assertions are first-class graph entities in `.amd/`. They get stable IDs, they participate in edges, they show up in `amd scan`, and they never require creating a fake Markdown file.

`.amd/` may also keep small derived context alongside this metadata so retrieval works well, but it should not become a full document mirror.

If a directive later needs durable human rationale, it can be promoted into or linked to a real `decision_record` artifact. That is optional, not the default.

### New command: `amd capture`

Creates a metadata-native directive/assertion without requiring a Markdown file.

```
amd capture --type directive --directive-type clarification --statement "..." [--scope "..."]
```

What it does:

- Creates a directive/assertion record in the index
- Writes the canonical record into `.amd/` metadata storage
- Returns the `directive_id`

This is a core command. It does not decide what to do with the directive — it just records it.

### New command: `amd affected`

Queries the graph for artifacts/sections relevant to a topic.

```
amd affected --query "term" [--query "term2"] [--kind plan,architecture] [--format json]
```

What it does:

- Runs FTS5 search over section headings, labels, and text
- Follows relation edges from matching artifacts
- Returns a ranked candidate list with:
  - artifact_id
  - section_id
  - file path
  - section heading
  - match reason (FTS hit, relation edge, both)
  - snippet of matching text

What it does NOT do:

- Decide which candidates need updating
- Filter by relevance to the specific clarification
- Modify any files

This is a pure query. The agent uses the output to make its own decisions.

### FTS5 is required, not optional

Earlier drafts treated FTS5 as optional. It is not.

FTS5 is the engine behind `amd affected`. Without it, the only way to find relevant sections is:

- Grep the filesystem (brittle, no section awareness)
- Walk relation edges only (misses documents not yet linked)

FTS5 indexes titles, headings, labels, and section text. This is what makes topic-based discovery possible.

### New edge type: `reflected_in`

For connecting directives/assertions to the artifacts they affected.

```
directive:amd-metadata-context --reflected_in--> artifact:context-graph-arch
directive:amd-metadata-context --reflected_in--> artifact:scaffold
```

This creates a traceable record: "this directive is reflected in these artifacts."

Related edges AMD should support:

- `applies_to` for scoping a directive to artifacts/sections/domains
- `supersedes` for replacing an older directive
- `contradicted_by` for surfacing drift or inconsistency

## What The Agent Layer Needs

The agent layer is NOT code in the CLI. It is a prompt/instruction set that tells external agents how to use AMD. It ships with AMD as package-owned instructions or skill definitions, not as project data inside `.amd/`, and it runs inside the agent, not inside AMD.

### The agent instruction set should cover:

**1. Recognizing clarifications**

When the user says something that sounds like a directive, constraint, clarification, or decision about the project:

- Capture it with `amd capture`
- Then run `amd affected` to find what needs updating

Not every user statement is a directive. The agent uses judgment.

**2. Filtering candidates**

AMD returns candidates. The agent must:

- Read each candidate section (or at least the heading + snippet)
- Decide: does this section actually need to reflect the clarification?
- Skip sections where the existing text already aligns or where the context is different

The instruction should explicitly say: "Do not blindly update every candidate. Read first, judge, then edit."

**3. Making edits**

For each section the agent decides to update:

- Read the full section
- Integrate the clarification naturally into the existing prose
- Do not rewrite sections wholesale — make targeted additions/modifications
- Respect ownership: only edit user-owned sections if the user initiated the change

**4. Closing the loop**

After edits:

- Run `amd refresh` to update the index
- Run `amd link` to connect the directive to affected artifacts
- Optionally: tell the user what was updated and why

### Example agent instruction fragment

```
When the user makes a clarification, constraint, or decision about the project:

1. Record it:
   amd capture --type directive --directive-type clarification --statement "<brief summary>"

2. Find affected documents:
   amd affected --query "<key terms from the clarification>"

3. Review the candidate list. For each candidate:
   - Read the section
   - Decide if it needs updating to reflect the clarification
   - Skip sections where the existing text already aligns

4. Edit only the sections that need it. Make targeted changes,
   not wholesale rewrites.

5. Update the graph:
   amd refresh
   amd link <directive_id> --edge reflected_in --targets <updated_artifact_ids>

6. Tell the user what you updated:
   "Updated 3 of 10 candidate sections to reflect: <clarification>"
```

## What This Changes In Existing Plans

### context-graph-architecture.md

- FTS5 moves from "optional" to required
- metadata-native `directive` / `assertion` node added
- `reflected_in`, `applies_to`, and `supersedes` added as edge types
- `amd affected` and `amd capture` added as commands

### skeleton.md

- F16 (Command Surface) gains `capture` and `affected`
- F6 (Rebuildable Local Index) gains FTS5 as a required table
- A new metadata entity type is needed for directives/assertions
- A new feature section is needed for the agent instruction layer

### scaffold.md

- The "Command Surface" section should reference `capture` and `affected`
- The "Prime / Context Delivery" section should note that `affected` is the discovery mechanism for propagation, while `prime` is the delivery mechanism for general context

## Design Constraints

1. **AMD core never decides what to update.** It returns candidates. The agent filters.

2. **AMD core never edits content.** It provides graph operations. The agent writes prose.

3. **The agent layer is prompts, not code.** It ships with AMD but runs inside the external agent.

4. **FTS5 is required.** It is the discovery mechanism. Without it, `amd affected` cannot work.

5. **Directives/assertions are first-class metadata entities.** They are small but load-bearing. They create traceable update history without polluting the artifact space.

6. **The agent must filter, not blindly propagate.** The instruction set must explicitly say: read first, judge, then edit. AMD returning 10 candidates does not mean 10 files need changes.
