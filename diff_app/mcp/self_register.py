"""Write this app's own ``mcp.json`` so aw-mcp-gateway's app-scan
(``scan_app_mcp_servers()``, reading ``<installed-app-dir>/mcp.json``)
discovers the ``/mcp`` endpoint (``http_handler.py``) without any manual
wiring — mirrors ``aw-app-presentations``' ``presentations_app/mcp/
self_register.py`` (itself mirroring aw-app-whiteboard's, in turn
aw-app-kb's).

This app is Tier-1 (in-process): it IS the aw-workspace process, so
``socket.gethostname()`` returns the exact same value ``ContainerSupervisor``
injects into sibling containers as ``AW_WORKSPACE_HOST`` — no
``AW_APP_SELF_HOST`` needed (that's the Tier-2/own-container case), and no
secret leaves this process, since ``AW_WORKSPACE_API_KEY`` is already in its
own ``os.environ``.

History: from 2026-08-05 (when the diff viewer was decoupled out of the
monolith into this app) until 2026-08-12, the ``show_diff`` MCP tool was
left behind in the monolith as a stdio script,
``agentic-workspace/src/mcp/diff-tool-server.py``, which forwarded to this
app's REST route over HTTP at 127.0.0.1:9123. That script was registered in
the monolith's runtime ``.mcp.json`` as ``aw-diff-tool`` — which is also how
a stale row for it ended up frozen in agents-platform-multitenant's
``mcp_servers`` table (it mounted that file until 2026-08-06). The app itself
never registered anywhere, so the tool was invisible to aw-gateway and to
every agent. This module closes that gap; the monolith script is now dead.
"""

from __future__ import annotations

import json
import logging
import os
import socket

log = logging.getLogger("aw_apps.diff_tool")

MCP_SERVER_NAME = "aw-diff-tool"


def _mcp_json_path(package_dir: str) -> str:
    return os.path.join(package_dir, "mcp.json")


def register_self(package_dir: str, port: int) -> None:
    """Best-effort; a bare dev run with no package_dir on a scanned root
    simply no-ops (nothing to write into, nothing breaks)."""
    if not os.path.isdir(package_dir):
        return

    host = socket.gethostname()
    api_key = os.environ.get("AW_WORKSPACE_API_KEY")
    entry: dict = {
        "type": "http",
        "url": f"http://{host}:{port}/api/apps/diff-tool/mcp",
        "enabled": True,
    }
    if api_key:
        entry["headers"] = {"X-Api-Key": api_key}

    path = _mcp_json_path(package_dir)
    data: dict = {"mcpServers": {}}
    try:
        with open(path) as f:
            existing = json.load(f)
        if isinstance(existing, dict) and isinstance(existing.get("mcpServers"), dict):
            data = existing
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    if data["mcpServers"].get(MCP_SERVER_NAME) == entry:
        return
    data["mcpServers"][MCP_SERVER_NAME] = entry
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
        log.info("registered self as %r in %s (%s)", MCP_SERVER_NAME, path, entry["url"])
    except OSError as e:
        log.warning("could not write %s: %s", path, e)
