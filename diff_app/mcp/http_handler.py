"""MCP server for the diff tool, exposed over Streamable HTTP (POST /mcp).

Replaces the monolith's stdio script ``agentic-workspace/src/mcp/
diff-tool-server.py`` (left behind when the viewer was decoupled into this
app on 2026-08-05). That shape — a subprocess spawned by aw-mcp-gateway,
calling back into this app's own REST route over HTTP — needed the gateway
container to hold this workspace's API key, which it has no path to short of
hand-editing the installed (never git-committed) copy after every deploy.
aw-app-presentations hit exactly this wall and abandoned the stdio port on
2026-08-08; this file follows its ``presentations_app/mcp/http_handler.py``.

This app is Tier-1 (in-process) — its routes already run inside the same
aw-workspace process as everything else. So the handler below calls
``build_diff`` DIRECTLY instead of making an HTTP hop back into
``/diffs/render``: no network, no credentials, nothing to provision.
``self_register.py`` tells aw-mcp-gateway where this endpoint lives.
"""

from __future__ import annotations

from fastapi.concurrency import run_in_threadpool

from ..build import MAX_FILES, build_diff
from ..storage import DiffStore


def _ok(req_id, text):
    return {"jsonrpc": "2.0", "id": req_id,
            "result": {"content": [{"type": "text", "text": text}], "isError": False}}


def _err(req_id, text):
    return {"jsonrpc": "2.0", "id": req_id,
            "result": {"content": [{"type": "text", "text": text}], "isError": True}}


TOOLS_SCHEMA = [
    {
        "name": "show_diff",
        "description": (
            "Display a file diff in the AW UI with interactive views: Unified (hunks "
            "only), Split (side-by-side), Full File (expand/collapse like GitHub). "
            "Supports multiple files as tabs, and an embedded Commit & Push panel when "
            "a repo is resolvable. Two input modes: (1) repo+ref auto-discovers all "
            "changed files via `git diff --name-only`; (2) explicit `files` list for "
            "hand-picked file/ref/diff-text combinations. The window opens in the "
            "user's dashboard automatically — report the returned counts rather than "
            "re-describing the diff textually."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Path to the git repo — absolute, a bare workspace/child name (e.g. 'aw-app-diff-tool' resolves under repos/), or relative. Required for auto-discovery mode; also enables the Commit & Push panel when files are relative to it.",
                },
                "ref": {
                    "type": "string",
                    "description": "Git ref to diff against (e.g. 'develop', 'origin/main', 'HEAD~1'). Used with repo for auto-discovery, or as the default ref for files that don't specify their own. Omit to diff the working tree.",
                },
                "files": {
                    "type": "array",
                    "description": "Explicit list of files to diff. Optional — if repo+ref is given without files, changed files are auto-discovered.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "Absolute path, or relative to repo if repo is also given"},
                            "diff_text": {"type": "string", "description": "Raw unified diff output — if omitted, computed via `git diff` against ref/repo"},
                            "ref": {"type": "string", "description": "Git ref to diff against for this specific file (overrides the top-level ref)"},
                        },
                        "required": ["file_path"],
                    },
                },
                "title": {"type": "string", "description": "Optional window title"},
            },
        },
    },
]


async def handle_request(request: dict, *, store: DiffStore) -> dict | None:
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "aw-diff-tool", "version": "2.0.0"},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_SCHEMA}}

    if method != "tools/call":
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"}}

    name = request.get("params", {}).get("name", "")
    args = request.get("params", {}).get("arguments", {}) or {}

    if name != "show_diff":
        return _err(req_id, f"Unknown tool: {name}")

    # build_diff shells out to git — keep it off the event loop.
    try:
        result = await run_in_threadpool(
            build_diff, store,
            repo=args.get("repo") or "", ref=args.get("ref") or "",
            title=args.get("title") or "", files=args.get("files"),
        )
    except Exception as e:
        return _err(req_id, f"show_diff failed: {e}")

    if not result.get("success"):
        return _err(req_id, result.get("error", "show_diff failed"))

    count = result.get("files", 0)
    cap_note = f", capped at {MAX_FILES}" if result.get("capped") else ""
    return _ok(req_id, f"Diff displayed: {result['diff_id']} "
                       f"({count} file{'s' if count != 1 else ''}{cap_note})")
