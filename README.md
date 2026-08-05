# aw-app-diff-tool

Interactive git diff viewer + commit panel for aw-workspace, decoupled from
the monolith (`agentic-workspace`'s `src/api/routes/diff.py` +
`src/mcp/presentation/diff_viewer.py` + `src/api/routes/git_ops.py`'s
`show_diff`/`commit_and_push`). Multi-file tabs, unified/split view toggle,
GitHub-style collapsible context regions, inline word-diff highlighting, and
an embedded Commit & Push panel.

Two ways a diff window opens:

1. **An agent calls the `show_diff` MCP tool** — explicit files or
   repo+ref auto-discovery, renders and pushes a `diff_open` event.
2. **The git repo nav's expand arrow** (in `aw-workspace-ui`'s `RepoNav.jsx`)
   — posts `{repo, ref, title}` to `POST /api/apps/diff-tool/diffs/from-repo`.

Both funnel into the same in-memory `DiffStore` (ephemeral — diffs don't
survive a restart, same as the monolith) and broadcast the same
`diff_open` WebSocket event over this app's own `/api/apps/diff-tool/ws`.

## Layout

- `aw-app.json` — manifest (`id: diff-tool`, `tier: inprocess`).
- `diff_app/render.py` — unified-diff parsing + the self-contained HTML/CSS/JS
  diff-viewer generator, ported verbatim from the monolith's
  `diff_viewer.py`. Only change: the embedded Commit & Push panel's JS posts
  to a same-origin, app-relative `COMMIT_PATH` instead of the monolith's
  hardcoded `/api/git/commit` + `x-api-key` header.
- `diff_app/repo_paths.py` — `resolve_repo_path()`, ported from
  `git_ops.py::_resolve_repo_path` (absolute / bare workspace name / bare
  `repos/<name>` child / relative path, all normalized to an absolute repo
  path).
- `diff_app/storage.py` — `DiffStore`, an ephemeral in-memory LRU
  (`OrderedDict`, max 50) ported from `diff.py`, plus this app's own
  WebSocket broadcast (`add_listener`/`remove_listener`/`_broadcast`).
- `diff_app/routes.py` — `build_app(store)`, mounted at
  `/api/apps/diff-tool`: `POST /diffs`, `GET /diffs/{id}/html`,
  `POST /diffs/from-repo` (repo+ref auto-discovery), `POST /commit`,
  `WS /ws`.
- `diff_app/plugin.py` — `DiffToolAppPlugin.activate(ctx)`. Sets the
  broadcast loop directly instead of via `@api.on_event("startup")` — F1
  hot-loads this app's sub-app into an already-running process, so that
  event never fires (same fix as `aw-app-presentations`).
- `ui/` — component-mode frontend: a `diff.viewer` window body
  (`core.window.body:diff.viewer` slot), multi-instance via the
  `instanceId` window framework addition (one open window per diff).
- `skills/aw-diff-tool/SKILL.md` — how an agent opens a diff (the
  `show_diff` MCP tool).

## Dependency

`aw-app-git` declares this app as a dependency (`aw-app.json`'s
`dependencies`) — the git repo nav's expand arrow needs it installed to
render diffs.

## CI/CD

Same `tekflox/aw-marketplace` shared release pipeline as every other
`aw-app-*` repo — `tests/validate_manifest.py` + `tests/test_*.py` gate the
release before any version bump/tag/catalog sync.
