# AMD v2 Plan: Config And Schemas

## Executive Summary

AMD needs both a project config and a schema system, but they should not compete with each other.

The clean split is:

- **`.amd/config.yml`** defines how this project operates
- **`.amd/schemas/*.yml`** define what artifact kinds mean
- **artifact frontmatter** defines one artifact instance and its local exceptions

That gives AMD three layers with distinct ownership:

- project policy and runtime defaults
- kind semantics and derivation contracts
- instance-specific overrides

The strongest recommendation is:

- keep `config.yml` narrow and operational
- keep schemas as the only place that defines kind structure
- rename config-side `kinds:` to **`kind_policy_overrides:`** if that feature exists at all
- implement schema inheritance in AMD core, not by trying to make JSON Schema itself model class inheritance

This is the best fit for AMD because MyST shows a strong project/page override pattern,[1][2] Dendron shows the value of schemas as an optional type system with template binding,[3] and the JSON Schema project explicitly notes that inheritance is not something JSON Schema can model perfectly on its own.[4][5]

## Key Findings

- **Project config and per-document metadata should be separate layers**: MyST distinguishes project-level configuration from page-level frontmatter and explicitly documents which fields are project-only, page-only, or page-overrides-project.[1][2]
- **Explicit clearing matters**: MyST documents that `null` on the page can override and clear an inherited project value.[1] AMD should adopt the same behavior for overrideable policy fields.
- **Schemas work best as an optional type system**: Dendron describes schemas as an optional type system for notes and highlights automatic template insertion as a primary capability.[3]
- **AMD should not inherit Dendron’s path/hierarchy-centric matching as a core rule**: Dendron’s schemas are hierarchy-oriented,[3] but AMD’s design goal is arbitrary file layout. For AMD, schema selection should be kind-first, not path-first.
- **JSON Schema is good for validation, not for AMD’s semantic inheritance rules**: JSON Schema provides meta-schemas and validation vocabularies,[4] but the JSON Schema team’s own guidance is that inheritance is not fully expressible in JSON Schema itself.[5]
- **Configuration composition should be explicit and conservative**: MyST supports composable config files with `extends`, but its own docs warn about complexity around extended files and override behavior.[1] AMD should support a simpler, safer composition model.
- **Typed internal models are a good implementation fit**: Pydantic can validate Python data structures and emit JSON Schema, which fits AMD’s Python codebase and gives a clean path from YAML -> validated model -> JSON Schema for docs/tests.[6][7]

## Detailed Analysis

### 1. The problem config and schemas solve

AMD needs to answer three different questions:

1. **How should this project behave by default?**
   - freshness defaults
   - rollup windows
   - priority coefficients
   - hooks
   - runtime settings

2. **What is a `report.incident` or `mental_model`?**
   - required sections
   - optional sections
   - template binding
   - ownership defaults
   - derivation contracts

3. **What is special about this one artifact instance?**
   - local labels
   - unusually urgent stale threshold
   - one-off derive override

If AMD tries to answer all three in one file, the system gets blurry. If it splits them cleanly, resolution is straightforward.

### 2. The relation between config, schemas, and frontmatter

The clean model is:

- **config** = project operating environment
- **schema** = kind definition
- **frontmatter** = object instance

That means they are not peers. They are layered.

#### Project config owns

- project-wide artifact policy defaults
- kind-level policy overrides that are local to this project
- runtime behavior
- hooks
- indexing/timeseries tuning

#### Schema owns

- kind ID
- parent kind
- required/optional sections
- template binding
- ownership defaults
- derivation contract
- kind-level default policy

#### Frontmatter owns

- instance identity
- local metadata
- one-off policy overrides
- explicit `null` to clear inherited values

### 3. Recommended resolution order

For effective artifact policy, the recommended order is:

1. project config defaults
2. resolved parent schema policy
3. resolved child schema policy
4. project `kind_policy_overrides`
5. artifact frontmatter override

Rule:

- later layers override earlier ones
- explicit `null` clears an inherited value when that field is nullable

This matches the spirit of MyST’s project/page override behavior,[1][2] while preserving schema portability across projects.

### 4. What should live in `.amd/config.yml`

`config.yml` should contain project-scoped concerns only.

Recommended categories:

- `version`
- `extends`
- `artifact_policy_defaults`
- `kind_policy_overrides`
- `priority`
- `signals`
- `runtime`
- `hooks`

#### Recommended shape

```yaml
version: 1

extends:
  - ./base.amd.yml

artifact_policy_defaults:
  freshness_class: tactical
  stale_after: 24h
  refresh_mode: auto

kind_policy_overrides:
  report.incident:
    freshness_class: observational
    stale_after: 4h
  mental_model:
    freshness_class: foundational
    stale_after: 168h

priority:
  manual_baseline: 50
  coefficients:
    freshness: 10
    caveat: 5
    signal_warn: 10
    signal_critical: 20
    derivation_drift: 10

signals:
  windows: [15m, 1h, 6h, 24h, 7d]
  silence_multiplier: 6

runtime:
  lock_timeout: 5s
  sqlite:
    wal: true

hooks:
  pre_refresh: scripts/pre_refresh.py
  post_refresh: scripts/post_refresh.sh
  post_derive: scripts/post_derive.py
```

