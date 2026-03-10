**Findings**
- `[P1]` The repo’s central claim, “multi-agent traceability,” is not true under concurrent writers. [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):105, [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):363, [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):487. Every command does read-modify-write on the same Markdown file with no lock and no atomic replace. I reproduced concurrent `add_event()` calls and hit `ValueError: ... is not an AMD document`, which means readers can observe a torn write. That makes the “append-only timeline” claim in the README misleading for the exact multi-agent case it is supposed to solve.
- `[P1]` `init` and `derive-skill` can silently overwrite existing work. [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):292, [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):323, [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):590. `create_artifact()` always writes the target path immediately; there is no existence check, backup, or `--force` gate. For a tool that manages hand-edited Markdown, silent clobbering is a bad default.
- `[P2]` The “semantic drift” feature is just raw text hashing, so it fires on formatting-only edits. [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):143, [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):155, [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):373, [README.md](/Users/avinier/Projects.py/amd/README.md):12. I changed only whitespace in a section and `refresh_artifact()` still reported a fingerprint change. That is lexical drift, not semantic drift, so the headline feature is overstated.
- `[P2]` The JSONL sidecar adds complexity without actually solving scale. [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):184, [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):418, [README.md](/Users/avinier/Projects.py/amd/README.md):15, [README.md](/Users/avinier/Projects.py/amd/README.md):27. Every refresh rescans the entire sidecar file to recompute summary metadata. For “heavier signal history,” that turns `refresh` and `watch` into O(n) history walks, so the sidecar separates storage from Markdown but does not buy you operational efficiency.
- `[P3]` Verification is fragile and partly masked inside the tests. [tests/test_qa.py](/Users/avinier/Projects.py/amd/tests/test_qa.py):20, [pyproject.toml](/Users/avinier/Projects.py/amd/pyproject.toml):5. The subprocess tests manually inject `PYTHONPATH`, `pytest -q` failed collection with `ModuleNotFoundError`, and plain `python3 -m unittest -v` ran `0` tests here. The repo does have passing tests, but only via `python3 -m unittest discover -s tests -v`.

**Why This Isn’t Needed**
Assuming “this” means the AMD abstraction itself: today it is mostly a custom Markdown wrapper, not a capability you could not get more cheaply with normal files.

- A lot of the metadata is speculative rather than functional. `context_refs`, `template.name`, `persistence.expires_after_hours`, and `amd_version` are written in [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):250 but are not meaningfully consumed elsewhere.
- `derive-skill` is not a real derivation pipeline; it copies three named sections into another template. [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):578, [amd/core.py](/Users/avinier/Projects.py/amd/amd/core.py):590.
- `watch` is a forever polling loop, and the README itself says stronger automation should be externalized to cron/launchd/agent loops. [amd/cli.py](/Users/avinier/Projects.py/amd/amd/cli.py):190, [README.md](/Users/avinier/Projects.py/amd/README.md):74.

So the repo adds a file format, metadata schema, sidecar storage, and CLI surface area, but it still lacks the hard part that would justify those abstractions: safe concurrent writes, real semantic understanding, and a consumer that does something materially better than Markdown + frontmatter + git + a tiny helper script.

**Checks**
I cross-checked the implementation against the local source and the [GitHub README](https://github.com/Avinier/amd). `python3 -m unittest discover -s tests -v` passed 5 tests; `pytest -q` failed import collection; a concurrent write repro broke document parsing; a whitespace-only edit triggered a fingerprint change.

Yes. The gap is real. That is the strongest argument for building AMD.

But it is only a good reason to build AMD if you build the hard part, not just the wrapper.

Right now, the unmet need is not “Markdown with extra fields.” You can already get that from Obsidian, MyST, Quarto, or plain frontmatter. The real unmet need is:

- agent-managed context that evolves without hand-written instructions
- durable trace/provenance across multiple agents
- stale/priority/caveat policy
- derivation from mental models into operational artifacts
- large-report change detection that is better than naive text diff
- safe automation around all of that

That is a legitimate product surface.

What I’m pushing back on is this: the current AMD mostly implements the easy 20%:
- metadata block
- templates
- timeline section
- JSONL sidecar
- hash-based refresh

Those are not the reasons someone would adopt it. The reasons are the hard 80%:
- concurrent-safe writes
- merge semantics
- AST/semantic fingerprinting
- strong stale detection rules
- real derivation pipeline
- query/index layer for priority and caveats
- user/agent ownership boundaries

So the answer is:

- Yes, this is a reason to build `something`.
- No, it does not yet justify `this exact implementation` as-is.

If you keep building AMD, I’d narrow it to one thesis:

“Policy engine and provenance layer for agent-maintained Markdown.”

Not “new Markdown format.”

That means:
- keep plain `.md` or frontmatter-compatible files
- move trace/index/priority/staleness into an external index or sidecar DB
- use Git as the source of truth for audit/history
- make derivation and refresh the product
- make fingerprints structural, not raw text hashes
- solve concurrent updates before adding more metadata

If you want, I can turn that into a concrete “AMD v2 should be X, not Y” architecture.