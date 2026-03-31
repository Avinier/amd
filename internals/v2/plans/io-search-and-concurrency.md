# AMD v2 Plan: I/O, Search, And Concurrency

## Executive Summary

AMD v2 should treat I/O as a first-class subsystem, not a grab bag of file operations.

The right mechanics layer for v2 is:

- **SQLite + FTS5** as the primary structured search and query engine
- **JSONL append-only files** for canonical journal and signal writes
- **cold-build plus warm-incremental refresh** driven by Git when available
- **atomic temp-file writes + rename** for any file rewrite
- **lock files plus SQLite WAL** for concurrent agent safety on one worktree

The most important design split is:

- journals and signals are the **canonical write log**
- SQLite is the **derived read model**
- Markdown is the **canonical prose**

That keeps the system rebuildable, fast for agents, and safe under concurrent Codex/Claude workflows.[1][2][3][4][5][6][7][8][9][10]

## Key Findings

- **FTS5 should be the primary AMD search surface**: it already gives AMD phrase queries, boolean operators, prefix search, BM25 ranking, snippets, and column weighting inside SQLite.[1]
- **v2 should use a normal FTS5 table, not external-content or contentless mode**: external-content tables are easy to make inconsistent, and contentless tables remove capabilities AMD wants for phrase/snippet-heavy agent workflows.[1]
- **The main speed win is warm incremental refresh, not replacing SQLite**: Git's porcelain status output, untracked cache, and FSMonitor let AMD work from changed paths instead of rescanning the full tree every run.[5][6][7]
- **WAL mode is the right SQLite journal mode for AMD's derived index**: readers and writers can proceed concurrently, but AMD still needs to plan for `SQLITE_BUSY`, one-writer-at-a-time behavior, and local-disk-only fast paths.[2][3]
- **One SQLite connection per command is the right Python model**: Python's `sqlite3` module defaults to thread-affine connections, and shared cross-thread connections require user-side serialization anyway.[13]
- **Git-aware discovery should have two modes**: `git ls-files` is the right cold-path enumerator, while `git status --porcelain=v2 -z` is the right warm-path candidate set.[5][6]
- **APSW is the best SQLite binding upgrade, but it is optional**: stdlib `sqlite3` is sufficient for v2, while APSW becomes attractive when AMD wants more direct SQLite feature access and version control over the runtime.[12][13]
- **`ripgrep` should stay supplementary, not primary**: it is excellent for regex and literal raw-file search and respects ignore rules by default, but it does not replace AMD's section-aware, ranked, graph-backed retrieval.[17][18]
- **Every AMD rewrite should be atomic**: write to a temp file in the same directory, flush + fsync, then `os.replace()` into place.[11][19]
- **Lock files should be the cross-process coordination primitive**: `os.open()` exposes `O_CREAT` and `O_EXCL` on Unix and Windows, which is enough for portable lock-file acquisition in a CLI tool.[11]

## Detailed Analysis

### 1. Search architecture

AMD needs four distinct search surfaces:

1. **FTS5** for semantic document search
2. **filesystem discovery** for finding candidate files
3. **graph traversal** for relation-aware expansion
4. **ripgrep** for raw regex/literal fallback

Each one has a different job. Do not collapse them into one mechanism.

### 2. Primary search: FTS5 inside SQLite

FTS5 should be the default engine behind:

- `amd affected`
- `amd query`
- `amd prime`
- `amd scan`

#### Recommended FTS5 table shape

Use a dedicated FTS5 virtual table such as:

- `artifact_title`
- `section_heading`
- `section_labels`
- `plain_text`

Recommended options:

- `tokenize='unicode61 remove_diacritics 2'`
- `prefix='2 3'`
- `detail=full`
- `columnsize=1`

Why:

- `unicode61` is the default Unicode-aware tokenizer in FTS5.[1]
- prefix indexes support partial-token lookup without a full table scan.[1]
- `detail=full` preserves phrase, snippet, highlight, and column-aware behavior; `detail=column` disables phrase and `NEAR` queries, which is too aggressive for AMD's agent search surface.[1]
- `columnsize=1` keeps BM25 efficient; SQLite documents that turning it off makes token-count retrieval slower.[1]

`porter` should be an **opt-in project choice**, not the v2 default. SQLite documents Porter as a tokenizer wrapper around the default tokenizer, but it is English-oriented. AMD should default to the safer multilingual baseline and allow English-heavy repos to opt into stemming explicitly.[1]

