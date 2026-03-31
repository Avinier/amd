AMD v2 Developer Use Case Flow

  Foundational Constraints

  AMD is an agent-native CLI. Humans never run AMD commands directly. The primary consumers are AI agents (Claude Code, Codex, etc.) that invoke AMD
  commands automatically via Skills and hooks — at machine speed and volume — while the developer works normally in their editor or chat session.

  The two layers:
  - Core layer (AMD CLI): deterministic operations — parse, index, query, record. Never decides what to edit. Never rewrites prose.
  - Skill/agent layer (Claude Code Skills, Codex Skills, hooks): intelligence — recognizes intent, invokes AMD core, filters candidates, makes edits.

  .amd/ is metadata plus lightweight derived context: identity records, relation edges, temporal data (journals, signals), context metadata, rebuildable
  index, exported manifests. Zero document content. The user's Markdown files live wherever they want. .amd/ only knows about them.

  ---
  The Scenario

  A developer is onboarding to a payments service, investigates an incident, builds knowledge, and that knowledge flows downstream to other agents and
  teammates. Throughout all of this, the developer never types a single `amd` command — their agent handles it.

  ---
  1. Project Bootstrap

  The developer runs `amd init --project` once (the only command a human ever runs directly). Creates the `.amd/` directory structure (config/, journal/, signals/, cache/, export/). AMD core hardcodes sensible defaults for freshness, priority, and signal windows. After this, the AMD Skill is loaded into their agent session and hooks are configured — all subsequent AMD usage is agent-driven.

  ---
  2. Building a Mental Model (Developer Learns, Agent Structures)

  The developer tells their agent: "I'm onboarding to the payments authorization flow, help me build a mental model."

  What the developer sees: the agent asks questions, reads code, discusses architecture.

  What happens underneath (Skill layer → Core layer):

    Skill recognizes: user is building foundational knowledge → create a mental_model artifact.

    Agent invokes:
      amd init --kind mental_model artifacts/mental_model.payments.authorization.md

    Core layer: agent seeds the config/ file with required sections (decision-rules, failure-modes, integration-points) and policy
    (freshness_class: foundational, stale_after: 168h). Returns a clean .md file with YAML frontmatter and a matching .amd/config/ entry.

  The developer and agent collaborate to fill in sections. The agent writes prose based on what it learns from code and conversation. The developer edits
  freely in their editor. The .md file is theirs — no JSON blobs, no HTML comments (except optional AMD labels).

  ---
  3. Incident Hits — Agent Creates the Report

  An alert fires. The developer tells their agent: "Payments auth is returning 500s, help me investigate."

  What happens underneath:

    Skill recognizes: this is an active incident → create an incident report artifact.

    Agent invokes:
      amd init --kind report.incident artifacts/report.payments.incident-2026-03-11.md

    Core layer: agent seeds config/ with required_sections (executive-summary, current-context, risk-assessment, caveats) and policy (freshness_class: observational,
    stale_after: 4h) — this doc decays fast.

  The developer doesn't know or care that `amd init` ran. They see a structured report appear and start working the incident.

  ---
  4. Investigation — Agents Record Events Automatically

  The developer and agent dig into logs. The agent finds the root cause.

  What happens underneath:

    The agent (or a parallel Codex session) invokes:
      amd event --artifact report.payments.incident-2026-03-11 \
        --agent codex --activity investigate \
        --summary "Root cause identified: race condition in auth token refresh"

    A fix gets deployed. The agent records the caveat:
      amd caveat --artifact report.payments.incident-2026-03-11 \
        --severity high \
        --text "Fix deployed but not yet verified under load" \
        --expires-in 24h

    Monitoring data flows in:
      amd signal --artifact report.payments.incident-2026-03-11 \
        --metric error_rate --value 0.02

    Core layer: all of this writes to append-only JSONL — .amd/journal/<artifact_id>.jsonl and .amd/signals/<artifact_id>.jsonl. The Markdown file is never
    touched. No write contention, no file clobber — multiple agents can record simultaneously.

  The developer sees none of these commands. They're chatting, reading logs, deploying fixes. The Skill layer handles the bookkeeping.

  ---
  5. User Clarifies Something — Agent Propagates

  During the investigation, the developer says: "btw, the token refresh uses a mutex, not a semaphore — the old docs are wrong."

  What happens underneath:

    Skill recognizes: this is a clarification/directive that may affect existing artifacts.

    Agent invokes:
      amd capture --type directive --directive-type clarification \
        --statement "Token refresh uses mutex, not semaphore"

    Agent invokes:
      amd affected --query "token refresh" --query "semaphore" --query "mutex"

    Core layer returns: 10 candidate sections across 4 artifacts with FTS5-ranked snippets.

    Skill layer (the brain) filters: reads each candidate, decides 3 of 10 actually need updating, skips sections that already say mutex or discuss
    unrelated topics.

    Agent edits the 3 sections with targeted prose changes. Then:
      amd refresh
      amd link directive:token-refresh-mutex --edge reflected_in \
        --targets artifact:mental-model-payments,artifact:oncall-runbook

    Agent tells the developer: "Updated 3 of 10 candidate sections to reflect: token refresh uses mutex."

  The developer said one sentence. The agent handled multi-artifact propagation automatically. AMD core found the candidates; the agent filtered and edited.

  ---
  6. Index Refresh (Hooks, Not Human Action)

  The Skill calls `amd refresh` after edits, or a post-save hook triggers it automatically. The developer never runs this.

  What refresh does (core layer):
  - Parses Markdown to AST
  - Resolves stable section IDs (labels survive heading renames)
  - Computes structural fingerprints (whitespace changes don't trigger false drift)
  - Updates freshness scores, priority, signal rollups in SQLite
  - Does NOT rewrite the Markdown body

  The .md file stays exactly as the developer wrote it.

  ---
  7. Knowledge Flows Downstream (Agent Derives)

  Later, the Skill detects that the mental model has changed significantly since the oncall runbook was last derived.

  Agent invokes:
    amd derive --source mental_model.payments.authorization \
      --target skill.payments.oncall

  Core layer: declared transform in the source artifact's config/ pulls labeled sections (decision-rules, failure-modes) from the mental model, restructures them into the
  oncall runbook. Output sections are marked generated (machine-owned). User-owned sections in the target are never touched.

  Every derivation writes a provenance record (JournalRecord with activity type `derivation_updated`) to .amd/journal/<artifact_id>.jsonl — traceable: which source sections fed the skill, which agent ran the derive,
  and when.

  ---
  8. Materialize (Optional: Render for Human Reading)

  If the developer wants to see the operational state in their Markdown (for a PR, a handoff, a quick glance), the agent runs:

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
  9. Next Agent Session — Instant Context (The Payoff)

  The next morning, the developer starts a new Claude Code session: "What's the status on the payments incident?"

  The Skill fires immediately:

    amd prime --limit 5 --format json

  Core layer returns a structured context pack:
  - Top 5 highest-priority artifacts, ranked by the computed priority formula
  - Only relevant sections (not entire files)
  - Active caveats surfaced first
  - Freshness annotations ("this report is 14h old, observational class, stale for 10h — needs review")
  - Recent derivation changes
  - Recent signal trends (error_rate trending down)

  The agent doesn't read raw files — it consumes pre-ranked, pre-filtered context. It immediately knows: the incident report is stale, there's an
  unverified caveat, error rates are recovering. It briefs the developer with zero ramp-up.

  A different agent (Codex running in CI, a teammate's Claude session) gets the same ranked context. Knowledge built in one session is consumable by any
  agent, any session, instantly.

  ---
  10. Query and Triage (Agent-Driven)

  The Skill uses these throughout the session as needed — the developer never invokes them directly:

  amd agenda          # Priority-ranked work queue — what needs attention?
  amd scan            # Quick status overview (reads from index, not files)
  amd doctor          # Validate required sections, labels, journal integrity
  amd query --stale   # Find everything past its freshness threshold
  amd affected        # FTS5 discovery — what documents touch this topic?

  All read from SQLite. No file reparsing.

  ---
  The Flow Visualized

  Developer chats/codes normally          Skills + hooks fire underneath
          │                                         │
          ▼                                         ▼
  "help me investigate"              Skill: amd init, amd event, amd capture
  "the token uses a mutex"           Skill: amd affected → filter → edit
  "what's the status?"               Skill: amd prime → brief developer
          │                                         │
          ▼                                         ▼
     .md files (user-owned)          .amd/journal/ (append-only JSONL)
          │                          .amd/signals/ (append-only JSONL)
          │                                         │
          └──────────┬──────────────────────────────┘
                     ▼
              amd refresh (hook or Skill-triggered)
                     │
                     ▼
          .amd/cache/index.sqlite (rebuildable cache)
                     │
          ┌──────────┼──────────────┐
          ▼          ▼              ▼
     amd prime   amd scan      amd agenda
     (any agent) (any agent)   (any agent)
                     │
                     ▼
            amd materialize (optional)
                     │
                     ▼
            Generated blocks in .md
            (clearly fenced, machine-owned)

  ---
  The Two Layers Throughout

  In every step above, two things are happening:

  Skill/Agent Layer (the brain):
  - Recognizes developer intent from natural conversation
  - Decides which AMD commands to invoke and when
  - Filters candidates returned by AMD core (10 candidates → 3 real edits)
  - Makes actual prose edits to Markdown files
  - Briefs the developer with relevant context
  - Judges semantic relevance — AMD core cannot do this

  Core Layer (the hands):
  - Deterministic CLI operations: parse, index, record, query
  - Returns structured JSON — never decides what to edit
  - Never rewrites prose — journals are append-only, index is rebuildable
  - FTS5-powered discovery via `amd affected`
  - Graph operations via `amd link`, `amd capture`
  - Temporal state via freshness classes, signal rollups, multi-clock tracking

  The Skill layer is not code in the CLI. It is external prompt/skill definitions that run inside the agent session (Claude Code Skills, Codex Skills,
  hooks). AMD ships these as part of its distribution — they are the agent-facing interface.

  ---
  Why This Flow Works

  1. Zero developer overhead — AMD is invisible; the developer just works with their agent
  2. Files are just Markdown — render anywhere, edit in any editor, no tooling lock-in
  3. Machine state never corrupts human prose — journals are separate, projections are fenced
  4. Concurrent agents don't clobber — append-only journals + lock-based writes
  5. False drift eliminated — AST-aware fingerprinting ignores whitespace/reflow
  6. Knowledge flows are traceable — every derivation has provenance edges back to source sections
  7. Agents get pre-ranked context — prime delivers exactly what they need, nothing they don't
  8. Multi-session, multi-agent — knowledge built in one session is consumable by any agent instantly
  9. Clarifications propagate — one developer sentence updates N artifacts via capture → affected → filter → edit
  10. Core never decides, agent always decides — clean separation means AMD stays deterministic, intelligence stays in the agent
