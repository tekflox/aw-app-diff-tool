"""Entrypoint referenced by aw-app.json's runtime.entrypoint
("diff_app.plugin:DiffToolAppPlugin").

Ports the monolith's ``src/api/routes/diff.py`` +
``src/api/routes/git_ops.py``'s diff/commit endpoints onto the F4 ``ctx``
facades — ``ctx.routes`` (``routes:register``) mounts this app's sub-app at
``/api/apps/diff-tool``. Still no ``db:own-tables``: diffs are cache entries
with a retention cap, not records. They do outlive a restart now, through
``fs:workspace-data`` (a JSON file per diff under the app's own data dir) —
see ``storage.py`` for why that changed.
"""
from __future__ import annotations

import asyncio
import logging
import os

from . import routes as routes_mod
from .mcp import self_register as mcp_self_register
from .storage import DiffStore, default_data_dir

log = logging.getLogger("aw_apps.diff_tool")

PERSIST_CAPABILITY = "fs:workspace-data"


def _may_persist(ctx) -> bool:
    """True unless the host tells us the capability was withheld.

    ``ctx.has`` is the real answer; a minimal test double or a bare dev run
    without one gets the benefit of the doubt, same as the MCP self-register
    below — this app must still activate against a stub ctx.
    """
    has = getattr(ctx, "has", None)
    return has(PERSIST_CAPABILITY) if callable(has) else True


class DiffToolAppPlugin:
    async def activate(self, ctx) -> None:
        self.ctx = ctx
        # There is no ctx facade for fs:workspace-data yet (framework gap the
        # whiteboard migration flagged too) — an inprocess app resolves the
        # path itself. Honour the grant anyway: without it, no disk cache.
        data_dir = default_data_dir() if _may_persist(ctx) else None
        self.store = DiffStore(data_dir)
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
