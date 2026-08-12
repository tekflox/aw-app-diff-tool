"""Diff-tool REST + WebSocket sub-app, ported from the monolith's
``src/api/routes/diff.py`` (ephemeral store) and
``src/api/routes/git_ops.py``'s ``show_diff``/``commit_and_push`` (the
repo-vs-ref auto-discovery path and the embedded Commit & Push panel's
backend), registered via ``ctx.routes.register`` at
``/api/apps/diff-tool`` (mounted by the runtime).

Two ways a diff gets created here, matching the two entry points the app
exists for:
  * ``POST /diffs`` — an agent (via this app's MCP tool) posts pre-rendered
    title+html directly, same shape as the monolith's ``POST /api/diff``.
  * ``POST /diffs/from-repo`` — the git-repo-nav "arrow" button posts
    {repo, ref, title}; this discovers changed files via
    ``git diff --name-only`` and renders them itself (the monolith's
    ``GitOpsRoutes.show_diff``).

Both paths funnel into the same ``DiffStore`` and broadcast the same
``diff_open`` WS event, so a single frontend listener drives both entry
points into ``window.__awOpenAppWindow``.

Auth: same framework gap as every other hot-mounted app sub-app today
(aw-app-git, aw-app-presentations) — IdentityGuard doesn't cover mounted
routes yet, so these are reachable unauthenticated on the current
framework. Not re-solved per-app.
"""
from __future__ import annotations

import logging
import subprocess

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse

from .build import MOUNT_PREFIX, build_diff  # noqa: F401  (MOUNT_PREFIX re-exported)
from .repo_paths import resolve_repo_path
from .storage import DiffStore

_log = logging.getLogger("diff_app.routes")


def build_app(store: DiffStore) -> FastAPI:
    api = FastAPI()

    @api.post("/diffs")
    async def create_diff(data: dict = Body(...)):
        title = data.get("title", "Diff")
        html = data.get("html", "")
        diff_id = data.get("id")
        entry = store.create(title, html, diff_id=diff_id)
        return {"diff_id": entry["id"], "success": True}

    @api.get("/diffs/{diff_id}/html")
    async def get_diff_html(diff_id: str):
        entry = store.get(diff_id)
        if not entry:
            return HTMLResponse("<h1>Diff not found or expired</h1>", status_code=404)
        return HTMLResponse(entry["html"])

    @api.post("/diffs/render")
    async def render_diff(data: dict = Body(...)):
        """Render a diff from a repo (auto-discovery) or an explicit file list.

        Expects: {repo?, ref?, files?: [{file_path, diff_text?, ref?}], title?}
        Both this app's two entry points funnel here: the git-repo-nav arrow
        sends {repo, ref, title} (auto-discovery); the show_diff MCP tool can
        send either mode, matching the monolith's presentation-server.py
        show_diff handler this replaces.
        """
        try:
            result = await run_in_threadpool(
                build_diff, store,
                repo=data.get("repo", ""), ref=data.get("ref", ""),
                title=data.get("title", ""), files=data.get("files"),
            )
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)
        status = result.pop("status", None)
        if status is not None:
            return JSONResponse(result, status_code=status)
        return result

    # ------------------------------------------------------------------
    # MCP — Streamable HTTP, auto-discovered by aw-mcp-gateway's app-scan
    # (see mcp/self_register.py + mcp/http_handler.py).
    # ------------------------------------------------------------------

    @api.post("/mcp")
    async def mcp_post(data: dict | list = Body(...)):
        from fastapi.responses import Response

        from .mcp.http_handler import handle_request as mcp_handle_request

        messages = data if isinstance(data, list) else [data]
        responses = []
        for m in messages:
            r = await mcp_handle_request(m, store=store)
            if r is not None:
                responses.append(r)
        if not responses:
            return Response(status_code=202)
        return JSONResponse(responses if isinstance(data, list) else responses[0])

    @api.get("/mcp")
    async def mcp_get():
        from fastapi.responses import Response
        return Response(status_code=405)

    @api.post("/commit")
    async def commit_and_push(data: dict = Body(...)):
        """Commit selected files and optionally push.

        Expects: {repo_dir, files: [str], message, push}
        Ported verbatim from the monolith's git_ops.py::commit_and_push.
        """
        raw_repo = data.get("repo_dir", "")
        files = data.get("files", [])
        message = data.get("message", "").strip()
        push = data.get("push", True)

        if not files:
            return JSONResponse({"success": False, "error": "No files selected"}, status_code=400)
        if not message:
            return JSONResponse({"success": False, "error": "Commit message is required"}, status_code=400)

        repo_abs = resolve_repo_path(raw_repo)
        if not repo_abs:
            return JSONResponse({"success": False, "error": f"Not a git repo: {raw_repo}"}, status_code=400)

        try:
            result = subprocess.run(
                ["git", "add", "--"] + files,
                capture_output=True, text=True, cwd=repo_abs, timeout=30,
            )
            if result.returncode != 0:
                return JSONResponse({"success": False, "error": f"git add failed: {result.stderr.strip()}"})

            result = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True, text=True, cwd=repo_abs, timeout=30,
            )
            if result.returncode != 0:
                return JSONResponse({"success": False, "error": f"git commit failed: {result.stderr.strip()}"})

            commit_output = result.stdout.strip()

            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, cwd=repo_abs, timeout=10,
            )
            commit_hash = result.stdout.strip()

            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, cwd=repo_abs, timeout=10,
            )
            branch = result.stdout.strip()

            push_output = ""
            if push:
                result = subprocess.run(
                    ["git", "push"],
                    capture_output=True, text=True, cwd=repo_abs, timeout=60,
                )
                if result.returncode != 0:
                    return JSONResponse({
                        "success": False,
                        "error": f"Commit succeeded but push failed: {result.stderr.strip()}",
                        "commit_hash": commit_hash,
                        "branch": branch,
                    })
                push_output = result.stderr.strip() or result.stdout.strip()

            return JSONResponse({
                "success": True,
                "commit_hash": commit_hash,
                "branch": branch,
                "files_committed": len(files),
                "pushed": push,
                "commit_output": commit_output,
                "push_output": push_output,
            })
        except subprocess.TimeoutExpired:
            return JSONResponse({"success": False, "error": "Git operation timed out"})
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)})

    @api.websocket("/ws")
    async def diff_stream(websocket: WebSocket):
        """Stream diff_open events — mounted at /api/apps/diff-tool/ws.

        {"type": "diff_open", "diff": {"id": ..., "title": ...}} per new diff.
        """
        await websocket.accept()
        store.add_listener(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            store.remove_listener(websocket)

    return api
