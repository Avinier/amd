AMD v2 Developer Use Case Flow

  Foundational Constraints

  AMD is an agent-native CLI. The primary consumers are AI agents (Claude Code, Codex, etc.) that invoke AMD commands at machine speed and volume —
  creating artifacts, recording events, querying the graph, deriving new documents, and breaking/rebuilding structure dynamically as understanding evolves.

  .amd/ is metadata only: identity records, relation edges, temporal data (journals, signals), and context metadata. Zero document content.
  The user's Markdown files live wherever they want. .amd/ only knows about them.

  ---
  The Scenario

  A developer is onboarding to a payments service, investigates an incident, builds knowledge, and that knowledge flows downstream to other agents and
  teammates.

  ---
  1. Project Bootstrap

  amd init --project

  Creates .amd/config.yml with project defaults (freshness classes, stale thresholds, rollup windows). Developer drops schema files into .amd/schemas/ — e.g.
   report.incident.yml, mental_model.yml. This is a one-time setup.

  ---
  2. Create a Mental Model (Deep Learning Phase)

  amd init --kind mental_model artifacts/mental_model.payments.authorization.md

  Schema selects the template, injects required sections (decision-rules, failure-modes, integration-points), sets policy (freshness_class: foundational,
  stale_after: 168h). The developer gets a clean .md file with YAML frontmatter — no JSON blob, no HTML comments — and writes prose in user-owned sections.

  ---
  3. Incident Hits — Create an Incident Report

  amd init --kind report.incident artifacts/report.payments.incident-2026-03-11.md

  Schema enforces executive-summary, current-context, risk-assessment, caveats. Policy auto-sets freshness_class: observational, stale_after: 4h — this doc
  decays fast.

  ---
  4. Record Events and Caveats (Machine Writes)

  amd event --artifact report.payments.incident-2026-03-11 \
    --agent codex --activity investigate \
    --summary "Root cause identified: race condition in auth token refresh"

  amd caveat --artifact report.payments.incident-2026-03-11 \
    --severity high \
    --text "Fix deployed but not yet verified under load" \
    --expires-in 24h

  These write to append-only JSONL journals (.amd/journal/events/, .amd/journal/caveats/). The Markdown file is never touched. No write contention, no file
  clobber.

  ---
  5. Ingest Signals (Metrics)

  amd signal --artifact report.payments.incident-2026-03-11 \
    --metric error_rate --value 0.02

  Appends to .amd/signals/report.payments.incident-2026-03-11.jsonl. Index computes incremental rollups (15m, 1h, 6h, 24h windows) without rescanning the
  full file.

  ---
  6. Refresh the Index (No File Rewrite)

  amd refresh

  This is the key behavioral change from v1. Refresh now:
  - Parses Markdown to AST
  - Resolves stable section IDs (labels survive heading renames)
  - Computes structural fingerprints (whitespace changes don't trigger false drift)
  - Updates freshness scores, priority, signal rollups in SQLite
  - Does NOT rewrite the Markdown body

  The .md file stays exactly as the developer wrote it.

  ---
  7. Derive a Skill Artifact (Knowledge Flows Downstream)

  amd derive --source mental_model.payments.authorization \
    --target skill.payments.oncall

  Declared transform in the schema pulls labeled sections (decision-rules, failure-modes) from the mental model, restructures them into an oncall runbook.
  Output sections are marked generated (machine-owned). User-owned sections in the target are never touched.

  Every derivation writes a provenance record to .amd/journal/derivations/ — you can trace exactly which source sections fed the skill, which agent ran the
  derive, and when.

  ---
  8. Materialize (Optional: Render Projections into Markdown)

  amd materialize artifacts/report.payments.incident-2026-03-11.md

  This is the only command that writes back into Markdown, and only into clearly delimited generated blocks:

  <!-- amd:generated:start timeline-summary -->
  **Recent Events:**
  - 2026-03-11T12:00Z [codex/investigate] Root cause identified...
  <!-- amd:generated:end -->

  <!-- amd:generated:start caveats-summary -->
  **Active Caveats (1):**
  - HIGH: Fix deployed but not yet verified under load (expires 2026-03-12)
  <!-- amd:generated:end -->

  Human prose is untouched. Generated blocks are clearly fenced.

  ---
  9. Agent Consumption (The Payoff)

  amd prime --limit 5 --format json

  An AI agent (Claude, Codex) calls prime and gets a structured context pack:
  - Top 5 highest-priority artifacts, ranked by the computed priority formula
  - Only relevant sections (not entire files)
  - Active caveats surfaced first
  - Freshness annotations ("this report is 2h old, observational class, stale in 2h")
  - Recent derivation changes
  - Recent signal trends

  The agent doesn't read raw files — it consumes pre-ranked, pre-filtered context.

  ---
  10. Query and Triage

  amd agenda          # Priority-ranked work queue
  amd scan            # Quick status overview (reads from index, not files)
  amd doctor          # Validate schemas, labels, journal integrity
  amd query --stale   # Find everything past its freshness threshold

  All read from SQLite. No file reparsing.

  ---
  The Flow Visualized

  Developer writes prose          Agents write events/caveats/signals
          │                                    │
          ▼                                    ▼
     .md files (user-owned)          .amd/journal/ (append-only JSONL)
          │                          .amd/signals/ (append-only JSONL)
          │                                    │
          └──────────┬─────────────────────────┘
                     ▼
              amd refresh
                     │
                     ▼
          .amd/cache/index.sqlite (rebuildable cache)
                     │
          ┌──────────┼──────────────┐
          ▼          ▼              ▼
     amd prime   amd scan      amd agenda
     (agents)    (humans)      (triage)
                     │
                     ▼
            amd materialize (optional)
                     │
                     ▼
            Generated blocks in .md
            (clearly fenced, machine-owned)

  ---
  Why This Flow Works

  1. Files are just Markdown — render anywhere, edit in any editor, no tooling lock-in
  2. Machine state never corrupts human prose — journals are separate, projections are fenced
  3. Concurrent agents don't clobber — append-only journals + lock-based writes
  4. False drift eliminated — AST-aware fingerprinting ignores whitespace/reflow
  5. Knowledge flows are traceable — every derivation has provenance edges back to source sections
  6. Agents get pre-ranked context — prime delivers exactly what they need, nothing they don't
 