#### Why not external-content FTS5

Do **not** make v2's primary FTS table an external-content table.

SQLite explicitly warns that external-content tables can become inconsistent if the content table and FTS table drift, and the maintenance story depends on triggers or disciplined write ordering.[1] AMD already has enough moving parts. v2 should prefer a simpler model:

- keep normalized plain text in the relational table
- keep a separate FTS5 index table
- update both in the same refresh transaction

That duplicates some derived text, but it keeps the system easier to reason about and recover.

#### Why not contentless FTS5

Do **not** use contentless FTS5 for v2 search.

Contentless mode removes normal column reads and imposes update/delete restrictions.[1] AMD wants:

- snippets
- highlights
- section previews
- cheap query-time joins back to derived section context

That is a bad fit for contentless mode.

#### Optional side index: trigram

If AMD later needs stronger substring-heavy search, it should add a **separate optional trigram FTS5 index**, not replace the main index.

Use cases:

- path-fragment lookup
- symbol-like substrings
- camelCase-ish or mixed-token search
- candidate generation for raw literal follow-up

SQLite documents the trigram tokenizer as a way to support general substring matching and to accelerate `LIKE` and `GLOB` patterns.[1]

The main index should still stay:

- phrase-oriented
- heading/snippet-friendly
- `detail=full`

The trigram index is a sidecar optimization, not the primary v2 search surface.

### 3. Ranking and query semantics

FTS5 BM25 should be AMD's default lexical ranking surface.

Recommended persistent rank mapping:

- `artifact_title`: `8.0`
- `section_heading`: `5.0`
- `section_labels`: `3.0`
- `plain_text`: `1.0`

SQLite documents that FTS5 lets each column receive a different BM25 weight and that ordering by the hidden `rank` column is faster than recomputing `bm25()` directly in `ORDER BY`.[1]

That gives AMD the right bias:

- title hits rank highest
- heading hits next
- labels help routing
- body text still matters, but less

#### Query model

AMD should expose a **safe simplified query language** over FTS5, not blindly pass raw user strings through.

v2 should support:

- bare terms
- quoted phrases
- prefix search on final tokens
- boolean `AND` / `OR` / `NOT`
- optional column filtering internally, not as a public dependency

Internally this still compiles to FTS5 `MATCH` queries.[1]

### 4. `amd affected`: FTS first, graph second

`amd affected` should work in two phases:

1. **Seed retrieval**
   - run an FTS5 query over section/title text
   - return the top direct lexical hits

2. **Relation expansion**
   - use recursive CTE traversal over graph edges
   - walk only followable edge types
   - apply a depth limit
   - penalize expansion distance compared with direct lexical hits

Recommended followable edge set:

- `derived_from`
- `references`
- `applies_to`
- `reflected_in`
- `supersedes`
- `revision_of`
- `alternate_of`
- `relates_to`

Recommended defaults:

- max traversal depth: `2`
- direct lexical hits always outrank graph-only expansions
- `contains` is never a traversal edge for propagation search

This keeps `amd affected` targeted instead of turning it into "walk the entire graph because one section matched."

### 5. Supplementary raw search: `ripgrep`

`ripgrep` remains valuable, but it should be a **supplementary** search surface.

Use cases:

- literal or regex search over raw Markdown
- code-fence content that FTS tokenization may flatten awkwardly
- index-absent or index-corrupt fallback
- agent debugging and one-off investigations

The ripgrep docs emphasize that `rg` is a recursive, line-oriented search tool that respects `.gitignore` rules and skips hidden/binary files by default.[17] It also supports additional glob filtering and machine-readable JSON output.[18][20]

#### Core recommendation

AMD core should **not** wrap `ripgrep` for normal semantic commands.

Instead:

- AMD semantic commands use SQLite + FTS5
- agents may use `rg` directly for regex/literal raw-file search
- AMD may add a future fallback/debug path that shells out to `rg --json`, but that is not the primary v2 search contract

This avoids turning AMD into a grep wrapper.

### 6. Refresh modes and filesystem discovery

AMD refresh should have two execution modes:

#### Cold build / rebuild

Use:

- `git ls-files -z --cached --others --exclude-standard --full-name --deduplicate`

Then filter to AMD's include roots, exclude roots, and Markdown suffixes.

This is the right full enumeration path because it is:

- NUL-safe
- repo-root-relative
- aware of tracked and untracked files
- aligned with Git's ignore model[5]

#### Warm incremental refresh

Use:

- `git --no-optional-locks status --porcelain=v2 -z`

Then treat only those reported paths as the candidate set for:

- modified files
- deleted files
- renamed/copied paths
- new untracked files

Git documents porcelain output as stable for scripts, and `--no-optional-locks` is specifically intended for background/scripting scenarios that should avoid taking optional repository locks.[6][14]

This should be AMD's default repeat-refresh path inside Git repos.

#### Recommended Git performance knobs

AMD should not require these, but `amd doctor` should recommend them for large repos:

- `core.untrackedCache=true`
- `core.fsmonitor=true`
- optional `core.splitIndex=true`

Git documents untracked cache and FSMonitor as ways to avoid rescanning the whole tree for repeated status operations, and split index as a large-index optimization.[6][7][15]

Outside Git repos, use a manual `os.scandir()`/stack walk instead of `Path.rglob()`.

Why:

- AMD can prune ignored directories before descending
- it avoids needless recursion into known-heavy trees
- it gives cheap access to `stat()` metadata during discovery

In the non-Git fallback path:

- prune `.git/`, `.amd/`, `node_modules/`, `__pycache__/`, and configured ignore roots before descent
- use `st_size` + `st_mtime_ns` as a cheap prefilter
- only read bytes and recompute the content hash when the prefilter says "maybe changed"

Do **not** use mtime as the canonical change detector. It is only a prefilter for the non-Git fallback path.

### 7. File-level reads

AMD should use a two-step read path for Markdown:

1. `Path.read_bytes()` to compute a full-file content hash
2. full text decode + parse only if the content hash changed

Why bytes first:

- hash stability is independent of newline normalization decisions in Python text decoding
- unchanged files are skipped before parse cost

This is the critical refresh optimization for large repos.

### 8. SQLite reads

Use **one SQLite connection per AMD command**.

That is the right Python CLI model:

- commands are short-lived
- no connection pool is necessary
- it matches Python `sqlite3` defaults
- it avoids shared-thread connection hazards

Python documents that `check_same_thread=True` is the default and that if it is disabled, write operations may need to be serialized by the user to avoid corruption.[13] v2 should keep the default behavior.

Recommended connection setup:

- `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=NORMAL`
- `PRAGMA foreign_keys=ON`
- `PRAGMA busy_timeout=5000`

SQLite documents that WAL allows concurrent readers and writers, but also documents that `SQLITE_BUSY` can still occur and that there is only one writer at a time.[2][3][4]

For AMD this is the right trade because `index.sqlite` is a **rebuildable derived cache**, not canonical storage. `synchronous=NORMAL` improves throughput and is acceptable because a power-loss rollback can be recovered by rebuild.[2]

APSW is a valid future upgrade path here, but not required for v2. If AMD stays on stdlib `sqlite3`, `amd doctor` should check the runtime SQLite version and warn on unsafe WAL versions.[12][13]

### 9. Journal and signal reads

Journal and signal files remain JSONL streams.

Read pattern:

- open file in binary or UTF-8 text mode
- seek to stored byte offset for incremental consumers
- read line by line
- parse one JSON object per newline

If the final line is truncated or invalid JSON:

- treat it as a write failure artifact
- ignore only the trailing broken line
- flag it in `amd doctor`
- offer repair by truncating back to the last valid newline

This keeps append-only files recoverable without throwing away the whole stream.

### 10. Signal read mechanics

Signals should use incremental byte offsets exactly as the temporal plan assumes.

Mechanically:

1. open signal file
2. `seek(source_offset)`
3. read and decode complete newline-delimited records
4. stop at EOF
5. persist the new byte offset after successful processing

That keeps signal rollups incremental without rescanning whole files.

### 11. Write patterns: journals and signals

Canonical order for append-only writes:

1. acquire file lock
2. open with append semantics
3. write exactly one JSON object plus trailing newline
4. flush user-space buffers
5. `os.fsync()` before releasing the lock
6. release lock

Python documents that `os.fsync()` should be preceded by `flush()` when writing through a buffered Python file object.[19]

This is the safest default for AMD because journals and signals are the canonical write log.

### 12. SQLite writes

SQLite is the derived index, so write latency should be minimized by **moving expensive work outside the transaction**.

Recommended refresh structure:

