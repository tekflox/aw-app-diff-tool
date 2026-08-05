"""Repo-path resolution, ported from the monolith's
``src/api/routes/git_ops.py::_resolve_repo_path`` — same normalization
rules, same reasoning (see docstring below), just pointed at this
app's own notion of the workspace root instead of the monolith's
``BASE_DIR`` import.

Root discovery mirrors aw-app-git's ``uncommitted_watchdog.workspace_root()``:
aw-workspace runs with ``WORKDIR /opt/agentic-workspace`` (bind-mounted to
the host workspace dir), so ``os.getcwd()`` at call time is that directory.
``AW_APP_DIFF_TOOL_ROOT`` overrides it for tests / non-default layouts.
"""
from __future__ import annotations

import os


def workspace_root() -> str:
    return os.environ.get("AW_APP_DIFF_TOOL_ROOT") or os.getcwd()


def resolve_repo_path(value: str) -> str | None:
    """Map any of the forms we see in the wild to an absolute git repo path.

    Accepts:
      - absolute path  -> used as-is if it's a git repo
      - bare workspace name ("agentic-workspace") -> workspace root
      - bare child name ("vpn", "resume") -> <root>/repos/<name>
      - relative path -> resolved against the workspace root

    Returns the absolute path if it points to a git repo, otherwise None.
    """
    if not value:
        return None
    base_dir = workspace_root()
    if os.path.isabs(value):
        return value if os.path.isdir(os.path.join(value, ".git")) else None
    if value == os.path.basename(os.path.normpath(base_dir)):
        candidate = base_dir
        if os.path.isdir(os.path.join(candidate, ".git")):
            return candidate
    if "/" not in value:
        candidate = os.path.join(base_dir, "repos", value)
        if os.path.isdir(os.path.join(candidate, ".git")):
            return candidate
    candidate = os.path.normpath(os.path.join(base_dir, value))
    if os.path.isdir(os.path.join(candidate, ".git")):
        return candidate
    return None
