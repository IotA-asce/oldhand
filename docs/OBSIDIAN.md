# Open Oldhand memory in Obsidian

Oldhand stores ordinary Markdown. Obsidian can open the same files as a vault;
you can read and edit your original memory notes and explore their graph.
No Obsidian plugin, separate export, or account is required.

## Set up the graph

Native record links are included in `0.6.0b2` and later. Install or upgrade in
your preferred Python environment with `python -m pip install --upgrade --pre
oldhand`, or use `pipx install oldhand==0.6.0b3` for an isolated CLI installation.
Version `0.6.0b1` has the older topic-hub-only command.

1. Run `oldhand --root /path/to/archive obsidian` once. Use the directory that
   contains `memory/`, or the common workspace root for multiple collections.
2. In Obsidian's vault switcher, choose **Open folder as vault**, then select
   that exact directory. Keep an existing vault if the archive already lives
   inside one; the generated relative links work there too.
3. Open `HOME.md` to browse collections and topics. Open **Graph view** to see
   the archive, or select a memory note and run **Open local graph**.

Each memory is a real note in the graph. Topic hubs connect records sharing a
topic; declared relationships connect records directly. For example:

```yaml
relations:
  depends_on:
    - config-replacement-semantics
```

Oldhand resolves that stable record ID to its actual file and adds a link
labelled `depends_on` in the note's **Obsidian graph** section. It does not
infer relationships from similar wording. Link paths include the directories
needed to distinguish identically named notes across collections.

## Edit the same notes

Edit Summary, Knowledge, and other authored sections in Obsidian as usual.
Keep required Oldhand frontmatter and headings valid. YAML `relations` remain
the authoritative typed relationships, and `topics` remains authoritative
topic membership. Obsidian's properties UI cannot edit nested mappings, so
use Source mode for `relations`, or run `oldhand relate` / `oldhand unrelate`.

After changing metadata or moving files manually, run:

```bash
oldhand --root /path/to/archive rebuild
```

Oldhand's CLI authoring commands refresh the enabled graph as part of their
normal index refresh. There is no background watcher: Obsidian immediately
shows prose edits, while derived graph links update on the next rebuild.
Do not edit the generated graph section to change a relationship; use the
canonical metadata or CLI. Manually authored links elsewhere remain yours.

## What Oldhand owns

- **Original records:** only the section between the reserved
  `<!-- oldhand:graph:start -->` / `<!-- oldhand:graph:end -->` lines.
  Refreshes preserve all bytes outside that section and leave metadata,
  including `updated_at`, unchanged. Ordinary authoring commands still update
  metadata timestamps when the knowledge itself changes.
- **Navigation:** `HOME.md` and marked notes under `_topics/` are generated
  and may be replaced. Stale marked hubs are removed; unmarked user notes are
  preserved. A conflicting user `HOME.md` must be moved before enabling.
- **Enablement:** `_topics/.oldhand.json` persists the opt-in. Keep this file
  with your archive if you want other checkouts to refresh the graph too.
  Removing it stops automatic refreshes; existing links remain ordinary
  Markdown until you remove the generated sections or re-enable the feature.

Oldhand does not write `.obsidian/` settings. If you used the older generator,
its recognizable generated `HOME.md` can be upgraded. Old, unmarked topic
notes are preserved; inspect and remove those legacy duplicates manually if
they clutter the graph.

Generated sections are excluded from Oldhand's parsed retrieval text so
navigation cannot make a record rank for another record's title. Topic hubs
and HOME are outside the canonical `memory/` records. Deleting the derived
`.oldhand/` database does not disable graph refreshes.

## Graph behavior and limits

Obsidian's graph displays links between notes; it does not label an edge with
Oldhand's relationship type. Read the source note's graph section or use
`oldhand backlinks ID` for that information. Retired records remain visible,
and their statuses appear in navigation notes. HOME and memory indexes may
appear as large hubs; use Graph view's filters to focus on memory notes and
topic hubs. Other Markdown files under the vault also appear normally.

Malformed records block explicit `oldhand obsidian` synchronization. A graph
refresh failure during rebuild prints a warning and preserves the normal
search rebuild behavior; fix the reported conflict and rerun the command.
Generated output refuses symlink paths and never replaces an unowned note.

The integration uses Obsidian's documented [internal Markdown links](https://obsidian.md/help/links)
and [Graph view](https://obsidian.md/help/plugins/graph). See also its
[properties documentation](https://obsidian.md/help/properties) for supported
frontmatter editing.
