# AMD v2 Plan: Per-Artifact Config As The Single Policy Lever

## Executive Summary

AMD uses a two-layer config resolution model: per-artifact config files and minimal frontmatter overrides, with universal hardcoded defaults as the baseline. There is no global project config, no shared kind definitions file, and no separate schema subsystem.

The clean split is:

- **`.amd/config/<artifact_id>.yml`** is the single authoritative policy source for each artifact — kind classification, freshness policy, signal thresholds, derive contracts, required sections, refresh mode
- **artifact frontmatter** carries identity (`amd.id`) and rare local one-off policy overrides (`amd.policy`)
- **AMD hardcoded defaults** provide the universal baseline when config fields are absent

Every artifact is different. Even two incident reports may have different staleness thresholds, different required sections, different signal streams. The per-artifact config file is the lever to fine-tune how AMD evaluates, prioritizes, and monitors each artifact's journals and signals.

`kind` is a classification tag, not a resolution layer. It is useful for filtering, querying, and for `amd init` to know which built-in template to seed. But it does not create a shared contract — the config file is the contract.

No schemas. No global config. No `kinds.yml`. Per-artifact config plus hardcoded defaults plus SQLite covers everything.

## Design Principle

**Every artifact is its own thing.**

Even artifacts of the same kind may have different staleness requirements, different signal thresholds, different required sections, and different derive contracts. A payments incident report and a search incident report may both be `report.incident` but live under completely different operational pressures.

The per-artifact config file is the single place where this artifact's operational behavior is defined. The agent sets it up at creation time, adjusts it as the artifact evolves, and AMD reads it on every refresh to evaluate temporal state, signal health, and derivation drift.

## Kind As Classification, Not Contract

### What kind is

`kind` is a free-form classification string stored in the per-artifact config file. It tells agents and humans what type of artifact this is. It is useful for:

- filtering (`amd query --kind report.incident`)
- display and grouping in `amd scan` and `amd agenda`
- `amd init --kind <type>` knowing which built-in template to seed

### What kind is not

`kind` is not a resolution layer. AMD does not look up a kind definition and apply shared defaults. The config file contains all the policy fields this artifact needs. If a field is absent from config, AMD falls through to universal hardcoded defaults — not to a kind-level definition.

This means:

- changing what "incident report" means for a project requires updating each relevant config file
- this is an agent-native operation: the agent can query by kind and update config files in bulk
- there is no hidden shared layer that silently changes behavior across artifacts

### Kind authority

| Surface | Role for `kind` |
|---|---|
| `.amd/config/<artifact_id>.yml` | **Authoritative.** AMD reads kind from here. |
| Artifact frontmatter `amd.kind` | **Informational.** Human convenience. Doctor flags divergence. |

## Why No Global Config

A global `config.yml` would hold project-wide defaults for freshness, priority coefficients, signal windows, and hooks. In practice:

- **Freshness defaults** — hardcoded defaults handle this. `tactical` / `24h` is the universal baseline. Per-artifact config overrides when needed.
- **Priority coefficients** — No one tunes these on Day 1. Hardcode them. Add a config surface later if someone actually needs it.
- **Signal windows and silence multiplier** — `[15m, 1h, 6h, 24h, 7d]` and `6` are sensible defaults. Hardcode them.
- **Hooks** — No other plan references hooks. No command consumes them. Defer.
- **Runtime tuning** — WAL mode on, sensible lock timeout. Implementation details, not user-facing config.

A global config adds a resolution layer that does not pay for itself in v2. Every value it would hold either belongs in per-artifact config or AMD core.

## Why No Shared Kind Definitions

Earlier iterations considered `.amd/kinds.yml` as a shared definition layer — one file defining what each kind means (required sections, freshness policy, derive contracts), resolved at refresh time so all artifacts of a kind inherit shared defaults.

This was cut because:

- **Every artifact is different.** Even artifacts of the same kind may need different freshness thresholds, different signals, different required sections. A shared layer encourages treating same-kind artifacts as interchangeable when they are not.
- **Per-artifact config already covers everything.** Config files are the lever. Making them depend on a shared definition adds a resolution layer without proportional benefit.
- **Bulk kind-level changes are an agent-native operation.** "All incident reports should require a timeline section" is exactly the workflow AMD is built for: query by kind, filter, update config files. The agent handles this the same way it handles any multi-artifact propagation.
- **One fewer resolution layer to debug.** With kinds.yml, a value could come from hardcoded defaults, kind definitions, per-artifact config, or frontmatter. Without it, the chain is: hardcoded → config/ → frontmatter. Simpler to reason about, simpler to implement.
- **Built-in templates handle the Day 1 experience.** `amd init --kind report.incident` seeds the config file with sensible starting values. The artifact gets the right defaults at creation time without needing a live resolution layer.