#### Why not `defaults: ... priority: ... timeseries: ...` all mixed together

Because some config is inherited artifact policy and some is engine/runtime tuning.

These are not the same thing:

- `stale_after` is inherited artifact policy
- `signals.windows` is engine rollup configuration
- `hooks.post_refresh` is runtime behavior

Grouping them separately makes resolution and reasoning much cleaner.

### 5. What should not live in `config.yml`

Do **not** put these in project config:

- required sections
- optional sections
- template path for a kind
- derive section mappings
- ownership rules for one kind

Those are schema concerns.

This is why `kinds:` is the wrong name if it contains anything beyond policy overrides. It sounds like a second schema registry.

Recommendation:

- use `kind_policy_overrides:` instead of `kinds:`

### 6. What should live in schema files

Schemas should define kind semantics only.

Recommended schema fields:

- `version`
- `id`
- `title`
- `description`
- `parent`
- `template`
- `sections`
- `ownership`
- `policy`
- `derive`

#### Recommended shape

```yaml
version: 1
id: report.incident
title: Incident Report
parent: report

template: templates/report.incident.md

sections:
  required:
    - executive-summary
    - current-context
    - risk-assessment
    - caveats
  optional:
    - timeline
    - affected-services
    - appendices

ownership:
  default: user
  generated: []
  mixed: []

policy:
  freshness_class: observational
  stale_after: 4h

derive:
  targets:
    report.postmortem:
      ownership: generated
      mappings:
        - from: executive-summary
          to: incident-summary
        - from: risk-assessment
          to: contributing-factors
        - from: timeline
          to: timeline-of-events
```

### 7. Schema inheritance

AMD should support parent-child schema inheritance, but the inheritance semantics should be **AMD-owned**, not delegated to JSON Schema inheritance tricks.

Recommended behavior:

- parent and child schemas are both validated structurally
- AMD resolves the inheritance graph in application logic
- the resolved schema is then used for doctor/init/derive

#### Recommended merge rules

- scalar fields
  - child overrides parent
- map/object fields
  - deep-merge
- `sections.required`
  - additive union, preserving order
- `sections.optional`
  - additive union, preserving order
- `ownership`
  - child overrides or extends by bucket
- `derive.targets`
  - child can add new targets or override an existing target spec by target kind

#### Why not just use JSON Schema `allOf`

Because JSON Schema is a validation language, not a complete inheritance language. The JSON Schema project’s own guidance says inheritance is not something it can model perfectly in general.[5]

So the right model is:

- JSON Schema or Pydantic validates the shape of AMD schema documents
- AMD core resolves semantic inheritance itself

### 8. Derivation contracts should be single-sourced

Avoid defining the same mapping in both source and target schemas.

Bad pattern:

- source schema says `decision-rules -> triage-steps`
- target schema repeats the same mapping in reverse

That creates two sources of truth.

Recommended rule:

- the source schema owns the transform contract
- the target schema owns only its own shape and ownership constraints

Optional target-side hint:

- a target schema may declare `accepts_from: [mental_model]` for discoverability or validation, but it should not duplicate the section mapping contract

### 9. Config composition and `extends`

MyST shows that composable configuration is useful,[1] but also shows how override and path semantics can become tricky.

Recommended AMD v2 rule:

- support **local-file `extends` only**
- do not support remote URL config inheritance in v2

Why:

- more reproducible
- easier to cache and debug
- avoids security ambiguity for an agent-native CLI

#### Recommended merge semantics for `extends`

Given:

```yaml
extends:
  - ./base.yml
  - ./team.yml
```

Apply in order:

1. load `base.yml`
2. overlay `team.yml`
3. overlay the current file

Recommended merge behavior:

- scalars override
- maps deep-merge
- lists replace by default
- explicit `null` clears inherited values

This is intentionally simpler than “magic list concatenation” so config composition stays predictable.

### 10. Unknown or schema-less artifacts

AMD should keep schema use optional.

This is one of the strongest borrowable ideas from Dendron: schemas are an optional type system, not a requirement for every note.[3]

For AMD, that means:

- a doc with no known schema is still a valid AMD artifact
- AMD can still track identity, sections, relations, temporal state, and directives
- schema validation simply does not apply
- `amd doctor` should report “unschematized” separately from “invalid against schema”

This matters because AMD explicitly wants to support messy, organic Markdown repositories.

### 11. Validation strategy

AMD needs validation at two levels:

1. **document validation**
   - is `config.yml` structurally valid?
   - is `report.incident.yml` structurally valid?

2. **semantic validation**
   - are there schema cycles?
   - does a parent exist?
   - do derive mappings point at valid section labels?
   - does `kind_policy_overrides.report.incident` reference a known schema or known kind?

Recommended approach:

