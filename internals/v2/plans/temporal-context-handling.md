# AMD v2 Plan: Temporal Context And Freshness

## Executive Summary

AMD should treat time as a first-class property of Markdown artifacts, but not by becoming a version-control system. Git remains the history of prose. AMD adds a second temporal layer: append-only operational history for changes, reviews, caveats, derivations, and signals, then materializes current freshness and priority state into SQLite.[4][5]

The core design is:

- raw temporal facts live in append-only journals and signal streams
- derived temporal state lives in the rebuildable SQLite index
- agents consume that state through `amd prime`, `amd agenda`, `amd history`, and `amd query --stale`
- agents, not AMD core, decide what stale means for the current task

That gives AMD the flagship behavior you want: incident reports, log-heavy docs, and active plans can be judged not only by when they were edited, but by when they were last reviewed, whether reality has moved, whether expected data stopped arriving, and whether upstream sources drifted.[1][2][3]

## Key Findings

- **AMD needs two histories, not one**: Git should remain the full content history, while AMD keeps operational/provenance history such as reviews, caveats, signal ingestion, freshness transitions, and derivation drift.[4][5]
- **Freshness needs multiple clocks**: `last_changed_at`, `last_observed_at`, `last_reviewed_at`, and `last_signal_at` answer different questions. Refreshing a file should never make it look reviewed.
- **Signal absence is itself a temporal fact**: cadence-aware silence should be modeled explicitly, not inferred loosely, following the same basic idea as Prometheus `absent_over_time`.[7]
- **Append-only raw points plus incremental rollups are the right fit**: this matches the existing v2 direction and the general continuous-aggregate pattern without turning AMD into a TSDB.[6]
- **State transitions matter more than scan noise**: `amd refresh` should record material temporal transitions, not spam one event for every unchanged artifact on every run.
- **Temporal computation belongs in core; action belongs in agents**: core computes freshness, decay, breaches, silence, and drift. Agents decide whether to update, annotate, defer, or just review.[1][2][3]

## Detailed Analysis

### 1. What “temporal context” means in AMD

AMD temporal context is not one thing. It is three related layers:

1. **Content history**
   - owned by Git
   - answers: what exact prose changed, when, and in which commit

2. **Operational history**
   - owned by AMD journals
   - answers: when AMD observed a change, when an agent reviewed a section, when a caveat became active, when a signal breached a threshold, when a downstream artifact drifted

3. **Current temporal state**
   - owned by the SQLite index
   - answers: is this artifact stale now, which section is stalest, which signals are silent, why is its priority high

This split is the cleanest fit for AMD because it keeps `.amd/` lightweight and queryable while avoiding the mistake of storing full Markdown snapshots in machine state.[1][4][5]

### 2. Core conclusion

AMD should be **event-sourced in the small**, not in the total-system sense.[4]

That means:

- raw temporal facts are append-only
- current temporal state is derived from those facts plus the latest parsed Markdown state
- the index is rebuildable from Markdown, journals, and signals

It does **not** mean:

- AMD becomes the canonical history of document text
- AMD stores full document revisions
- every refresh appends a giant snapshot of every artifact

Git is still the content ledger. AMD is the operational time layer on top.

### 3. Bottom-up temporal types

The types in this section (`JournalRecord`, `SignalPoint`, `SignalRollup`, `ArtifactTemporalState`, `SectionTemporalState`) are AMD core internal types defined in AMD's own source code. They are not user-facing config files. Per-artifact operational parameters (freshness policy, signal thresholds, derive contracts, required sections) live in `.amd/config/<artifact_id>.yml` — see the per-artifact-config plan for details.

However, the JSONL file format for journals and signals is not rigidly predefined. Each JSONL line has two layers:

1. **Core envelope** — a small set of mandatory fields that AMD core requires for computation (rollups, freshness, indexing, breach detection). These field names and types are fixed.
2. **Agent/user context** — everything beyond the envelope. The agent or user shapes this however the domain requires. Core stores it faithfully, indexes it for query, but does not validate or interpret it.

This means the on-disk JSONL schema is flexible. Core reads its envelope fields and passes through the rest. Agents and users are free to add any fields they need for their domain without modifying AMD core.

For **core-emitted** records (e.g. `content_changed`, `signal_breach_entered` — things `amd refresh` produces), core is the author, so core defines the full shape. For **agent/command-emitted** records (e.g. `review_recorded`, `caveat_added`, `signal_ingested` — things agents produce via CLI commands), the activity type reference below defines conventions, not enforcement.

#### `JournalRecord`

Canonical append-only temporal fact for machine or human actions.

Core envelope (mandatory — AMD core reads these for computation and indexing):

- `activity_id`
- `activity_type`
- `artifact_id`
- `occurred_at`
- `recorded_at`

Agent/user context (agent-authored — core stores and surfaces but does not validate):

- `target_entity_type` (`artifact`, `section`, `directive`)
- `target_entity_id`
- `section_ids` nullable
- `actor`
- `summary`
- `detail_json`
- any additional fields the agent wants to include

##### `summary` field

Free-form, agent-authored string. This is the operational context line for the activity — written by whatever agent or command invoked the action. AMD core does not template or generate it; the caller provides it.

Rules:

- must be operational context, never quoted prose from the Markdown source
- should be self-contained enough that an agent reading `amd history` output can understand what happened without opening the artifact file
- no length requirement, but short is better — one or two sentences typical
- AMD core may provide a fallback (e.g. "refresh detected 3 section changes") when the caller omits it, but the caller's summary always wins
- agents should write summaries that help future agents, not just log entries for humans

##### Design rules

1. `detail_json` is conventionally typed per activity type. The activity type reference below defines recommended fields per type as guidance for agents. Core does not validate `detail_json` contents — for agent-emitted types, the agent decides the shape. For core-emitted types (produced by `amd refresh`), core defines and writes the shape.
2. `occurred_at` is the real-world timestamp of the event. `recorded_at` is when AMD wrote the journal entry. External signals and delayed imports can arrive late; AMD preserves source time. Freshness anchors to `occurred_at`.
3. State transition pairs (`_entered` / `_cleared`) are always matched. An `_entered` without a corresponding `_cleared` means the condition is still active.
4. One journal record per material transition, not per scan. A nightly refresh that touches 200 unchanged files should not produce 200 journal records.
5. Signals and caveats are independent systems. Signal transitions do not auto-create caveats. Agents decide whether a breach or silence warrants a caveat.
6. `detail_json` is the canonical name for the per-activity payload field across all plans.

##### Journal storage

Journal files are per-artifact, identified by artifact ID — the same pattern as signals:

```
.amd/journal/
  report.payments.incident.jsonl
  mental_model.payments.jsonl
  _project.jsonl

.amd/signals/
  report.payments.incident.jsonl
  mental_model.payments.jsonl
```

Each artifact has one journal file and one signal file, both keyed by artifact ID. Every record in a journal file is a `JournalRecord` with an `activity_type` discriminator. Filtering by type happens at query time (via the SQLite index), not at storage time.

`_project.jsonl` holds project-level records that don't belong to a single artifact (e.g. `refresh_run`). The underscore prefix distinguishes it from artifact-keyed files.

