"""The diff build pipeline, shared by this app's two callers.

Extracted out of ``routes.py::render_diff``'s inner ``_build`` closure
(2026-08-12) when the MCP surface was added. A Tier-1 (in-process) app's MCP
handler calls its own logic DIRECTLY rather than doing an HTTP hop back into
its own REST route — see ``mcp/http_handler.py``'s docstring for why the
older stdio-over-HTTP shape was abandoned. That's only possible if the logic
lives somewhere both can import, hence this module.

Blocking by design (it shells out to ``git``): both callers hand it to a
thread (``run_in_executor`` / ``run_in_threadpool``) rather than blocking the
event loop.
"""
from __future__ import annotations

import os
import subprocess

from . import render
from .repo_paths import resolve_repo_path

MOUNT_PREFIX = "/api/apps/diff-tool"

#: Auto-discovery only ever renders this many files; beyond it the result is
#: flagged ``capped`` so callers can say so out loud instead of silently
#: truncating.
MAX_FILES = 50


def build_diff(store, *, repo: str = "", ref: str = "", title: str = "",
               files: list | None = None) -> dict:
    """Render a diff and store it (which broadcasts ``diff_open``).

    Two input modes, matching the two entry points this app exists for:
      * ``repo`` (+ optional ``ref``) — auto-discover changed files via
        ``git diff --name-only``.
      * ``files`` — an explicit ``[{file_path, diff_text?, ref?}]`` list.

    Returns ``{"success": True, "diff_id", "files", "capped"}`` on success, or
    ``{"success": False, "error"}`` on failure.

    A failure dict may carry a ``status`` key — the HTTP code the REST caller
    should use. Only the unresolvable-repo case sets it (400); every other
    soft failure deliberately omits it so the route answers 200 with
    ``success: false``, which is the contract ``/diffs/render`` shipped with
    and ``tests/test_routes.py`` pins. The MCP caller ignores ``status``
    entirely — for it, ``success`` is the only thing that matters.
    """
    explicit_files = files or []

    repo_path = resolve_repo_path(repo) if repo else None
    if repo and not repo_path:
        return {"success": False, "error": f"Not a git repo: {repo}", "status": 400}

    capped = False
    total_changed = 0
    if explicit_files:
        changed = explicit_files
    else:
        if not repo_path:
            return {"success": False, "error": "repo or files is required"}
        cmd = ["git", "diff", "--name-only"]
        if ref:
            cmd.append(ref)
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_path, timeout=30)
        changed_names = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        if not changed_names:
            return {"success": False, "error": "No changes found"}
        capped = len(changed_names) > MAX_FILES
        total_changed = len(changed_names)
        if capped:
            changed_names = changed_names[:MAX_FILES]
        changed = [{"file_path": os.path.join(repo_path, f)} for f in changed_names]

    files_data = []
    for f in changed:
        file_path = f["file_path"] if os.path.isabs(f["file_path"]) else (
            os.path.join(repo_path, f["file_path"]) if repo_path else f["file_path"]
        )
        diff_text = f.get("diff_text") or render.compute_git_diff(file_path, f.get("ref") or ref)
        if not diff_text:
            continue
        # rel_path must be the path relative to the repo root (e.g.
        # "src/api/routes/git_ops.py"), NOT os.path.basename(file_path)
        # — it becomes the commit checkbox's data-path, POSTed back to
        # /commit and fed to `git add --`. Using the basename makes
        # `git add` a no-op ("pathspec did not match any files"), so
        # the commit silently produces no changes despite reporting
        # success. Ported verbatim from the monolith's git_ops.py.
        rel_path = file_path
        if repo_path:
            try:
                rel_path = os.path.relpath(file_path, repo_path)
            except ValueError:
                pass
        files_data.append({"file_path": file_path, "diff_text": diff_text, "rel_path": rel_path})

    if not files_data:
        return {"success": False, "error": "No diffs found for the provided files"}

    if repo_path:
        repo_name = os.path.basename(repo_path)
        # `total_changed` is the pre-truncation count — reporting
        # `len(changed)` here would always print the cap itself ("first 50 of
        # 50+"), which tells the user nothing about how much was dropped.
        suffix = f" (first {MAX_FILES} of {total_changed})" if capped else ""
        diff_title = (title or f"Diff: {repo_name} vs {ref or 'working tree'}") + suffix
    else:
        file_names = ", ".join(os.path.basename(f["file_path"]) for f in files_data)
        diff_title = title or f"Diff: {file_names}"

    html = render.generate_diff_html(
        files_data,
        repo_dir=repo_path,
        commit_path=f"{MOUNT_PREFIX}/commit",
    )
    entry = store.create(diff_title, html)
    return {"success": True, "diff_id": entry["id"], "files": len(files_data), "capped": capped}
