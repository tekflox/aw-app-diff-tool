---
name: aw-diff-tool
description: Open an interactive diff viewer window in aw-workspace — explicit file diffs or repo+ref auto-discovery, with a Commit & Push panel. Use when a user asks to review/see changes, or after making edits you want them to inspect before committing.
---

# aw-diff-tool

Opens a diff-viewer window in the aw-workspace dashboard via the
`show_diff` MCP tool (aw-app-diff-tool's MCP server). Multi-file tabs,
unified/split view, GitHub-style collapsible context, inline word-diff
highlighting, and (when a repo is given) an embedded **Commit & Push**
panel the user can act on directly from the window.

## When to use

- The user asks to "show me the diff", "let me review the changes", "o que
  mudou", etc.
- After you've made a set of edits and want the user to visually review
  before you (or they) commit.
- Comparing a repo's working tree (or a ref) against another ref.

## Two ways this window opens

1. **This skill / the `show_diff` MCP tool** — an agent calls it directly.
2. **The git repo nav's expand arrow** in the aw-workspace dashboard — a
   user-driven equivalent, same backend, no agent involved.

Both land in the same window type; you don't need to do anything special
for the second path — it's documented here for completeness.

## Calling `show_diff`

Two input modes:

### Mode A — repo + ref (auto-discovery)

Let the tool discover changed files itself via `git diff --name-only`:

```json
{
  "repo": "aw-app-diff-tool",
  "ref": "HEAD~1",
  "title": "My changes"
}
```

- `repo` accepts an absolute path, a bare workspace name, or a bare child
  name under `repos/<name>` (resolved the same way `git`/`gh` CLI usage in
  this workspace already expects).
- `ref` defaults to the working tree vs. index if omitted (plain
  `git diff --name-only`).
- Files are capped at 50; if more changed, the tool flags `capped: true`.

### Mode B — explicit files

Pass exact file diffs yourself (useful when you already have diff text, or
want to hand-pick specific files/refs per file):

```json
{
  "files": [
    {"file_path": "/opt/aw-workspace/repos/aw-app-diff-tool/src/foo.py", "ref": "HEAD~1"},
    {"file_path": "/opt/aw-workspace/repos/aw-app-diff-tool/src/bar.py", "diff_text": "@@ ..."}
  ],
  "title": "Selected changes"
}
```

## What happens after the call

The tool renders the diff HTML, stores it, and broadcasts a `diff_open`
event over this app's own WebSocket — the dashboard opens a new window
instance automatically. The returned result string includes added/removed
line counts; report that back to the user in your own reply rather than
re-describing the diff textually (they'll see the real thing in the
window).

## Commit & Push panel

Only rendered when a repo is resolvable (Mode A always has one; Mode B only
if every `file_path` lives under a git repo). The user checks which files
to include, edits the suggested commit message, and clicks Commit — this
posts to the app's own `/commit` endpoint (`git add` + `git commit` +
optional `git push`), not back through you. You don't need to do anything
further once the window is open unless the user asks you to.