1. discover files
2. read and hash files
3. parse changed files
4. derive changed rows in memory
5. open one SQLite connection
6. start one short write transaction
7. bulk-apply row updates with parameterized statements / `executemany()`
8. update FTS rows for changed sections only
9. commit

Python's `sqlite3` module supports `executemany()` for repeated DML and uses the same implicit transaction machinery as `execute()`.[13]

Recommended transaction rule:

- one transaction per refresh pass
- one transaction per small write command
- never hold the write transaction open while parsing the filesystem
- run `PRAGMA optimize;` on write-heavy connections before close so SQLite can maintain planner statistics using its preferred lightweight path.[16]

### 13. Export writes

Exports such as:

- `.amd/export/amd.xref.json`
- `.amd/export/artifacts/<artifact_id>.json`

should be written atomically:

1. create temp file in the same directory
2. write JSON
3. flush + fsync
4. `os.replace(temp, target)`

Python documents that `os.replace()` atomically replaces the destination on success when the source and destination are on the same filesystem.[11]

### 14. Markdown writes

Markdown writes should happen only in materialization-style operations.

Write rule:

- read source Markdown
- replace generated blocks in memory
- write temp file in same directory
- flush + fsync
- `os.replace()`

Never edit Markdown in place.

### 15. Config writes

Config writes are stricter than raw user edits.

Rules:

- if AMD itself writes `.amd/config/<artifact_id>.yml`, it validates before replace
- if a human or agent edits config directly, AMD validates on next read
- invalid config must fail closed: do not partially apply it

### 16. Concurrency model

AMD needs two concurrency layers:

1. **SQLite WAL** for concurrent reads versus one writer
2. **filesystem lock files** for cross-process coordination on non-SQLite writes

They solve different problems.

### 17. Lock granularity

Use **mixed-granularity locks**:

#### Per-artifact lock

Required for:

- `journal/<artifact_id>.jsonl`
- `signals/<artifact_id>.jsonl`
- `.amd/config/<artifact_id>.yml`
- materializing one artifact's Markdown file

This is the default fine-grained lock and allows different agents to touch different artifacts concurrently.

#### Global index lock

Required for:

- `amd refresh`
- `amd reindex`
- export regeneration
- any migration that rewrites SQLite broadly

This prevents two agents from racing to rewrite the derived read model.

#### Project journal lock

Use a project-scoped lock for:

- `_project.jsonl`
- project-level directive capture
- directive-sourced relation writes that land in `_project.jsonl`

### 18. Lock implementation

Use lock files created with `os.open()` and `O_CREAT | O_EXCL | O_WRONLY`.

Python documents that `os.open()` exposes these flags on both Unix and Windows.[11]

Recommended lock payload:

- `pid`
- `hostname`
- `command`
- `started_at`
- optional `artifact_id`

Recommended lock path layout:

```text
.amd/locks/
  index.lock
  project.lock
  artifacts/
    report.payments.incident.lock
```

### 19. Stale lock handling

Lock acquisition should support:

- retry with backoff
- timeout
- stale-lock inspection

Stale rule:

1. if lock is younger than timeout, wait/retry
2. if lock is older than timeout, inspect payload
3. if same-host PID is clearly dead, steal lock
4. if liveness cannot be determined, require timeout expiry and emit warning

This is intentionally conservative.

### 20. SQLite concurrency specifics

WAL mode should be enabled on the index database.

Important implications from SQLite:

- readers and writers can overlap[2]
- there is still only one writer at a time[2]
- `SQLITE_BUSY` can still happen in WAL mode[2]
- the WAL index depends on shared memory, so all readers/writers are expected to be on the same machine[2]

Recommended defaults:

- `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=NORMAL`
- `PRAGMA busy_timeout=5000`
- allow reads during refresh
- return a retryable error for competing write commands if the index lock cannot be acquired

Product rule:

- the fast WAL path is **local-disk only**
- if AMD detects a network-mounted or otherwise unsupported filesystem, it should warn and fall back to a slower compatibility path

`amd doctor` should also gate WAL usage on a safe SQLite runtime version because SQLite's WAL docs now document a rare WAL-reset corruption bug fixed in newer releases.[2]

### 21. Checkpoint strategy

Leave SQLite WAL auto-checkpointing at the default for v2 unless profiling proves it inadequate.

SQLite documents that the default auto-checkpoint strategy runs when the WAL reaches 1000 pages and that this works well for most workstation-class applications.[2]

