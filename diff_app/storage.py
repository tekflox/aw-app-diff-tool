"""Ephemeral diff store, ported from the monolith's
``src/api/routes/diff.py`` — in-memory ``OrderedDict``, LRU-evicted at 50
entries, no DB (diffs are throwaway viewer artifacts, not records worth
persisting across a restart — unlike Presentations).

WebSocket broadcast follows the same ``activate()``-sets-the-loop-directly
pattern as aw-app-presentations' ``storage.py``: F1 hot-loads this app's
sub-app via a bare ``Mount()`` into the already-running process, so
Starlette's ``@api.on_event("startup")`` never fires for it — the loop must
be handed to ``set_loop()`` from ``plugin.py``'s ``activate(ctx)`` instead,
which runs inside the real running event loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import OrderedDict

logger = logging.getLogger("diff_app.storage")

_MAX_DIFFS = 50


class DiffStore:
    def __init__(self):
        self._store: "OrderedDict[str, dict]" = OrderedDict()
        self._listeners: set = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def create(self, title: str, html: str, diff_id: str | None = None) -> dict:
        diff_id = diff_id or uuid.uuid4().hex[:12]
        entry = {"id": diff_id, "title": title, "html": html}
        self._store[diff_id] = entry
        self._store.move_to_end(diff_id)
        if len(self._store) > _MAX_DIFFS:
            self._store.popitem(last=False)
        logger.info("diff created: %s (%s)", diff_id, title)
        self._broadcast({"type": "diff_open", "diff": {"id": diff_id, "title": title}})
        return entry

    def get(self, diff_id: str) -> dict | None:
        return self._store.get(diff_id)

    # ------------------------------------------------------------------
    # WebSocket broadcast
    # ------------------------------------------------------------------

    def add_listener(self, ws):
        self._listeners.add(ws)

    def remove_listener(self, ws):
        self._listeners.discard(ws)

    def _broadcast(self, msg: dict):
        if not self._listeners or not self._loop:
            return
        data = json.dumps(msg)
        self._loop.call_soon_threadsafe(asyncio.ensure_future, self._send_all(data))

    async def _send_all(self, data: str):
        dead = set()
        for ws in self._listeners:
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._listeners.discard(ws)