## Per-Artifact Config

### What it is

`.amd/config/<artifact_id>.yml` is the single authoritative policy source for each artifact. It follows the same per-artifact keying pattern as `journal/` and `signals/`. It defines how AMD evaluates, monitors, and prioritizes this artifact.

### What it contains

A config file defines the full operational policy for this artifact. `amd init --kind <type>` seeds it with built-in template values, then the agent or user adjusts as needed.

A typical config file after `amd init --kind report.incident`:

```yaml
kind: report.incident
freshness_class: observational
stale_after: 4h
refresh_mode: auto

required_sections:
  - executive-summary
  - current-context
  - risk-assessment
  - caveats

optional_sections:
  - timeline
  - affected-services
  - appendices
```

A config file for an artifact with signal tracking and derive contracts:

```yaml
kind: report.incident
freshness_class: observational
stale_after: 2h

required_sections:
  - executive-summary
  - current-context
  - risk-assessment
  - caveats
  - affected-services

signals:
  error_rate:
    expected_cadence: 5m
    thresholds:
      warn: 0.05
      critical: 0.10
  response_time_p99:
    expected_cadence: 5m
    thresholds:
      warn: 500
      critical: 1000

derive:
  targets:
    report.postmortem:
      mappings:
        - from: executive-summary
          to: incident-summary
        - from: risk-assessment
          to: contributing-factors
        - from: timeline
          to: timeline-of-events
```

### Fields

- `kind` — the artifact kind (e.g. `report.incident`, `mental_model`, `runbook`). Free-form string, namespaced by convention. Used for filtering and querying. **This is the authoritative kind assignment for this artifact.**
- `freshness_class` — one of `observational`, `tactical`, `foundational`. Determines how aggressively the artifact decays. Falls through to hardcoded default (`tactical`) if absent.
- `stale_after` — duration string (e.g. `4h`, `24h`, `168h`). The staleness threshold. Falls through to hardcoded default (`86400` / 24h) if absent.
- `refresh_mode` — one of `auto`, `manual`, `frozen`, `live`. Controls which refresh steps apply. Falls through to hardcoded default (`auto`) if absent.
- `required_sections` — list of section labels that `amd doctor` checks for. Falls through to hardcoded default (`[]`) if absent.
- `optional_sections` — list of section labels that are recognized but not required. Falls through to hardcoded default (`[]`) if absent.
- `signals` — map of metric definitions. Each metric has:
  - `expected_cadence` — how often AMD should expect new signal points
  - `thresholds` — `warn` and `critical` numeric boundaries for breach detection
- `derive` — derivation contracts for this artifact as a source.
  - `targets` — map keyed by target kind. Each target has:
    - `mappings` — list of `{ from, to }` section label pairs defining the transform contract

All fields are optional. Absent fields fall through to universal hardcoded defaults. The config file only needs the fields this artifact cares about.

### How section validation works

`amd doctor` validates sections using the config file and the SQLite section tree:

1. Read `required_sections` from `.amd/config/<artifact_id>.yml` (empty list if absent)
2. Query the `sections` table in SQLite for all sections belonging to this artifact
3. Compare: for each required label, check if a section with that label exists
4. Report missing required sections as errors
5. Report "no required_sections configured" as informational (not an error)
6. If frontmatter `amd.kind` diverges from config `kind`, report as error

This is a pure query against existing data — no schema files, no separate subsystem. The section tree is already built and persisted by the parsing plan on every `amd refresh`.

### How it gets created

When `amd init --kind report.incident` runs:

1. AMD looks up the built-in template for `report.incident`
2. AMD creates `.amd/config/<new_artifact_id>.yml` seeded with the template values (freshness_class, stale_after, required_sections, etc.)
3. The agent can adjust any field afterward as this artifact's needs become clearer

Built-in templates are hardcoded in AMD core. They provide sensible starting points for common artifact types. The template is copied into the config file at creation time — it is a snapshot, not a live reference. Subsequent changes to built-in templates (in AMD upgrades) do not retroactively affect existing config files.

When an agent creates an artifact without `amd init` (e.g. just writes a Markdown file and runs `amd refresh`):

1. AMD detects the new artifact
2. AMD creates a config file with no fields — universal hardcoded defaults apply to everything
3. The agent can populate the config file to define this artifact's operational policy

### How it gets updated

The agent updates config/ when:

- The user clarifies policy ("this report should be checked every 2 hours")
- The agent adds signal tracking to an artifact
- The agent sets up a derivation relationship
- The user or agent decides this artifact needs different required sections
- The user changes how this specific artifact should behave

Config files are YAML, human-readable, agent-editable. No special AMD command needed — the agent or user can edit directly, and `amd refresh` picks up changes.

### The `.amd/` directory pattern

```
.amd/
  config/<artifact_id>.yml        # how to evaluate (policy, signals, derive contracts)
  journal/<artifact_id>.jsonl     # what happened (activity history)
  signals/<artifact_id>.jsonl     # what the world says (observations)
  cache/index.sqlite              # computed state (derived, rebuildable)
  export/amd.xref.json            # agent bootstrap map (derived, rebuildable)
  export/artifacts/<id>.json      # per-artifact detail (derived, rebuildable)
```

Three per-artifact source-of-truth layers (config, journal, signals), keyed consistently by artifact ID. One derived cache. One export layer. No project-level definition files.

## Resolution Order

When AMD needs an effective value for an artifact (e.g. `stale_after`):

1. **Universal hardcoded default** — always available (e.g. `tactical` / `24h`)
2. **`.amd/config/<artifact_id>.yml`** — per-artifact policy
3. **Artifact frontmatter `amd.policy`** — local one-off overrides

Later layers override earlier ones.

### Null semantics

- **Field absent** — inherit from the next layer down (hardcoded default)
- **Field set to `null`** — explicitly unset. The value is cleared. It does not fall back to a lower layer. The artifact has no value for this field.
- **Field set to a value** — that value is used

This distinction matters. `stale_after: null` in a per-artifact config means "this artifact has no staleness policy" — it opts out. Removing the `stale_after` line entirely means "use the hardcoded default." These are different intentions and the system respects both.

## Universal Hardcoded Defaults

When no config field is specified, AMD uses these values:

| Parameter | Default | Rationale |
|---|---|---|
| `freshness_class` | `tactical` | Safe middle ground for most documents |
| `stale_after` | `86400` (24h) | One day is reasonable for tactical docs |
| `refresh_mode` | `auto` | Normal recomputation on every refresh |
| `required_sections` | `[]` (empty) | No section validation by default |
| `optional_sections` | `[]` (empty) | No section hints by default |
| `priority.coefficients.freshness` | `10` | |
| `priority.coefficients.caveat` | `5` | |
| `priority.coefficients.signal_warn` | `10` | |
| `priority.coefficients.signal_critical` | `20` | |
| `priority.coefficients.derivation_drift` | `10` | |
| `signals.windows` | `[15m, 1h, 6h, 24h, 7d]` | Standard rollup windows |
| `signals.silence_multiplier` | `6` | 6x expected cadence before flagging silence |

These are compiled into AMD core. They are not user-configurable in v2. If a future version needs project-level tuning for these universal values, a project config can be added then.

## Built-In Kind Templates

AMD ships with built-in templates for common artifact types. These are used by `amd init --kind <type>` to seed the config file. They are not a runtime resolution layer — they are copied into the config file at creation time.

Built-in templates (starting set):

| Kind | freshness_class | stale_after | required_sections |
|---|---|---|---|
| `report.incident` | `observational` | `4h` | executive-summary, current-context, risk-assessment, caveats |
| `report.postmortem` | `tactical` | `168h` | incident-summary, timeline-of-events, contributing-factors, remediation |
| `runbook` | `foundational` | `720h` | purpose, prerequisites, steps |
| `mental_model` | `foundational` | `720h` | (none) |
| `decision` | `tactical` | `168h` | context, options, decision, rationale |

If `amd init --kind <type>` receives a kind with no built-in template, AMD creates a config file with just `kind: <type>` and universal hardcoded defaults apply.

The agent can define any custom kind string — `kind` is free-form. Custom kinds just don't get template seeding.

## What Frontmatter Owns

Frontmatter carries identity and rare local policy overrides. It should be minimal.

### What frontmatter contains

```yaml
---
title: Payments Incident Report — Critical
amd:
  id: report.payments.incident-2026-03-11
  kind: report.incident           # informational — must match config if present
  policy:
    stale_after: 2h               # this one is extra urgent
---
```

- `amd.id` — artifact identity. Required.
- `amd.kind` — informational only. AMD does not use this for kind resolution. If present, `amd doctor` checks that it matches the config file's `kind` and flags divergence as an error.
- `amd.policy.*` — one-off policy overrides for this artifact instance. These are the highest-precedence layer in resolution.

Frontmatter is for: "this specific artifact instance is temporarily different from its config."

### What should NOT be in frontmatter

