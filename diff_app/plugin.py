"""Entrypoint referenced by aw-app.json's runtime.entrypoint
("diff_app.plugin:DiffToolAppPlugin").

Ports the monolith's ``src/api/routes/diff.py`` +
``src/api/routes/git_ops.py``'s diff/commit endpoints onto the F4 ``ctx``
facades — ``ctx.routes`` (``routes:register``) mounts this app's sub-app at
``/api/apps/diff-tool``. No ``db:own-tables`` — diffs are ephemeral
(``DiffStore`` is a plain in-memory LRU, matching the monolith's original
behavior), so nothing needs to survive a restart.
"""
from __future__ import annotations

import asyncio
import logging
import os

from . import routes as routes_mod
from .mcp import self_register as mcp_self_register
from .storage import DiffStore

log = logging.getLogger("aw_apps.diff_tool")


class DiffToolAppPlugin:
    async def activate(self, ctx) -> None:
        self.ctx = ctx
        self.store = DiffStore()
        # F1 hot-loads this app's sub-app via a Mount() into the ALREADY
        # running process — Starlette's own @api.on_event("startup") never
        # fires for a hot-mounted app (the outer app's startup sequence has
        # already completed). activate() runs inside the running event
        # loop, so grab it directly here instead of relying on that event
        # (same fix as aw-app-presentations' plugin.py — see that file's
        # comment for the full regression story, 2026-08-05).
        self.store.set_loop(asyncio.get_running_loop())

        subapp = routes_mod.build_app(self.store)
        ctx.routes.register(subapp)
        ctx.on_deactivate(self._close_all_sockets)

        # Discoverable by aw-mcp-gateway's app-scan — see mcp/self_register.py.
        # Best-effort by design: registration is how OTHER processes find us,
        # never something this app's own routes depend on, so a ctx without a
        # package_dir (bare dev run, minimal test double) must still activate.
        port = int(os.environ.get("AW_PORT", "9030"))
        mcp_self_register.register_self(getattr(ctx, "package_dir", "") or "", port)

        log.info("aw-app-diff-tool activated")

    async def deactivate(self) -> None:
        log.info("aw-app-diff-tool deactivated")

    async def _close_all_sockets(self) -> None:
        for ws in list(self.store._listeners):
            self.store.remove_listener(ws)
