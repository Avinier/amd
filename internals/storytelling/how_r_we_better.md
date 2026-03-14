# How Are We Better?

> **Obsidian vault + YAML frontmatter + Git + scheduled refresh/lint scripts + Quarto for report folders = amd**

## The Problem: You're Already Building AMD, Badly

If you're an agent-heavy team managing evolving Markdown artifacts today, you've probably duct-taped together some version of this stack:

| Layer | What You Cobbled Together | What Breaks |
|-------|--------------------------|-------------|
| **Structured metadata** | YAML frontmatter in Obsidian/VSCode | No computed fields. No staleness policy. No priority signal. You write `status: active` and it stays "active" for 6 months. |
| **Change tracking** | Git commits + blame | Tells you *what* changed, not *who among your agents* changed it, *why*, or whether anything is now stale because of it. |
| **Freshness enforcement** | A cron job or pre-commit hook running a lint script | Fragile. Silent failures. The script checks timestamps but has no concept of section-level decay or priority escalation. |
| **Report generation** | Quarto / Jupyter / R Markdown in a separate folder | Disconnected from the living context. The report folder doesn't know your mental model evolved. Freeze semantics are manual. |
| **Templating** | Obsidian templates / cookiecutter / copy-paste from last time | No schema binding. Nothing stops an agent from ignoring the template structure after creation. No guardrails on what sections must exist. |
| **Querying across artifacts** | Obsidian Bases / Dataview plugin / custom grep scripts | Works until you need computed priority, caveat counts, or cross-artifact derivation. Then you're writing a bespoke indexer. |
| **Audit trail** | Git log + maybe a `## Changelog` section someone manually updates | Agents don't update changelogs. Git log doesn't capture agent identity, event kinds, or structured signal data. |

That's **7 tools, 3 config files, 2 cron jobs, and a prayer** that your agents will follow the conventions you documented in a README nobody reads.

AMD replaces all of it with one command: `amd init`.

---

## What AMD Actually Gives You (That the DIY Stack Doesn't)

### 1. Metadata That Computes Itself

YAML frontmatter is static. You set it and forget it. AMD metadata is **alive**:

```
amd refresh docs/
```

One command. Every artifact in the tree gets:
- Section-level fingerprint updates (what actually changed, not just "file modified")
- Staleness flags on sections that haven't been touched within their policy window
- Priority scores recomputed from staleness + active caveats + new signal data
- Status automatically flipped from `active` to `stale` when sections decay

With YAML frontmatter, you write `priority: high`. With AMD, priority is **computed from reality**: how stale the sections are, how many unresolved caveats exist, whether new timeseries data arrived since last review.

### 2. Agent-Native Timeline (Not Git Log Archaeology)

Git gives you diffs. AMD gives you **structured agent history**:

```
## Timeline
<!-- amd:timeline:start -->
- 2026-03-10T18:00:00Z [agent:planner] [kind:note] split work into three streams
- 2026-03-10T18:05:00Z [agent:monitor] [kind:signal] error_rate recorded: 0.12
- 2026-03-10T18:10:00Z [agent:reviewer] [kind:caveat] added (high): staging data only
<!-- amd:timeline:end -->
```

Every event has: timestamp, agent identity, event kind, and structured detail. It's append-only. No agent can rewrite history. You get a traceable narrative of how the artifact evolved, not just a list of diffs.

### 3. Section-Level Staleness (Not File-Level Timestamps)

Your cron job checks `modified_at` on the whole file. AMD tracks freshness **per section**:

- "Executive Summary" was updated 2 hours ago -- fresh
- "Risk Assessment" hasn't been touched in 72 hours -- stale, priority boosted
- "Timeline" is always current by definition -- excluded from staleness

Each section has its own `stale_after_hours` policy. The refresh engine knows the difference between "the file was touched" and "the section that matters was reviewed."

### 4. Caveats as First-Class Objects

In a YAML frontmatter world, caveats are freetext notes that nobody reads. In AMD, they're **structured, expiring, priority-boosting objects**:

