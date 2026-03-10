# AMD

AMD is a small Python tool for managing adaptive Markdown artifacts for agents. The goal is not just "read and write a `.md` file", but to give each file machine-managed metadata, traceability, freshness signals, caveats, and heavier sidecar data where plain Markdown starts to break down.

## Core model

Each `*.amd.md` file contains:

- A machine-managed JSON metadata block embedded at the top of the Markdown file.
- A human-readable body with templates for task context, reports, mental models, and derived skill docs.
- An append-only Markdown timeline for multi-agent traceability.
- Section fingerprints so the tool can detect semantic drift across large evolving reports.
- Freshness and priority metadata so stale files can be surfaced instead of silently rotting.
- Structured caveats with severity and optional expiry.
- A timeseries sidecar (`.amd/data/<artifact>.jsonl`) for heavier signal history that should not live inline in Markdown.

## Why this covers your needs

- Dynamic evolving md filetype: metadata, fingerprints, freshness, and trace updates are maintained automatically by `amd refresh`, `amd event`, `amd signal`, and `amd caveat`.
- MD timeline trace for one big task and many agents: the `Timeline` section is append-only and every entry records timestamp, agent, and event kind.
- Better templating for agent context: `amd init` supports `task`, `report`, `mental-model`, and `skill-derived` templates.
- Mental model docs derived into skills docs: `amd derive-skill` creates a skill-oriented artifact from a mental model and carries provenance forward.
- Fingerprint scanner for nuanced 500-line reports: section-level hashes let you detect which parts actually changed without encoding the whole nuance into an instruction file.
- Persistent and non-persistent artifacts: every doc carries `persistence.mode` as `persistent` or `ephemeral`.
- Solving stale data: every section carries `updated_at`, stale thresholds, and document-level stale reasons.
- Auto-updating AMD files: `amd refresh-all` updates a tree; `amd watch` runs it continuously on an interval.
- Heavy timeseries data: datapoints go to JSONL sidecars and are summarized back into metadata, not duplicated inline.
- Setting update priority: manual priority is combined with stale sections, active caveats, and newer timeseries signals to compute an update score.
- Caveat rules: caveats are first-class structured objects with severity, creator, creation time, status, and optional expiry.

## CLI

```bash
python3 -m amd init docs/big-task.amd.md --kind task --title "Big Task"
python3 -m amd event docs/big-task.amd.md --agent planner --kind note --summary "split work into streams"
python3 -m amd caveat docs/big-task.amd.md --agent reviewer --severity high --text "benchmark data is from staging"
python3 -m amd signal docs/big-task.amd.md --agent monitor --metric error_rate --value 0.12 --unit ratio
python3 -m amd refresh docs/big-task.amd.md
python3 -m amd scan docs/big-task.amd.md
python3 -m amd init docs/payment-model.amd.md --kind mental-model --title "Payments Mental Model"
python3 -m amd derive-skill docs/payment-model.amd.md docs/payment-skill.amd.md
python3 -m amd watch docs --interval 300
```

## File shape

An AMD file is still ordinary Markdown, but it starts with a machine section:

```md
<!-- amd:meta
{
  "artifact_id": "big-task-1234abcd",
  "freshness": {
    "is_stale": false,
    "observed_at": "2026-03-10T18:00:00Z",
    "stale_after_hours": 24
  },
  "priority": {
    "manual": 50,
    "computed": 65
  }
}
-->
# Big Task
...
```

The Markdown body stays readable and editable by hand. The machine-managed block is what lets agents refresh state without needing another instruction file to encode everything.

## Notes

- The sidecar timeseries store is append-only JSONL. That keeps high-volume temporal data outside the narrative Markdown while still giving the artifact a summarized view.
- `amd refresh` only emits automatic fingerprint events for non-timeline sections, so normal trace updates do not create recursive drift noise.
- `amd watch` is intentionally simple polling. If you want stronger automation later, wire `refresh-all` into cron, launchd, or your own agent loop.