- use typed internal models to validate loaded YAML
- emit JSON Schema from those models for docs/tests/tooling when helpful
- perform semantic validation in AMD core after loading

Implementation note:

- Pydantic is a strong fit here because it validates Python data via `model_validate()` and can emit JSON Schema from models.[6][7]

### 12. Agent layer

The agentic layer here is not “invent the schema.” It is “decide which layer a change belongs in.”

#### The agent should put a change in:

- **project config** when it is project-wide operational policy
  - example: default freshness class
  - example: signal windows
  - example: hooks

- **schema** when it is kind-wide semantics
  - example: incident reports require `risk-assessment`
  - example: mental models can derive runbooks
  - example: runbook default freshness is tactical

- **artifact frontmatter** when it is instance-specific
  - example: this incident is extra urgent, `stale_after: 2h`
  - example: this legacy doc clears `stale_after`

#### What the agent should actively do

1. Prefer config/schema defaults over per-artifact overrides.
2. If the same frontmatter override appears repeatedly across many artifacts, suggest lifting it into a schema or project config.
3. If no schema fits, create or keep the artifact unschematized rather than forcing a bad kind match.
4. Do not invent new config or schema keys outside the spec.
5. When creating schemas, keep them kind-centric, not path-centric.

#### Practical decision rule for agents

Ask:

- “Does this apply to the whole project?”
  - `config.yml`
- “Does this apply to every artifact of one kind?”
  - schema file
- “Does this apply only to this artifact?”
  - frontmatter

### 13. How this ties into the other v2 plans

#### Source format

- source docs carry only minimal instance metadata in frontmatter
- config and schemas stay in YAML under `.amd/`

#### Context graph

- resolved kind and policy belong in the index
- schemas inform artifact type and derive edges

#### Parsing and section identity

- schema-required section labels can be validated against parsed section IDs

#### Temporal context

- temporal policy resolution depends on config -> schema -> frontmatter precedence

#### Changes propagation

- kind and schema information help agents know which docs are likely affected and how derived docs should be updated

## Areas Of Consensus

- config and schemas should be separate layers
- project policy and kind semantics should not be mixed
- schema use should remain optional
- project overrides should not become a second schema registry
- inheritance should be resolved in AMD logic, not outsourced entirely to JSON Schema

## Areas Of Debate

- whether schema `sections` should be nested as recommended here or remain as top-level `required_sections` / `optional_sections` for maximal brevity
- whether template files should live under `.amd/templates/` or a separate project-relative templates directory
- whether target schemas should have a light `accepts_from` hint or no derive-related fields at all
- whether `extends` should support only one parent in v2 for simplicity, or an ordered list as recommended here

## Recommendation

Implement config and schemas with this strict split:

1. `.amd/config.yml` for project policy, runtime, hooks, and kind policy overrides
2. `.amd/schemas/*.yml` for kind semantics, inheritance, templates, ownership, and derive contracts
3. artifact frontmatter for local exceptions only
4. application-level schema inheritance resolution
5. typed validation plus semantic post-validation
6. schema use remains optional for messy repositories

That is the best fit for AMD’s design goals. It keeps project behavior tunable, kind semantics reusable, and organic Markdown repos first-class instead of forcing every file into a rigid hierarchy.

## Sources

[1] MyST Markdown, “Configuration and content frontmatter.” Official docs. Project/page layering, override behavior, explicit `null`, and `extends`. <https://mystmd.org/guide/configuration>

[2] MyST Markdown, “Content frontmatter options.” Official docs. Field behavior categories such as `project only`, `page only`, and `page can override project`. <https://mystmd.org/guide/frontmatter>

[3] Dendron, “Schemas.” Official docs. Schemas as an optional type system, automatic template insertion, and unknown-schema notes remaining allowed. <https://wiki.dendron.so/notes/c5e5adde-5459-409b-b34d-a0d75cbb1052/>

[4] JSON Schema, “Specification.” Official docs. Meta-schemas and validation vocabularies. <https://json-schema.org/specification>

[5] JSON Schema, “Modelling Inheritance with JSON Schema.” Official blog. Explicitly notes that inheritance is not something JSON Schema can model perfectly in general. <https://json-schema.org/blog/posts/modelling-inheritance>

[6] Pydantic, “Models.” Official docs. `model_validate()` and validation modes over Python/JSON/string data. <https://docs.pydantic.dev/latest/concepts/models/>

[7] Pydantic, “JSON Schema.” Official docs. Pydantic models can generate JSON Schema. <https://docs.pydantic.dev/latest/concepts/json_schema/>

[8] Hugo, “Front matter.” Official docs. Frontmatter formats and cascade behavior; useful comparison point for targeted inheritance/cascade. <https://gohugo.io/content-management/front-matter/>

## Gaps And Further Research

- decide the final field names for schema section definitions (`sections.required` vs `required_sections`)
- decide the final template-path convention
- decide whether unschematized artifacts should carry an explicit generic `kind`
- define exact JSON Schema / Pydantic models for config and schema documents