```bash
amd caveat docs/report.amd.md --severity high --text "benchmark uses staging data"
```

This caveat:
- Has a severity level (`high`, `medium`, `low`)
- Boosts the artifact's computed priority while active
- Can auto-expire after a set date
- Is tracked in the timeline with the agent who created it
- Shows up in `amd scan` output so no agent can miss it

### 5. Timeseries Without the Bloat

You have a monitoring agent logging metrics. In the DIY stack, those numbers end up either:
- Inline in the Markdown (500-line files become 5000-line files), or
- In a separate system with no link to the document context

AMD puts heavy data in a JSONL sidecar (`.amd/data/<artifact-id>.jsonl`) and keeps a **summary in metadata**: latest value, min, max, count per metric. The narrative stays clean. The data stays linked.

```bash
amd signal docs/task.amd.md --metric error_rate --value 0.12 --unit ratio
```

### 6. Mental Model to Operational Skill (Derivation)

This is something the DIY stack simply cannot do. AMD can take a `mental-model` artifact and **derive** an operational `skill-derived` artifact:

```bash
amd derive-skill docs/payments-model.amd.md docs/payments-runbook.amd.md
```

- "Core Concepts" become "Workflow"
- "Decision Rules" become "Triggers"
- "Failure Modes" become "Guardrails"
- Caveats are inherited with provenance
- The derived artifact knows its source and can be refreshed when the source changes

No template copy-paste. No manual extraction. The derivation pipeline maintains the link.

### 7. One Scanner for Everything

```bash
amd scan docs/
```

Shows you every artifact in the tree with: kind, status, priority (manual + computed), stale section count, active caveats, latest signals. One command replaces your Dataview queries, your grep scripts, and your custom dashboards.

---

## The Replacement Table

| You Were Using | AMD Equivalent | What You Gain |
|---------------|---------------|---------------|
| Obsidian vault | `.amd.md` files in any directory | No app lock-in. Works with any editor. Git-native. |
| YAML frontmatter | `<!-- amd:meta -->` block | Computed priority, staleness, fingerprints, agent tracking. Metadata that updates itself. |
| Git history | Append-only Timeline + Git | Agent-attributed events with structured kinds, not just diffs. |
| Cron refresh scripts | `amd refresh-all` / `amd watch` | Section-level staleness. Priority escalation. No silent failures. |
| Quarto report folders | `report` kind artifacts with timeseries sidecars | Reports live alongside context. Signals stay linked. No folder sprawl. |
| Obsidian templates | Schema-bound `kind` templates (task, report, mental-model, skill-derived) | Templates enforced at creation. Four artifact kinds with purpose-built structure. |
| Dataview / grep scripts | `amd scan` | Priority-ranked artifact overview with caveat counts and stale flags. |
| Manual changelogs | `amd event` | Structured, timestamped, agent-attributed. Append-only. |
| Copy-paste runbooks | `amd derive-skill` | Provenance-linked derivation from mental models to operational artifacts. |

---

## Who This Is For

AMD is not for casual note-taking. It's for teams where:

- **Multiple agents (AI or human) touch the same evolving documents** and you need to know who changed what and whether it's still current
- **Staleness kills you** -- a report from last week that nobody flagged as outdated costs real decisions
- **Context is the product** -- your Markdown files aren't docs, they're living operational artifacts that agents maintain and act on
- **You're tired of the glue** -- the cron jobs, the lint scripts, the frontmatter conventions that nobody follows, the Dataview queries that break when someone renames a property

---

## The One-Liner

You can keep maintaining your Obsidian vault with YAML frontmatter, Git history, cron-scheduled refresh scripts, Quarto report folders, and a hope that your agents follow the rules.

Or you can run:

```bash
pip install amd
amd init docs/my-artifact.amd.md --kind task --title "My Artifact"
```

And get metadata that computes itself, staleness that enforces itself, a timeline that writes itself, caveats that expire themselves, and a priority score that means something.

**That's what AMD does. It's the stack you already built, except it actually works.**