- Computed state (staleness, priority, signal rollups)
- Full signal definitions (those belong in config/)
- Derive contracts (config/ is the canonical home)
- Required section lists (those belong in config/)
- Caveat lists (those live in journals)
- Kind assignment (config/ is authoritative)

If the same frontmatter override appears across many artifacts, the agent should lift it into config/ files.

## Derive Contracts: Canonical Home

Derive contracts live in per-artifact config files only.

When `amd derive` creates a new derivation, the agent records the contract in the source artifact's config file. This makes every derivation relationship explicit and traceable to a specific artifact's config.

Frontmatter is **not** a home for derive contracts. Derive contracts are structural relationships, not one-off overrides.

## Agent Layer

### What the agent should actively do

1. **Set kind and policy at artifact creation.** When creating a new artifact, use `amd init --kind <type>` to seed the config file. Review the seeded values and adjust if this artifact is different from the template.

2. **Treat config/ as the operational lever.** Config is where the agent tunes how AMD evaluates this artifact — freshness, signals, required sections, derive contracts, refresh mode. It is the primary surface for all operational policy.

3. **Infer kind from document purpose.** Daily reports -> `report.incident`. Architecture decisions -> `decision`. The agent picks the right kind for classification, but then reviews and adjusts the seeded config fields based on this artifact's actual needs.

4. **Prefer config/ over frontmatter.** Frontmatter is for temporary exceptions. Config/ is for the normal operating parameters.

5. **Update config/ when the user clarifies policy.** "This report should be checked every 2 hours" -> edit config/ `stale_after`.

6. **Record derive contracts in config/.** After running `amd derive`, ensure the source artifact's config/ has the contract recorded.

7. **Add signal definitions to config/ when connecting an artifact to external metrics.** The agent writes the metric name, expected cadence, and thresholds.

8. **Handle bulk kind-level changes as a propagation operation.** If the user says "all incident reports should require a timeline section," the agent queries by kind, filters relevant config files, and updates them. This uses the same capture → affected → filter → edit workflow as any other propagation.

### Practical decision rule

- "What kind is this artifact?" -> config/ `kind` field
- "What policy governs this artifact?" -> config/ (everything is here)
- "Is this one instance temporarily different?" -> frontmatter `amd.policy`
- "Change behavior for all artifacts of a kind?" -> agent updates relevant config/ files in bulk

## How This Ties Into Other v2 Plans

### Context graph architecture

- config/ files are read during refresh to populate `artifact_temporal` in SQLite
- derive contracts in config inform derivation drift detection
- the `.amd/` directory layout has `config/` alongside `journal/` and `signals/`

### Temporal context handling

- `stale_after`, `freshness_class`, and `refresh_mode` come from config/ with hardcoded fallback
- signal thresholds for breach/silence detection come from config/
- priority coefficients are hardcoded in AMD core (universal)
- signal windows and silence multiplier are hardcoded in AMD core

### Markdown parsing and section identity

- `required_sections` are read from config/ and validated against the section tree in SQLite
- `amd doctor` queries SQLite's `sections` table and compares against config's required sections — no separate schema system needed
- `amd doctor` checks frontmatter `amd.kind` against config `kind` and flags mismatches
- config/ does not interact with the parser — it is purely operational

### Changes propagation

- When a user clarifies policy for one artifact, the agent updates that artifact's config/
- When a user clarifies policy for a kind (bulk change), the agent queries by kind and updates relevant config/ files
- `amd affected` does not search config/ — it searches FTS5 over artifact content
- config/ changes do not trigger `content_changed` events (config is operational metadata, not content)

### Source format and agent-readable surfaces

- frontmatter stays minimal: `amd.id`, optional informational `amd.kind`, optional `amd.policy` overrides
- config/ is a machine surface, not an authoring surface — agents read and write it
- JSON exports include resolved temporal state (from SQLite), not raw config/ contents

### Bootstrap and project setup

- `amd init --project` creates the `.amd/` directory structure (config/, journal/, signals/, cache/, export/)
- `amd init --kind <type>` seeds config/ with built-in template values for that kind
- Projects that use custom kinds get universal hardcoded defaults — zero config required beyond `kind`

## Gaps and Further Research

- Define the full set of AMD built-in kind templates (the table above is a starting point)
- Decide whether `amd doctor` should distinguish severity levels for missing required vs optional sections
- Decide whether config/ should support a `signals.*.dimensions` field for multi-dimensional metric filtering
- Define exact Pydantic models for config/ validation and resolution
- Decide whether a bulk config update command (e.g. `amd config --kind report.incident --set required_sections+=timeline`) is needed in v2 or whether agent-driven multi-file edits are sufficient
