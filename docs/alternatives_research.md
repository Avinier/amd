## Executive Summary

No single off-the-shelf tool gives you everything AMD is trying to do. The best replacement is a stack, not a new filetype: `Obsidian + Git + a thin automation layer + Quarto for report-heavy docs`. If you want the file format itself to be more structured than plain Markdown, `MyST Markdown` is the strongest substrate. `Dendron` is the closest conceptual match, but as of March 10, 2026 it is still in maintenance mode from a March 2023 announcement, so I would not start greenfield there [1][2][3][4][5][6][7][8][9][10][11][12][13][14][15][16][17][18].

## Best Alternatives

- **Best overall if you want to stay in Markdown:** `Obsidian + Git + Quarto`. Obsidian gives typed YAML properties, templates, Bases views/formulas, CLI commands for create/read/append/diff/history, and shared vaults; Git gives the real audit trail; Quarto gives pre/post-render scripts and execution freezing for heavyweight reports [1][2][3][4][5][6][7][8].
- **Best repo-first structured format:** `MyST Markdown`. It has page/project frontmatter, directives, executable code-cell directives, labels, and cross-references. Inference: this is the cleanest base if you want AST-aware linting or fingerprinting later [9][10][11].
- **Best outline/journal alternative:** `Logseq`. It has templates, live queries, page properties, and page history, but the August 31, 2024 Sync guide explicitly said Sync did not support collaboration on the same graph, and same-page simultaneous editing was only “experimental Smart Merge” there [12][13][14].
- **Best schema-first note system:** `Dendron`. Its own pitch is that schemas and templates are a type system for general knowledge, which is very close to what you want. The problem is project status, not concept [15][16].
- **Best if you can drop Markdown:** `Org mode`. Functionally, Org is the closest thing to the “rich artifact file” you seem to want: property drawers, LOGBOOK-style trace, TODO state logging, and live code execution with Babel. It just breaks your Markdown constraint [17][18].

## Requirement Mapping

- **Dynamic evolving md filetype for agents:** Obsidian or MyST. Obsidian is better for human workflow; MyST is better for machine-structured docs [1][2][3][9][10].
- **MD timeline trace for multi-agent work:** use Git/history as the source of truth, not inline timeline sections. Obsidian has version history and shared vaults; Logseq has page history; Git is still the cleanest audit model [4][5][6][12].
- **Better templating:** Obsidian is the pragmatic winner; Dendron was the strongest schema/template design [2][15].
- **Mental model docs derived into skills:** no tool I checked does this natively. Quarto scripts or Obsidian CLI are the cleanest automation hooks for generating `skills.md` from `mental-model/*.md` [4][7].
- **500-line nuanced report / fingerprint scanner:** no mainstream tool I found has native semantic fingerprint scanning. Inference: MyST/Quarto are better bases because they expose more structure than plain Markdown [8][9][10][11].
- **Persistent vs non-persistent artifacts:** this is a frontmatter convention, not a product feature. You do not need a new file format for it.
- **Stale data, update priority, caveat rules:** same answer. I did not find first-class native support for these in the official docs I checked. This is policy you still implement yourself.
- **Auto-updating artifacts:** Quarto project scripts and Obsidian CLI both support this cleanly [4][7].
- **Heavy timeseries data:** Quarto or Org are strongest, because they support executable documents and keep heavy data outside the prose while rendering summaries into it [7][8][17].
- **Querying and dashboards:** Obsidian Bases or Logseq live queries can surface priority/staleness once you compute those fields [3][13][14].

## What I’d Actually Choose

If you want the least bespoke system while staying in Markdown, use:

`Obsidian vault + YAML frontmatter + Git + scheduled refresh/lint scripts + Quarto for report folders`

That gets you almost everything AMD wants without inventing a new format. The only part you still need custom code for is your policy layer: stale detection, priority scoring, caveat enforcement, and whatever “fingerprint” means for your domain.

If you want a more deterministic, repo-first system for agents, skip the vault UX and use:

`MyST/Quarto + Git + thin automation`

That is the cleaner engineering choice.

So the short answer is: you probably do **not** need AMD as a separate filetype. You need normal Markdown or Quarto/MyST files, plus conventions and automation.

## Sources

[1] [Obsidian Properties](https://help.obsidian.md/properties)  
[2] [Obsidian Templates](https://help.obsidian.md/Plugins/Templates)  
[3] [Obsidian Bases syntax](https://help.obsidian.md/bases/syntax)  
[4] [Obsidian CLI](https://help.obsidian.md/cli)  
[5] [Obsidian shared vault collaboration](https://help.obsidian.md/sync/collaborate)  
[6] [Obsidian sync methods, including Git](https://help.obsidian.md/sync-notes)  
[7] [Quarto Project Scripts](https://quarto.org/docs/projects/scripts.html)  
[8] [Quarto Managing Execution / freeze](https://quarto.org/docs/projects/code-execution.html)  
[9] [MyST frontmatter](https://mystmd.org/guide/frontmatter)  
[10] [MyST directives](https://mystmd.org/guide/directives)  
[11] [MyST cross-references](https://mystmd.org/guide/cross-references)  
[12] [Logseq Sync guide, August 31, 2024](https://blog.logseq.com/how-to-setup-and-use-logseq-sync/)  
[13] [Logseq live queries update](https://blog.logseq.com/whiteboards-and-queries-for-everybody/)  
[14] [Logseq templates and page-properties examples](https://blog.logseq.com/how-to-set-up-an-automated-daily-template-in-logseq/)  
[15] [Dendron homepage](https://www.dendron.so/)  
[16] [Dendron schemas docs](https://wiki.dendron.so/notes/c5e5adde-5459-409b-b34d-a0d75cbb1052/)  
[17] [Dendron maintenance-mode announcement, March 2023](https://github.com/dendronhq/dendron/discussions/3890)  
[18] [Org mode homepage and features](https://orgmode.org/)  
[19] [Org manual: properties drawers and LOGBOOK-style logging](https://orgmode.org/org.html)