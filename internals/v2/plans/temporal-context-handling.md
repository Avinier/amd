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

#### `ActivityRecord`

Canonical append-only temporal fact for machine or human actions.

Fields:

- `activity_id`
- `activity_type`
- `target_entity_type` (`artifact`, `section`, `directive`)
- `target_entity_id`
- `artifact_id`
- `section_ids` nullable
- `occurred_at`
- `recorded_at`
- `actor`
- `summary`
- `detail_json`

Recommended `activity_type` values:

- `artifact.created`
- `content.changed`
- `review.recorded`
- `caveat.added`
- `caveat.mitigated`
- `caveat.expired`
- `signal.ingested`
- `signal.breach.entered`
- `signal.breach.cleared`
- `signal.silence.entered`
- `signal.silence.cleared`
- `derivation.updated`
- `derivation.drift.entered`
- `derivation.drift.cleared`
- `directive.propagated`
- `refresh.run`

Rule:

- keep `occurred_at` separate from `recorded_at`
- external signals and delayed imports can arrive late; AMD should preserve source time

#### `SignalPoint`

Canonical raw numeric observation for a metric.

Fields:

- `artifact_id`
- `metric`
- `observed_at`
- `ingested_at`
- `value`
- `unit`
- `source`
- `dimensions_json` optional

Rule:

- freshness and cadence should anchor to `observed_at`, not `ingested_at`

#### `SignalRollup`

Derived windowed summary stored in SQLite.

Fields:

- `artifact_id`
- `metric`
- `window`
- `window_end_at`
- `count`
- `min`
- `max`
- `mean`
- `latest_observed_at`
- `latest_value`
- `slope`
- `cadence_health`
- `source_offset`

#### `ArtifactTemporalState`

Current temporal summary for one artifact.

Fields:

- `artifact_id`
- `first_seen_at`
- `last_changed_at`
- `last_observed_at`
- `last_reviewed_at`
- `last_signal_at`
- `freshness_class`
- `stale_after`
- `freshness_anchor_at`
- `staleness_ratio`
- `stale_state` (`fresh`, `aging`, `stale`, `archival`)
- `active_caveat_count`
- `signal_breach_count`
- `signal_silence_count`
- `derivation_drift_count`
- `priority_score`
- `priority_reason_json`

#### `SectionTemporalState`

Current temporal summary for one section.

Fields:

- `section_id`
- `artifact_id`
- `last_changed_at`
- `last_observed_at`
- `last_reviewed_at`
- `freshness_anchor_at`
- `staleness_ratio`
- `stale_state`
- `active_caveat_count`

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

Resolved precedence:

1. artifact frontmatter override
2. schema policy
3. project config

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

Keep the existing mode idea, but interpret it as freshness-policy behavior:

- `auto`
  - normal recomputation on refresh
- `manual`
  - state remains queryable but AMD only re-evaluates freshness when forced
- `frozen`
  - no decay, no stale transitions, still visible in history
- `live`
  - intended for generated or continuously updated projections; stale thresholds are effectively disabled and signal/cadence state dominates

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

- `breach.entered`
- `breach.cleared`

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

1. parse changed Markdown files
2. resolve section identity and fingerprints
3. update `last_observed_at` for touched artifacts and sections
4. set `last_changed_at` where fingerprints changed
5. process new signal points from checkpoints
6. recompute caveat lifecycle state
7. recompute freshness ratios and stale states
8. recompute derivation drift from upstream artifacts
9. recompute priority scores and reasons
10. append only **material** temporal activities

Important rule:

- do not append one per-artifact `refreshed` event for every unchanged file every run

Instead:

- write one `refresh.run` activity for the refresh operation itself
- write per-entity activities only for material transitions:
  - content changed
  - stale state changed
  - caveat expired or mitigated
  - signal breach entered or cleared
  - signal silence entered or cleared
  - derivation drift entered or cleared

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
- appends `review.recorded`
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
     - architecture note, mental model, decision record -> `freshness_class: foundational`
   - when the artifact has an obvious cadence, the agent should also suggest or set:
     - `stale_after`
     - `expected_cadence` for relevant signals
   - the agent should prefer schema/config defaults when they fit, and only introduce artifact-level overrides when the artifact is unusually time-sensitive or unusually stable

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
2. Prefer schema/project defaults when they fit; only add artifact-level temporal overrides when there is a clear reason.
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

- directive propagation should append `directive.propagated`
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