AMD is exactly that kind of workload.

### 22. Cross-branch and Git merge behavior

Recommended Git treatment:

- `.amd/cache/index.sqlite`: gitignored, always rebuildable
- `.amd/export/*.json`: optionally gitignored; rebuildable snapshots
- `.amd/journal/*.jsonl`: tracked append-only files
- `.amd/signals/*.jsonl`: tracked append-only files
- `.amd/config/*.yml`: tracked text files

For append-only JSONL:

- `merge=union` is acceptable **only if** the project accepts possible line reordering

Git explicitly warns that `merge=union` tends to keep lines from both sides in random order and should be used only with care.[8]

That is acceptable for AMD journals and signals because:

- order is recovered from timestamps during indexing
- lines are independent records

It is **not** acceptable for YAML config.

### 23. Failure modes and recovery

#### Lock held by dead process

- detect using timeout + lock payload
- steal conservatively
- emit a `doctor` warning

#### Half-written JSONL line

- ignore only the final truncated line
- flag it
- allow repair by truncating to the last valid newline

#### SQLite corruption

- run `PRAGMA quick_check` or `PRAGMA integrity_check`
- if corrupt, rebuild the index from Markdown + journals + signals

SQLite documents that `integrity_check` performs a low-level consistency check and reports `ok` when no errors are found.[21]

#### FTS inconsistency

- if the FTS table is suspected stale, rebuild search rows from relational section rows
- do not trust partial in-place repair when the full rebuild path is cheap

#### Concurrent refresh

- only one refresh may hold the global index lock
- the loser waits or exits with a retryable status

### 24. Performance targets

The v2 target should be:

- **500 Markdown files, 5 changed, refresh under 2 seconds on a normal developer laptop**

That target is realistic if AMD does all of the following:

- warm-refresh candidate discovery from Git status
- file hash skip for unchanged candidates
- parse only changed files
- one short SQLite write transaction
- per-section FTS updates instead of full rebuild

### 25. Journal growth and compaction

Do **not** compact journals in v2.

Reasons:

- append-only history is part of the product value
- the index is rebuildable
- project scale is still local-repo scale, not TSDB scale

Future archival or snapshotting may be useful, but v2 should keep the rule simple:

- journals grow
- indexes rebuild
- exports regenerate

## Agent Instructions

Agents should follow this search and I/O order:

1. use `amd prime`, `amd query`, or `amd affected` first for document-context questions
2. use `rg` when the question is regex-heavy, literal-heavy, or code-block-specific
3. open Markdown only after AMD has narrowed the candidate set
4. use Git for prose-delta questions (`git log`, `git diff`, `--word-diff`)

Git documents `--word-diff` and `--find-renames`, both of which are useful to agents diagnosing whether a content change is substantive or mostly cosmetic.[9]

Do not:

- query SQLite directly from the agent layer during normal operation
- rebuild the index just to do a one-off grep-like search
- treat `rg` output as equivalent to AMD's section-aware search results

## Core Decisions

v2 should lock these in:

1. **Primary search engine**: SQLite FTS5
2. **Supplementary raw search**: `ripgrep`, mostly agent-side
3. **Cold discovery in Git repos**: `git ls-files -z --cached --others --exclude-standard --full-name --deduplicate`
4. **Warm refresh in Git repos**: `git --no-optional-locks status --porcelain=v2 -z`
5. **Default tokenizer**: `unicode61 remove_diacritics 2`; `porter` is opt-in
6. **SQLite mode**: WAL + `synchronous=NORMAL` + `busy_timeout`
7. **Connection model**: one connection per command
8. **FTS maintenance**: incremental delete + reinsert per changed section
9. **Locking model**: lock files for append-only and rewrite operations, global index lock for refresh/reindex
10. **Rewrite model**: temp file + flush + fsync + `os.replace()`
11. **Journal compaction**: none in v2
12. **Optional upgrades, not defaults**: APSW, trigram side index, `orjson`

## How This Ties To Other v2 Plans