This means:
- `amd history artifact:X` reads one file
- archival (soft-delete) preserves both `journal/<id>.jsonl` and `signals/<id>.jsonl` — they are historical data, not garbage. Only permanent hard-deletion (a future operation, not part of v2) would remove these files.
- journal and signal storage follow the same partitioning convention

##### Activity type reference

---

###### `artifact_created`

A new artifact was initialized and claimed by AMD.

- **Trigger**: `amd init --kind <type>`
- **Scope**: artifact
- **Required `detail_json`**:
  - `kind` — the artifact kind (e.g. `report.incident`)
  - `source_path` — file path relative to project root
- **Optional `detail_json`**:
  - `template_used` — template file path, if scaffolded from one
  - `initial_policy` — `{ freshness_class, stale_after, refresh_mode }` if set at creation
- **Consumers**: `amd history`, agents inspecting artifact provenance, `first_seen_at` derivation

---

###### `artifact_archived`

An artifact's source file was removed or the artifact was explicitly archived. This is a soft-delete: the artifact remains in the index with `state: archived`, all history and signals are preserved, but it exits the active working set.

- **Trigger**: `amd refresh` detects a previously tracked file no longer exists at its `current_path`, OR explicit `amd archive <artifact_id>` command
- **Scope**: artifact
- **Required `detail_json`**:
  - `reason` — one of `file_missing` (detected on refresh), `explicit_archive` (user/agent ran archive command), `superseded` (replaced by another artifact)
  - `last_known_path` — the file path where the artifact was last seen
- **Optional `detail_json`**:
  - `superseded_by` — artifact ID of the replacement, if `reason` is `superseded`
  - `last_content_fingerprint` — fingerprint at time of archival, for future re-identification
  - `cascade_targets` — list of downstream artifact IDs that received drift + caveat as a result of this archival
- **Consumers**: `amd history`, `amd doctor`, export manifest, agent workflow, edge ending logic
- **Design note**: archival is always soft-delete. Signal files (`.amd/signals/<id>.jsonl`) are NOT deleted — they are historical data. Rollups for archived artifacts are not recomputed on subsequent refreshes. Active caveats on the archived artifact transition to a terminal state but are not deleted. The artifact can return to `active` if a file reappears with the same `amd.id` in frontmatter.

##### Cascade on archival

When artifact A is archived, AMD core performs the following cascade in the same refresh pass:

1. **Derivation edges where A is the source**: set `ended_at = now` on each edge. For each downstream target artifact, emit `derivation_drift_entered` with `detail_json.reason: source_archived`. Auto-create a caveat on each downstream artifact with severity `high`, text "Source artifact `<A.id>` has been archived; derived content may be stale or unsupported", no expiry (requires manual mitigation by agent or user).
2. **Relation edges where A is source or target**: set `ended_at = now`. No further cascade — relation edges are informational, not operational.
3. **Directive edges where A is a target**: the `reflected_in` edge to A is ended. The directive itself remains active. `amd doctor` flags directives where all `reflected_in` targets are archived.

##### Artifact lifecycle transitions

Artifact state transitions:

- `active` → `archived`: file missing on refresh, or explicit `amd archive` command, or superseded
- `archived` → `active`: file reappears at the same or new path with the same `amd.id` in frontmatter (re-claim on refresh). AMD emits a new `artifact_created` activity with `detail_json.reclaimed: true` and reconnects edges where possible.
- `active` → `superseded`: explicit, via `amd archive <id> --superseded-by <new_id>`. A form of archival with a forward pointer.

Rules:

- archived artifacts remain in the index with `state: archived`
- archived artifacts remain queryable via `amd history` and `amd query --include-archived`
- archived artifacts do NOT appear in `amd agenda`, `amd prime`, or `amd scan` by default (use `--include-archived` flag to include)
- `amd export` marks archived artifacts with `state: archived` in `amd.xref.json` rather than omitting them, so downstream consumers know the artifact existed

---

###### `content_changed`

A section or artifact fingerprint materially changed on refresh.

- **Trigger**: `amd refresh` detects fingerprint difference
- **Scope**: artifact and section (one record per artifact, `section_ids` lists affected sections)
- **Required `detail_json`**:
  - `changed_sections` — list of `{ section_id, old_fingerprint, new_fingerprint }`