- [markdown-parsing-and-section-identity.md](/Users/avinier/Projects.py/amd/internals/v2/plans/markdown-parsing-and-section-identity.md) defines the section units and normalized text this plan reads and indexes.
- [context-graph-architecture.md](/Users/avinier/Projects.py/amd/internals/v2/plans/context-graph-architecture.md) defines the relational and graph model this plan reads and writes.
- [temporal-context-handling.md](/Users/avinier/Projects.py/amd/internals/v2/plans/temporal-context-handling.md) defines journal and signal record semantics that this plan appends and streams.
- [config-and-schemas.md](/Users/avinier/Projects.py/amd/internals/v2/plans/config-and-schemas.md) defines the config files this plan validates and rewrites atomically.
- [changes-propagation.md](/Users/avinier/Projects.py/amd/internals/v2/plans/changes-propagation.md) is the primary consumer of the search architecture described here.

## Gaps And Future Work

- Whether AMD should expose a first-class `amd grep --regex` wrapper over `rg --json`
- Whether AMD should add an auxiliary trigram FTS5 index for substring-heavy repos
- Whether export regeneration should be always-on after refresh or an explicit `amd export`
- Whether directory fsync after `os.replace()` should be a platform-specific durability hardening step in v2

## Sources

[1] SQLite, “FTS5 Extension.” Official docs. Tokenizers, prefix indexes, external-content pitfalls, detail mode, BM25, rank, highlight, and snippet behavior. <https://sqlite.org/fts5.html>

[2] SQLite, “Write-Ahead Logging.” Official docs. Reader/writer overlap, one-writer rule, autocheckpoint defaults, same-machine WAL-index behavior. <https://sqlite.org/wal.html>

[3] SQLite, “File Locking And Concurrency In SQLite Version 3.” Official docs. Locking model background. <https://sqlite.org/lockingv3.html>

[4] SQLite, “PRAGMA busy_timeout.” Official docs. Busy wait configuration. <https://sqlite.org/pragma.html#pragma_busy_timeout>

[5] Git, “git-ls-files.” Official docs. `--cached`, `--others`, `--exclude-standard`, `-z`, and `--deduplicate`. <https://git-scm.com/docs/git-ls-files>

[6] Git, “git-status.” Official docs. Stable porcelain output for scripts, performance notes for untracked files, and FSMonitor/untracked cache guidance. <https://git-scm.com/docs/git-status>

[7] Git, “git-fsmonitor--daemon.” Official docs. Built-in file system monitor daemon. <https://git-scm.com/docs/git-fsmonitor--daemon>

[8] Git, “gitattributes.” Official docs. `merge=union` semantics and warning about random line order. <https://git-scm.com/docs/gitattributes>

[9] Git, “git-diff.” Official docs. `--word-diff` and `--find-renames`. <https://git-scm.com/docs/git-diff>

[10] ripgrep, official docs and guide. Recursive search behavior, ignore handling, glob filtering, JSON mode. <https://github.com/BurntSushi/ripgrep/blob/master/README.md> and <https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md>

[11] Python Standard Library, `os`. Official docs. `os.open()`, `O_CREAT`, `O_EXCL`, and `os.replace()`. <https://docs.python.org/3/library/os.html>

[12] APSW documentation, “sqlite3 module differences.” Official docs. Rationale for APSW versus stdlib `sqlite3`. <https://rogerbinns.github.io/apsw/pysqlite.html>

[13] Python Standard Library, `sqlite3`. Official docs. `check_same_thread`, `sqlite_version`, `timeout`, `executemany`, and transaction behavior. <https://docs.python.org/3.12/library/sqlite3.html>

[14] Git, main command documentation. Official docs. `--no-optional-locks` for background commands. <https://git-scm.com/docs/git/2.48.0.html>

[15] Git, “git-update-index.” Official docs. `split-index` and `untracked-cache`. <https://git-scm.com/docs/git-update-index>

[16] SQLite, “PRAGMA optimize.” Official docs. Preferred lightweight statistics maintenance. <https://sqlite.org/pragma.html#pragma_optimize>

[17] ripgrep, “README.” Official docs. Default ignore handling and line-oriented recursive search. <https://github.com/BurntSushi/ripgrep/blob/master/README.md>

[18] ripgrep, “GUIDE.” Official docs. Additional glob filtering. <https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md>

[19] Python Standard Library, `os.fsync`. Official docs. Flush before fsync guidance. <https://docs.python.org/3/library/os.html#os.fsync>

[20] ripgrep official site. JSON output capability and overview. <https://ripgrep.dev/>

[21] SQLite, “PRAGMA integrity_check.” Official docs. Integrity checking and `ok` result semantics. <https://sqlite.org/pragma.html>