- **Optional `detail_json`**:
  - `change_classification` — one of `lexical`, `structural`, `move` (from the parsing plan's change taxonomy)
  - `frontmatter_changed` — boolean, true if frontmatter fields changed
- **Consumers**: `last_changed_at` computation, derivation drift detection, `amd history`
- **Design note**: does not record the actual text diff. For prose deltas, agents use Git.

---

###### `review_recorded`

An artifact or section was explicitly verified as still accurate, without editing.

- **Trigger**: `amd review artifact:<id>` or `amd review artifact:<id> --section section:<id>`
- **Scope**: artifact or section
- **Required `detail_json`**:
  - `reviewed_by` — actor identity (agent name or user)
- **Optional `detail_json`**:
  - `section_ids` — specific sections reviewed (null = whole artifact)
  - `notes` — free-text reason or observation from the reviewer
- **Consumers**: `last_reviewed_at` computation, freshness anchor, priority scoring
- **Design note**: editing does not imply review. Review is a separate, explicit act. This type only records "confirmed accurate." If the reviewer finds the content wrong, the response is a content edit or caveat, not a review record.

---

###### `caveat_added`

A new caveat was attached to an artifact, section, or directive.

- **Trigger**: `amd caveat` command
- **Scope**: artifact, section, or directive (determined by `target_entity_type`)
- **Required `detail_json`**:
  - `caveat_id` — stable caveat identifier
  - `severity` — one of `low`, `medium`, `high`, `critical`
  - `text` — the caveat statement
- **Optional `detail_json`**:
  - `expires_at` — ISO timestamp, null if no expiry
  - `section_ids` — sections the caveat scopes to, if narrower than whole artifact
  - `evidence_refs` — list of references (signal metric names, external URLs, other artifact IDs) supporting the caveat
- **Consumers**: `active_caveat_count`, priority scoring (caveat penalty), agent trust assessment

---

###### `caveat_mitigated`

A caveat was explicitly resolved by an agent or human.

- **Trigger**: agent or user resolves a caveat (via `amd caveat --resolve <caveat_id>` or equivalent)
- **Scope**: inherits from the original caveat's scope
- **Required `detail_json`**:
  - `caveat_id` — which caveat was resolved
  - `resolved_by` — actor identity
- **Optional `detail_json`**:
  - `resolution_reason` — free-text explanation
  - `resolution_activity_id` — link to the content edit or review that addressed it
- **Consumers**: `active_caveat_count` decrement, priority re-scoring
- **Design note**: mitigation is always explicit. Signal recovery does not auto-mitigate caveats.

---

###### `caveat_expired`

A caveat's `expires_at` timestamp has passed.

- **Trigger**: `amd refresh` detects `now > caveat.expires_at`
- **Scope**: inherits from the original caveat's scope
- **Required `detail_json`**:
  - `caveat_id` — which caveat expired
  - `expired_at` — the expiry timestamp that was crossed
- **Consumers**: `active_caveat_count` decrement, priority re-scoring, `amd history`
- **Design note**: expiry is automatic on refresh. Expired caveats are no longer active but remain in history.

---

###### `signal_ingested`

A new signal datapoint was recorded for an artifact's metric stream.

- **Trigger**: `amd signal --artifact <id> --metric <name> --value <num>`
- **Scope**: artifact
- **Required `detail_json`**:
  - `metric` — metric name
  - `value` — numeric value
  - `observed_at` — when the observation occurred in the real world
- **Optional `detail_json`**:
  - `unit` — unit of measurement
  - `source` — where the signal came from (monitoring system, API, manual)
  - `dimensions` — key-value map of labels/tags on the signal
- **Consumers**: signal rollup computation, `last_signal_at`, cadence health tracking
- **Design note**: one record per datapoint. For batch ingestion, emit one `signal_ingested` per point. The raw numeric stream also lives in `.amd/signals/<artifact_id>.jsonl` as `SignalPoint` records; this journal record is the operational log entry, not a duplicate of the raw data.

---

###### `signal_breach_entered`

A signal metric crossed a defined threshold.

- **Trigger**: `amd refresh` detects metric value outside threshold bounds
- **Scope**: artifact
- **State transition pair**: cleared by `signal_breach_cleared`
- **Required `detail_json`**:
  - `metric` — which metric breached
  - `threshold_value` — the threshold that was crossed
  - `breach_value` — the actual signal value at breach time
  - `direction` — `upper` or `lower`
- **Optional `detail_json`**:
  - `window` — which rollup window detected the breach (e.g. `1h`, `24h`)
- **Consumers**: `signal_breach_count`, priority scoring (signal penalty), agent routing
- **Design note**: signals and caveats are independent. A breach does not auto-create a caveat. Agents inspect breaches and decide whether to add a caveat, edit content, or investigate the data source.

---

###### `signal_breach_cleared`

A signal metric recovered from a previously entered breach state.

- **Trigger**: `amd refresh` detects metric value returned within threshold bounds
- **Scope**: artifact
- **State transition pair**: resolves a prior `signal_breach_entered`
- **Required `detail_json`**:
  - `metric` — which metric recovered
  - `recovery_value` — the signal value after recovery
- **Optional `detail_json`**:
  - `breach_duration` — how long the breach lasted
- **Consumers**: `signal_breach_count` decrement, priority re-scoring

---

###### `signal_silence_entered`

An expected signal stream stopped arriving beyond the cadence tolerance.

- **Trigger**: `amd refresh` detects `now - latest_observed_at > expected_cadence * silence_multiplier`
- **Scope**: artifact
- **State transition pair**: cleared by `signal_silence_cleared`
- **Required `detail_json`**:
  - `metric` — which metric went silent
  - `expected_cadence` — the configured expected interval (e.g. `5m`)
  - `last_observed_at` — when the last signal arrived
  - `silence_duration` — elapsed time since last observation
- **Optional `detail_json`**:
  - `silence_multiplier` — the multiplier used (default 6)
- **Consumers**: `signal_silence_count`, priority scoring, agent routing
- **Design note**: silence means "the data pipeline is not delivering." It is operationally different from a breach. Agents should investigate the data source, not the document content.

---

###### `signal_silence_cleared`

A previously silent signal stream resumed.

- **Trigger**: `amd refresh` or `amd signal` detects new datapoint for a previously silent metric
- **Scope**: artifact
- **State transition pair**: resolves a prior `signal_silence_entered`
- **Required `detail_json`**:
  - `metric` — which metric resumed
  - `resumed_value` — the new signal value
- **Optional `detail_json`**:
  - `silence_duration` — total duration of the silence period
- **Consumers**: `signal_silence_count` decrement, priority re-scoring

---

###### `derivation_updated`

A derived artifact was regenerated from its source.

- **Trigger**: `amd derive --source <source_id> --target <target_id>`
- **Scope**: artifact (target artifact is the `artifact_id`)
- **Required `detail_json`**:
  - `source_artifact_id` — upstream artifact
  - `source_section_ids` — which source sections fed the derivation
  - `target_section_ids` — which target sections were produced or updated
- **Optional `detail_json`**:
  - `config_source` — the config file that defined the derivation contract
  - `mappings` — list of `{ from, to }` section mappings applied
- **Consumers**: derivation provenance, drift baseline reset, `amd history`
- **Design note**: this also clears any active `derivation_drift_entered` state for the same source-target pair.

---

###### `derivation_drift_entered`

A source artifact changed after a derivation, making the downstream target potentially stale.

- **Trigger**: `amd refresh` detects source artifact fingerprint differs from the fingerprint at last derivation
- **Scope**: artifact (target artifact is the `artifact_id`)
- **State transition pair**: cleared by `derivation_drift_cleared`
- **Required `detail_json`**:
  - `source_artifact_id` — which upstream artifact changed
  - `source_section_ids` — which source sections changed
  - `old_fingerprint` — source fingerprint at last derivation
  - `new_fingerprint` — current source fingerprint
- **Optional `detail_json`**:
  - `drift_classification` — `lexical`, `structural`, or `move` (from parsing plan change taxonomy)
- **Consumers**: `derivation_drift_count`, priority scoring (derivation drift penalty), agent workflow (re-derive vs review)

---

###### `derivation_drift_cleared`

Derivation drift was resolved, either by re-deriving or by explicit review confirming the target is still valid.

- **Trigger**: `amd derive` (re-derivation) or `amd review` on the target with drift acknowledged
- **Scope**: artifact (target artifact is the `artifact_id`)
- **State transition pair**: resolves a prior `derivation_drift_entered`
- **Required `detail_json`**:
  - `source_artifact_id` — which upstream artifact
  - `resolution_method` — `re_derived` or `reviewed`
- **Optional `detail_json`**:
  - `resolved_by` — actor identity
- **Consumers**: `derivation_drift_count` decrement, priority re-scoring

---

###### `directive_created`

A new directive or assertion was captured as a project-level metadata entity.

- **Trigger**: `amd capture --type directive --directive-type <type> --statement "..."`
- **Scope**: project-level (the `artifact_id` envelope field is null; the `target_entity_type` is `directive`)
- **Required `detail_json`**:
  - `directive_id` — the stable identifier assigned to the directive
  - `directive_type` — one of `clarification`, `constraint`, `decision`, `invariant`
  - `statement` — the directive text
- **Optional `detail_json`**:
  - `scope` — what area this directive affects (freeform tag or namespace)
  - `status` — `active` (default), `superseded`, `revoked`
- **Consumers**: graph index rebuild, `amd scan` directive inventory, agent propagation workflow, `amd history`
- **Design note**: directives are project-level entities, not scoped to a single artifact, so this record is appended to `journal/_project.jsonl`. This is the second activity type (alongside `refresh_run`) where `artifact_id` is null.

---

###### `directive_propagated`

A directive or assertion was reflected into one or more artifacts.

- **Trigger**: `amd link <directive_id> --edge reflected_in --targets <artifact_list>` or agent records propagation after manual edits
- **Scope**: directive (the `target_entity_type` is `directive`)
- **Required `detail_json`**:
  - `directive_id` — which directive was propagated
  - `target_artifacts` — list of artifact IDs that were updated to reflect the directive
- **Optional `detail_json`**:
  - `target_sections` — map of `{ artifact_id: [section_ids] }` for section-level tracking
  - `propagated_by` — actor identity
  - `remaining_targets` — artifact IDs that still need propagation (for partial propagation)
- **Consumers**: directive lifecycle tracking, `amd scan` propagation status, agent workflow ("has this been fully propagated?")

---

###### `relation_created`

A graph edge was created between two entities.

- **Trigger**: `amd link` command
- **Scope**: artifact (the source entity's artifact is the `artifact_id`) or project-level when the source is a directive
- **Required `detail_json`**:
  - `src_entity_type` — `artifact`, `section`, or `directive`
  - `src_entity_id` — source entity ID
  - `dst_entity_type` — `artifact`, `section`, or `directive`
  - `dst_entity_id` — destination entity ID
  - `edge_type` — the relation type (e.g. `revision_of`, `derived_from`, `depends_on`, `reflected_in`)
- **Optional `detail_json`**:
  - `origin` — `declared` (explicit `amd link`) or `inferred` (heuristic/agent-suggested)
- **Consumers**: graph index rebuild, `amd history`, agent provenance queries
- **Design note**: replaces the former `journal/relations/` subfolder. Edge records are now standard journal records in the single journal stream.
- **Journal partition rule**: when `src_entity_type` is `artifact` or `section`, the record goes to `journal/<src_artifact_id>.jsonl`. When `src_entity_type` is `directive`, the record goes to `journal/_project.jsonl` (with `artifact_id: null`) plus a copy to each `journal/<dst_artifact_id>.jsonl` (with `artifact_id` set to the destination artifact) so per-artifact history includes the edge. See the context-graph-architecture plan for the full partition rule.

---

###### `stale_entered`

An artifact crossed its staleness threshold (staleness_ratio >= 1.0) as detected during refresh.

- **Trigger**: `amd refresh` computes `staleness_ratio >= 1.0` for an artifact whose previous stored `stale_state` was `fresh` or `aging`
- **Scope**: artifact
- **State transition pair**: cleared by `stale_cleared`
- **Required `detail_json`**:
  - `staleness_ratio` — the computed ratio at detection time
  - `freshness_anchor_at` — the anchor timestamp used
  - `stale_after_seconds` — the resolved threshold used
- **Optional `detail_json`**:
  - `previous_stale_state` — `fresh` or `aging`
  - `freshness_class` — the resolved freshness class
- **Consumers**: `amd history` freshness timeline, agent workflow, priority explanations
- **Design note**: since staleness is continuous, the actual threshold crossing may have occurred between refreshes. The `occurred_at` timestamp records when AMD detected the transition, not the exact moment it happened. To reconstruct the approximate crossing time, agents can compute `freshness_anchor_at + stale_after_seconds`. This is a core-emitted type — AMD refresh produces it, not agents.

---

###### `stale_cleared`

An artifact returned below its staleness threshold after being stale, typically because of a content edit or review.

- **Trigger**: `amd refresh` computes `staleness_ratio < 1.0` for an artifact whose previous stored `stale_state` was `stale`
- **Scope**: artifact
- **State transition pair**: resolves a prior `stale_entered`
- **Required `detail_json`**:
  - `staleness_ratio` — the new ratio after clearing
  - `resolution_cause` — `content_changed` or `review_recorded` (whichever reset the freshness anchor)
- **Optional `detail_json`**:
  - `stale_duration_approx` — approximate duration of the stale period (time between `stale_entered` and this event)
- **Consumers**: `amd history` freshness timeline, agent workflow

---

###### `refresh_run`

An `amd refresh` operation completed.

- **Trigger**: `amd refresh` command finishes
- **Scope**: project-level (not artifact-specific; `artifact_id` is null)
- **Required `detail_json`**:
  - `artifacts_scanned` — count of artifacts parsed
  - `artifacts_changed` — count with material content changes
- **Optional `detail_json`**:
  - `sections_changed` — total count of sections with fingerprint changes
  - `stale_entered` — count of artifacts that crossed into stale state
  - `stale_cleared` — count of artifacts that returned from stale state
  - `caveats_expired` — count of caveats that expired during this refresh
  - `breaches_entered` — count of new signal breaches detected
  - `breaches_cleared` — count of signal breaches resolved
  - `silences_entered` — count of new signal silences detected
  - `silences_cleared` — count of signal silences resolved
  - `drifts_entered` — count of new derivation drifts detected
  - `drifts_cleared` — count of derivation drifts resolved
  - `duration_ms` — wall-clock duration of the refresh
  - `scope` — `all` or list of specific paths/artifact IDs if partial refresh
- **Consumers**: audit trail, performance tracking, agent coordination
- **Design note**: this is one of the activity types where `artifact_id` is null (alongside `directive_created`). It summarizes the refresh operation itself. Per-artifact material transitions are recorded as separate journal records (`content_changed`, `caveat_expired`, etc.).

---

##### Command trigger map

| Command | Activity types emitted |
|---|---|
| `amd init` | `artifact_created` |
| `amd refresh` | `refresh_run`, plus per-artifact: `artifact_archived` (if file missing), `content_changed`, `stale_entered`, `stale_cleared`, `caveat_expired`, `caveat_added` (cascade from archival), `signal_breach_entered`, `signal_breach_cleared`, `signal_silence_entered`, `signal_silence_cleared`, `derivation_drift_entered`, `derivation_drift_cleared` |
| `amd archive` | `artifact_archived`, plus cascade: `derivation_drift_entered` and `caveat_added` on downstream artifacts |
| `amd review` | `review_recorded`, optionally `derivation_drift_cleared` (if reviewing a drifted target) |
| `amd caveat` | `caveat_added` |
| `amd caveat --resolve` | `caveat_mitigated` |
| `amd signal` | `signal_ingested`, optionally `signal_silence_cleared` (if metric was silent) |
| `amd derive` | `derivation_updated`, optionally `derivation_drift_cleared` |
| `amd capture` | `directive_created` |
| `amd link` | `relation_created`, and `directive_propagated` when linking directives to targets |
| `amd materialize` | none (only writes Markdown output, no temporal activity) |

#### `SignalPoint`

Canonical raw numeric observation for a metric. One line in `.amd/signals/<artifact_id>.jsonl`.

A signal is any value that can change over time due to its environment, and therefore needs to be tracked over time. Documents make claims about the world, and the world moves. A signal is the numeric evidence that the world has moved — or hasn't. When the signal changes, the artifact's claims may need updating. When the signal stops arriving, the artifact may be going blind.

Signals are not limited to any domain. They can represent anything quantifiable that bears on the artifact: research citation counts, market prices, customer satisfaction scores, test pass rates, content engagement numbers, competitor activity, regulatory changes, inventory levels, or any domain-specific measurement. The only requirement is that the value is numeric and the observation has a timestamp.

Core envelope (mandatory — AMD core reads these for rollup computation, freshness, and cadence):

- `metric` — name of the metric. Free-form string, namespaced by convention. No enforced naming scheme, but dot-separated namespacing is recommended for clarity (e.g. `engagement.page_views`, `market.price_usd`, `test.pass_rate`, `ops.error_rate`). The metric name is the key that groups signal points into a stream.
- `observed_at` — ISO 8601 timestamp of when the observation occurred in the real world. This is the authoritative time for freshness and cadence computation.
- `value` — numeric value. Float. Required and must not be null. If the intent is to record "observed but no meaningful value," the caller should use a sentinel (e.g. `0` or `-1`) and document the convention in the metric's dimensions, or simply not emit a signal point.

Agent/user context (agent-authored — core stores but does not validate or interpret):

- `artifact_id` — which artifact this observation is relevant to. One artifact can have multiple metrics; each metric is a separate stream of signal points. Note: since the filename is already `<artifact_id>.jsonl`, this field is redundant on disk but makes each line self-contained for portability and query.
- `ingested_at` — ISO 8601 timestamp of when AMD recorded the point. May differ from `observed_at` for delayed imports, batch ingestion, or external data sources. Stored for audit, not used for freshness.
- `unit` — optional string describing the unit of measurement (e.g. `ms`, `%`, `count`, `usd`, `score`). Informational; AMD does not perform unit conversion. Agents use it for display and interpretation.
- `source` — optional string identifying where the observation came from. Free-form. Examples: `prometheus`, `manual`, `github_api`, `market_feed`, `survey_system`, `ci_pipeline`. Useful for provenance and debugging when multiple systems feed the same metric.
- `dimensions` — optional key-value map (string keys, string values) of labels or tags on the signal. Used to distinguish sub-streams within a metric or to carry additional context. Examples: `{"region": "us-east", "service": "payments"}`, `{"paper_id": "arxiv:2301.01234"}`, `{"competitor": "acme_corp"}`. AMD does not enforce dimension keys; they are domain-specific.
- any additional fields the agent or ingestion system wants to include

##### Design rules

1. Freshness and cadence anchor to `observed_at`, never `ingested_at`. A batch import of week-old data should not make an artifact look freshly signaled.
2. One signal point per observation. For batch ingestion, emit one `SignalPoint` per data point.
3. Signal points are append-only. Once written to JSONL, they are never modified or deleted during normal operation.
4. Signals are general-purpose. AMD does not assume what kind of data a signal represents. The meaning of a metric is determined by the artifact's domain and the agent interpreting it, not by AMD core.
5. Thresholds and expected cadence are not stored in `SignalPoint`. They are configured in the artifact's config/ file or frontmatter policy and evaluated at rollup/refresh time.

#### `SignalRollup`

Derived windowed summary for one metric, stored in SQLite. Computed incrementally from raw `SignalPoint` records on `amd refresh`. Rebuildable from JSONL if the index is deleted.

Unlike `SignalPoint` and `JournalRecord`, rollups are entirely core-owned. Core computes them, core defines the shape, agents only read them. There is no agent/user context layer here — the rollup is a fixed computation output.

Fields:

- `artifact_id` — which artifact.
- `metric` — which metric stream (matches `SignalPoint.metric`).
- `window` — the rollup window as a duration string: one of the configured windows (default: `15m`, `1h`, `6h`, `24h`, `7d`). Each window produces a separate rollup row.
- `window_end_at` — ISO 8601 timestamp marking the end of this window. The window covers `[window_end_at - window_duration, window_end_at]`.
- `count` — integer. Number of signal points that fell within this window. Zero means no data arrived (relevant for silence detection).
- `min` — float. Minimum value observed in the window.
- `max` — float. Maximum value observed in the window.
- `mean` — float. Arithmetic mean of values in the window.
- `latest_observed_at` — ISO 8601 timestamp. The `observed_at` of the most recent signal point in the window. Used for silence detection: `now - latest_observed_at > expected_cadence * silence_multiplier`.
- `latest_value` — float. The value of the most recent signal point in the window.
- `slope` — float. Linear trend over the window, expressed as value change per hour. Computed by simple linear regression over the signal points in the window. Positive means increasing, negative means decreasing, near-zero means flat. When `count < 2`, slope is `null` (not enough points for a trend).
- `cadence_health` — float, range `0.0` to `1.0`. Ratio of actual observation count to expected observation count in the window, based on `expected_cadence` from artifact policy. `1.0` means data is arriving at exactly the expected rate. Below `1.0` means data is arriving less frequently than expected. When no `expected_cadence` is configured for this metric, `cadence_health` is `null`.
- `source_offset` — integer. Byte offset into the `.amd/signals/<artifact_id>.jsonl` file marking the last raw point that was consumed for this rollup. On the next incremental refresh, AMD reads from this offset forward instead of rescanning the entire file.

##### Design rules

1. Rollups are derived state, not source of truth. They live only in SQLite and are rebuildable from the raw JSONL files. Deleting `index.sqlite` and running `amd reindex` must reproduce identical rollups.
2. Rollup computation is incremental. On refresh, AMD reads only new signal points (from `source_offset` forward), updates affected windows, and writes the new offset. This keeps refresh fast even with large signal histories.
3. One row per `(artifact_id, metric, window)` combination. The rollup table is a current-state summary, not a history of past windows.
4. `slope` and `cadence_health` are nullable. When there is insufficient data (fewer than 2 points for slope, no configured cadence for health), these fields are `null` rather than zero. Agents must handle null.
5. Threshold evaluation happens against rollup values, not raw points. Breach detection compares `latest_value` (or `mean`, depending on threshold config) against configured thresholds during `amd refresh`.
6. Rollup windows are hardcoded in AMD core: `15m`, `1h`, `6h`, `24h`, `7d`. All windows are computed for every metric. If a future version needs project-level tuning, a config surface can be added then.

#### `ArtifactTemporalState`

Current temporal summary for one artifact. Stored fields live in the `artifact_temporal` SQLite table. Computed fields are evaluated at query time using `unixepoch('now')` — see the context-graph-architecture plan for the write-time vs query-time split.

Stored fields (written on refresh):

- `artifact_id`
- `first_seen_at`
- `last_changed_at`
- `last_observed_at`
- `last_reviewed_at`
- `last_signal_at`
- `freshness_class` — resolved via 3-layer precedence (hardcoded -> config/ -> frontmatter)
- `stale_after_seconds` — resolved via 3-layer precedence (hardcoded -> config/ -> frontmatter)
- `refresh_mode` — resolved via 3-layer precedence (hardcoded -> config/ -> frontmatter) (`auto`, `manual`, `frozen`, `live`)
- `freshness_anchor_at` — `max(last_changed_at, last_reviewed_at)`
- `stale_state` — the stale state as of the last refresh: `fresh`, `aging`, or `stale`. Stored so that refresh can detect transitions and emit `stale_entered` / `stale_cleared` activity records. Between refreshes, the query-time computation may differ from this stored snapshot.
- `active_caveat_count`
- `signal_breach_count`
- `signal_silence_count`
- `derivation_drift_count`

Computed fields (evaluated at query time):

- `staleness_ratio` — `(now - freshness_anchor_at) / stale_after_seconds`
- `stale_state` — `fresh` (< 0.5), `aging` (0.5–1.0), `stale` (> 1.0)
- `priority_score` — composite formula from staleness_ratio + count penalties
- `priority_reasons` — structured breakdown of score components

#### `SectionTemporalState`

Current temporal summary for one section. Same stored/computed split as artifact level.

Stored fields:

- `section_id`
- `artifact_id`
- `last_changed_at`
- `last_observed_at`
- `last_reviewed_at`
- `freshness_anchor_at`
- `active_caveat_count`

Computed fields:

- `staleness_ratio` — uses parent artifact's `stale_after_seconds`
- `stale_state`

### 4. The clocks AMD should track

This is the most important design detail. One timestamp is not enough.

#### `last_changed_at`

Set when a section or artifact fingerprint materially changes on `amd refresh`.

Answers:

- when did the prose itself change

#### `last_observed_at`

Set when AMD most recently parsed and indexed the artifact or section, even if nothing changed.

Answers:

- when did AMD last look at this

Important rule:

- `last_observed_at` must **not** reset freshness by itself

Otherwise a nightly refresh would make old, unreviewed docs look current.

#### `last_reviewed_at`

Set only by an explicit review action.

Answers:

- when did a human or agent say “this is still accurate”

Important rule:

- editing does not automatically imply review
- freshness should anchor to `max(last_changed_at, last_reviewed_at)`

That lets active docs stay fresh through edits, while still preserving the difference between “modified” and “confirmed”.

#### `last_signal_at`

The most recent `observed_at` across relevant signal points.

Answers:

- when did reality last speak to this artifact

#### `first_seen_at`

Set when AMD first claims or indexes the artifact.

Answers:

- how long has this thing existed in AMD

### 5. Freshness model

Freshness should remain policy-driven and artifact-class-based, but the computation needs to be more explicit.

#### Freshness classes

Keep the v2 classes:

- `observational`
- `tactical`
- `foundational`
- `archival`

Resolved precedence (must match the config plan's resolution order):

1. AMD universal hardcoded defaults — always available
2. `.amd/config/<artifact_id>.yml` — per-artifact policy
3. Artifact frontmatter `amd.policy` — rare local one-off overrides

Later layers override earlier ones. This is the same 3-layer resolution model used for all config values across v2. See the per-artifact-config plan for full resolution semantics including null handling.

#### Freshness anchor

For content freshness:

```text
freshness_anchor_at = max(last_changed_at, last_reviewed_at)
```

For signal-backed artifacts, content freshness is only one part of the picture. Signal cadence and threshold state modify urgency, but they do not replace the content anchor.

#### Staleness ratio

```text
staleness_ratio = (now - freshness_anchor_at) / stale_after
```

Interpretation:

- `< 0.5` = fresh
- `0.5 - 1.0` = aging
- `> 1.0` = stale

The exact cut points are configurable, but the important part is the ratio, not only the raw timestamp. This is consistent with age-of-information thinking, where “freshness” is a function of both elapsed time and how costly stale information is for the use case.[8]

#### Refresh modes

`refresh_mode` is resolved via the same 3-layer precedence as other temporal policy (hardcoded -> config/ -> frontmatter). It controls which refresh steps apply to an artifact. The refresh algorithm consults it after resolution (step 6) and gates subsequent per-artifact steps accordingly.

- `auto` (default)
  - all refresh steps apply normally: fingerprint comparison, temporal clock updates, stale transition detection, signal rollup processing, caveat lifecycle, derivation drift detection
- `manual`
  - parsing and fingerprinting still run (AMD needs current section IDs and fingerprints for graph integrity)
  - `last_observed_at` is updated
  - temporal recomputation is **skipped**: no stale transition detection, no signal threshold evaluation, no caveat expiry processing, no derivation drift detection
  - the artifact's temporal state remains frozen at its last `auto` or forced-refresh values
  - an explicit `amd refresh --force <artifact_id>` overrides this and runs the full recomputation for that artifact
- `frozen`
  - same as `manual`, plus: `freshness_anchor_at` is never updated, even on content change. The artifact never transitions to `stale` via normal refresh. It remains at whatever stale_state it had when frozen.
  - `last_changed_at` and `last_observed_at` are still updated (for history accuracy), but they do not feed into staleness computation
  - signals are still ingested (data arrives independently), but threshold evaluation is skipped
  - useful for archived-but-referenced documents, stable specs, or intentionally pinned artifacts
- `live`
  - content-based staleness is disabled: `staleness_ratio` is always `0.0` regardless of elapsed time
  - signal/cadence state dominates: signal rollups, breach detection, and silence detection run normally
  - stale transitions (`stale_entered` / `stale_cleared`) are never emitted
  - useful for generated projections, dashboards, or artifacts whose freshness is entirely signal-driven

### 6. Signals and timeseries

AMD should be timeseries-informed, not a general TSDB.

That implies:

- keep append-only JSONL for low-to-medium volume streams
- use incremental rollups in SQLite
- for truly heavy feeds, ingest summarized points or external references instead of the full firehose

This keeps the local CLI model workable while preserving the high-value temporal behavior from reports and incidents.[1][6]

#### Storage model

Raw:

```text
.amd/signals/<artifact_id>.jsonl
```

Derived:

```text
.amd/cache/index.sqlite
```

#### Rollup windows

Use the existing v2 defaults:

- `15m`
- `1h`
- `6h`
- `24h`
- `7d`

#### Incremental processing

On refresh:

1. read the last checkpoint offset for each signal file
2. read only new lines
3. update affected windows
4. write updated rollups and the new checkpoint

This follows the same operational idea as continuous aggregates, but in a lightweight local form rather than a dedicated database product.[6]

The SQLite index should run in WAL mode so `refresh`, `signal`, and read-heavy commands such as `prime` and `agenda` can coexist without unnecessary contention.[9]

#### Silence detection

Signal silence should be explicit.

For each metric with `expected_cadence`:

```text
signal_silent = now - latest_observed_at > expected_cadence * silence_multiplier
```

Recommended default:

- `silence_multiplier = 6`

This is the AMD analog of “absence over time”, which is often more operationally meaningful than one bad value.[7]

#### Threshold state

Threshold breaches should be modeled as state transitions, not just instantaneous numbers:

- `signal_breach_entered`
- `signal_breach_cleared`

That gives `amd history` a real timeline instead of forcing agents to reconstruct it from raw points.

### 7. Caveats and temporal state

Caveats are temporal by definition. They should participate in the same model, not live beside it.

Important rules:

- caveats have lifecycle timestamps
- caveats can scope to artifacts, sections, or directives
- expired caveats should transition automatically on refresh
- active caveats increase urgency, but do not by themselves reset freshness

This matters for incident and log-report workflows because the operational question is often not “how old is this report” but “how old is it relative to unresolved caveats”.

### 8. Priority as temporal synthesis

Priority is where temporal facts become triage signals.

Recommended shape:

```text
priority_score =
    manual_baseline
  + freshness_penalty
  + caveat_penalty
  + signal_penalty
  + derivation_drift_penalty
```

Use higher score = more urgent.

Important refinement:

- keep the individual reasons as structured data
- never return only the scalar

Agents need:

- `score`
- `reasons`
- `stalest_section`
- `active_caveats`
- `signal_breaches`
- `signal_silence`

That is what makes `amd prime` and `amd agenda` explainable instead of opaque.

### 9. What `amd refresh` should actually do

`amd refresh` is the temporal recomputation boundary. It should:

1. scan configured Markdown roots for current files
2. compare known artifact paths against found files; for each known artifact whose file no longer exists, transition to `archived` and run archival cascade (see `artifact_archived` activity type and cascade rules above)
3. parse changed Markdown files
4. detect re-appeared files: if a file contains an `amd.id` matching an archived artifact, transition that artifact back to `active`
5. resolve section identity and fingerprints
6. resolve temporal policy for each artifact using the 3-layer resolution chain: start with AMD hardcoded defaults, apply per-artifact policy from `.amd/config/<artifact_id>.yml`, apply frontmatter `amd.policy` overrides. Write the resolved `freshness_class`, `stale_after_seconds`, and `refresh_mode` into `artifact_temporal` in SQLite.
7. update `last_observed_at` for touched artifacts and sections (all modes)
8. set `last_changed_at` where fingerprints changed (all modes — needed for history accuracy)
9. **gate on refresh_mode**: for each artifact, check the resolved `refresh_mode`. Steps 10–14 apply only to `auto` and `live` mode artifacts (plus `manual` artifacts targeted by `--force`). `frozen` and unforced `manual` artifacts skip steps 10–14 entirely. `live` artifacts skip steps 12–13 (content-based staleness) but run steps 10–11 (signals and caveats).
10. process new signal points from checkpoints (skip archived artifacts; skip `frozen` and unforced `manual`)
11. evaluate signal thresholds from resolved config against rollup values — detect breach enter/clear and silence enter/clear (skip `frozen` and unforced `manual`)
12. recompute caveat lifecycle state (skip `frozen` and unforced `manual`)
13. recompute `freshness_anchor_at` as `max(last_changed_at, last_reviewed_at)` (skip archived, `frozen`, and `live`)
14. detect stale state transitions: compute current `staleness_ratio` using `unixepoch('now')`, derive `stale_state`, compare against the stored `stale_state` from the previous refresh. If the state crossed the threshold in either direction, emit `stale_entered` or `stale_cleared` and update the stored `stale_state`. (Skip `frozen`, `live`, and unforced `manual`.)
15. read derive contracts from resolved config — detect derivation drift from upstream artifacts (skip `frozen` and unforced `manual`)
16. append only **material** temporal activities

Note: `staleness_ratio` and `priority_score` are ephemeral query-time values computed using `unixepoch('now')` in SQL — they are NOT stored. However, `stale_state` IS stored as a snapshot so that refresh can detect transitions and emit `stale_entered` / `stale_cleared` journal records. Between refreshes, the live query-time `stale_state` may differ from the stored snapshot. See the context-graph-architecture plan for the full write-time vs query-time computation split.

Important rule:

- do not append one per-artifact `refreshed` event for every unchanged file every run

Instead:

- write one `refresh_run` activity for the refresh operation itself
- write per-entity activities only for material transitions:
  - artifact archived or re-claimed
  - content changed (`content_changed`)
  - stale state crossed threshold (`stale_entered` / `stale_cleared`)
  - caveat expired or mitigated (`caveat_expired` / `caveat_mitigated`)
  - signal breach entered or cleared (`signal_breach_entered` / `signal_breach_cleared`)
  - signal silence entered or cleared (`signal_silence_entered` / `signal_silence_cleared`)
  - derivation drift entered or cleared (`derivation_drift_entered` / `derivation_drift_cleared`)

That keeps history useful instead of noisy.

### 10. Commands AMD should expose

#### `amd review`

Records that an artifact or section was verified without necessarily editing it.

```bash
amd review artifact:runbook.payments
amd review artifact:runbook.payments --section section:api-endpoints
```

Effects:

- updates `last_reviewed_at`
- appends `review_recorded`
- does not modify Markdown
- does not clear caveats automatically

#### `amd history`

Returns the temporal timeline for an artifact or section.

```bash
amd history artifact:report.payments.incident-2026-03-11 --format json
amd history section:report.payments.incident-2026-03-11:risk-assessment --since 7d
```

Returns:

- activity timeline
- caveat lifecycle events
- signal transitions and recent rollups
- freshness state transitions
- derivation drift transitions

`amd history` is the missing operator for “what happened to this document over time” without reopening Git and multiple journals separately.

#### Existing commands that should surface temporal state

- `amd prime`
  - freshness summary
  - priority reasons
  - active caveats
  - recent signal trends
  - recent transitions
- `amd agenda`
  - priority-ranked queue with temporal reasons
- `amd query --stale`
  - artifacts or sections past threshold
- `amd scan`
  - compact health/status overview

### 11. Agent layer

Temporal judgment belongs in the agent layer, not AMD core.

#### What agents should use this layer for

1. **Choosing attention**
   - use `amd agenda` and `amd prime` to find stale or drifting artifacts first

2. **Understanding recency**
   - use `amd history` before editing incident reports, runbooks, or investigative docs

3. **Confirming without editing**
   - call `amd review` when the agent has actually checked a doc and found it still correct

4. **Interpreting signal-backed docs**
   - treat threshold breaches and signal silence as routing signals, not automatic edit commands

5. **Avoiding false freshness**
   - never treat recent `last_observed_at` as evidence of correctness

#### What agents should actively do

1. **Infer temporal policy at artifact creation**
   - when a user creates a new Markdown artifact, the agent should classify how fast it will decay and set or suggest the right temporal policy
   - examples:
     - daily report, status note, incident log -> `freshness_class: observational`
     - active implementation plan, investigation, runbook draft -> `freshness_class: tactical`
     - architecture note, decision record -> `freshness_class: foundational`
   - when the artifact has an obvious cadence, the agent should also suggest or set:
     - `stale_after`
     - `expected_cadence` for relevant signals
   - the agent should prefer the defaults already in `.amd/config/<artifact_id>.yml` (seeded from hardcoded defaults at init time), and only add frontmatter overrides when the artifact is unusually time-sensitive or unusually stable

2. **Use temporal data to choose review versus edit**
   - if an artifact is stale but no contradictory signals or caveats exist, the agent should consider a review pass before assuming a rewrite is needed
   - if the artifact is stale and there are active caveats, signal breaches, or derivation drift, the agent should lean toward a content update or escalation instead of a no-op review

3. **Use Git to inspect actual prose deltas**
   - AMD tells the agent *that* something changed, *when* it changed, and *which section* changed
   - when the exact textual delta matters, the agent should use Git history and diff to inspect the real prose change
   - practical rule:
     - use `amd history` or `last_changed_at` to localize the time window
     - then use Git log/diff to inspect what changed in the source file
   - this keeps responsibilities clean:
     - AMD = temporal routing and state
     - Git = canonical textual diff

4. **Treat silence differently from contradiction**
   - signal silence means “the expected observation stream is missing”
   - signal breach means “observations disagree with thresholds”
   - these should trigger different agent behavior:
     - silence -> investigate data source / freshness of monitoring path
     - breach -> inspect whether the document’s claims or caveats need updating

5. **Use temporal state to rank propagation work**
   - when a directive/assertion needs propagation, the agent should prefer updating:
     - high-priority stale artifacts first
     - artifacts with active caveats first
     - downstream derived artifacts with drift before unrelated fresh docs

6. **Record review only after actual verification**
   - `amd review` should be called only after the agent has actually read the relevant section or artifact and judged it still correct
   - it should not be used as a cheap freshness reset

7. **Re-rank temporal urgency by current task relevance**
   - AMD can rank artifacts by temporal urgency
   - the agent should re-rank them by current-task relevance
   - practical rule:
     - stale and relevant -> pull forward
     - fresh but caveated and relevant -> still read
     - stale but irrelevant -> defer
   - AMD cannot know the current user task; the agent can

8. **Detect signal-prose gaps**
   - AMD core can detect threshold breaches and signal silence
   - the agent should compare those signal states against actual prose claims in the document
   - if a document claims something materially contradicted by current signals, the agent should:
     - flag the discrepancy
     - consider adding a caveat
     - propose or apply a targeted content update
     - check whether the same claim appears in related artifacts

9. **Respond to derivation drift with diagnosis, not blind re-derive**
   - when AMD reports derivation drift, the agent should inspect:
     - which source section changed
     - whether that section is part of the derivation mapping
     - whether the Git diff shows a substantive or cosmetic change
   - response options:
     - substantive upstream change -> re-derive or manually update downstream
     - cosmetic upstream change -> review downstream and confirm if still valid
     - unclear impact -> review both source and target before acting

10. **Narrate temporal state for the user**
   - when the user asks what has been happening with an artifact or domain, the agent should turn `amd history`, caveats, and signal state into a concise narrative
   - the output should answer:
     - what changed
     - what is still unresolved
     - what is fresh versus risky to trust
   - this is an agent responsibility; AMD core only provides the timeline data

11. **Lead with trust signals during context delivery**
   - when bootstrapping a task, the agent should not just list related docs
   - it should lead with temporal trust information:
     - which artifacts are stale
     - which have active caveats
     - which show signal-prose gaps
     - which were recently reviewed and are likely safe to trust

#### Example agent instruction fragment

When working with AMD temporal context, the agent should follow this loop:

1. On artifact creation, infer likely freshness class and decay rate from the document’s purpose.
2. Prefer the defaults in `.amd/config/<artifact_id>.yml` (seeded from hardcoded defaults at init time); only add frontmatter temporal overrides when there is a clear reason.
3. Before editing a stale or drifting artifact, call `amd history` and inspect active caveats and signals.
4. If the exact prose delta matters, use Git diff/log around the reported change window to inspect what actually changed.
5. Choose between:
   - `amd review` if the content is still correct
   - content edit + `amd refresh` if the content needs updating
   - caveat/signal follow-up if the issue is uncertainty or monitoring drift rather than prose drift
6. Re-rank AMD urgency by relevance to the current user task before deciding what to read or update first.
7. Never use refresh timestamps alone as evidence of correctness.

#### What agents should not assume

- a recent refresh means a document is accurate
- a recent edit means caveats are resolved
- a signal breach means the document is wrong
- a stale foundational document always needs rewriting right now

AMD computes the facts. The agent decides the action.

### 12. How this ties into the other v2 plans

#### Context graph architecture

- journals and signals are the raw temporal layer
- SQLite is the derived temporal state layer
- exported manifests may include lightweight temporal summaries, but not full history

#### Markdown parsing and section identity

- section fingerprints are what make `last_changed_at` meaningful
- stable section IDs are what make per-section history durable

#### Changes propagation

- directive propagation should append `directive_propagated`
- propagation targets can be ranked by freshness and caveats
- after a real verification pass, agents can record `amd review`

This means the temporal plan is not a side feature. It is the layer that turns the graph from static structure into living context.

## Areas Of Consensus

- raw signals and activity history should be append-only
- the index should hold derived temporal state, not the source of truth
- freshness is more than file mtime or last edit time
- signal cadence matters, especially for operational reports
- agents need explainable urgency, not a black-box priority number

## Areas Of Debate

- whether `manual` refresh mode should freeze decay entirely or only suppress automatic recomputation
- whether editing a section should optionally also record review when done through certain commands
- how much temporal summary should be exported in `amd.xref.json` versus kept only in CLI JSON
- whether extremely high-volume signal streams should stay in JSONL or require an explicit “external metric source” mode
- how far v2 should go on proactive temporal maintenance, such as reclassification suggestions or “will go stale soon” forecasts

## Recommendation

Implement the temporal layer as:

1. append-only activity journals plus signal JSONL
2. explicit temporal clocks in SQLite
3. `amd review` and `amd history` as first-class commands
4. cadence-aware signal freshness and threshold transitions
5. explainable priority scoring built from freshness, caveats, signals, and derivation drift

That is the strongest fit for AMD’s agent-native Markdown model. It preserves the lightweight CLI architecture, makes incident and report workflows genuinely better, and stays compatible with the other three v2 plans instead of creating a second system.

## Sources

[1] Local v2 use case and skeleton direction on freshness classes, incremental rollups, `prime`, and append-only journals:
- `/Users/avinier/Projects.py/amd/internals/v2/usecase.md`
- `/Users/avinier/Projects.py/amd/internals/v2/skeleton.md`

[2] Local graph architecture and propagation plans:
- `/Users/avinier/Projects.py/amd/internals/v2/plans/context-graph-architecture.md`
- `/Users/avinier/Projects.py/amd/internals/v2/plans/changes-propagation.md`

[3] Local parsing plan for stable section identity and fingerprints:
- `/Users/avinier/Projects.py/amd/internals/v2/plans/markdown-parsing-and-section-identity.md`

[4] Martin Fowler, “Event Sourcing.” Strong reference for append-only fact capture and rebuilding current state from the event log. <https://martinfowler.com/eaaDev/EventSourcing.html>

[5] W3C PROV-DM. Strong reference for separating entities, activities, agents, revision, and derivation in a provenance-aware system. <https://www.w3.org/TR/2013/PR-prov-dm-20130312/>

[6] Tiger Data / Timescale documentation on continuous aggregates. Useful operational reference for incremental rollup thinking; AMD should borrow the pattern, not the full system. <https://www.tigerdata.com/docs/use-timescale/latest/continuous-aggregates/about-continuous-aggregates/>

[7] Prometheus query functions, especially `absent_over_time`. Useful operational reference for modeling silence and missing expected data as first-class signals. <https://prometheus.io/docs/prometheus/latest/querying/functions/#absent_over_time>

[8] Yin Sun et al., “Update or Wait: How to Keep Your Data Fresh.” Primary research grounding for age-of-information and freshness as more than a raw timestamp. <https://arxiv.org/abs/1601.02284>

[9] SQLite Write-Ahead Logging. Useful reference for local concurrency and read/write behavior in the rebuildable index. <https://www.sqlite.org/wal.html>

[10] Quarto freeze modes. Useful product reference for `auto` / `manual` / `freeze` style policy semantics, adapted here for AMD freshness behavior. <https://quarto.org/docs/projects/code-execution.html#freeze>

## Gaps And Further Research

- decide whether `amd history` should optionally include linked Git commits when available
- decide whether `live` refresh mode belongs in v2 or can wait until generated-content workflows need it
- define exact JSON output contracts for `amd history`
- define whether per-section signal attachment is needed in v2 or whether artifact-level signals are enough initially
- decide whether proactive temporal maintenance belongs in v2:
  - impending-staleness predictions
  - review cadence recommendations
  - suggested reclassification from observational/tactical/foundational based on observed behavior
