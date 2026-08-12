"""Coverage for DiffStore's on-disk cache — the half of "a restored diff
window still works" that lives in this app (the other half is
aw-workspace-ui's appWindowKeys.js, which stopped restored windows coming
back blank).

Run: python -m pytest tests/test_storage_persistence.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diff_app.storage import DiffStore, default_data_dir  # noqa: E402


@pytest.fixture
def data_dir(tmp_path):
    return str(tmp_path / "diff-tool")


def test_diff_survives_losing_the_whole_process(data_dir):
    """The regression that motivated this: a workspace restart used to take
    every open diff window's content with it."""
    created = DiffStore(data_dir).create("My Diff", "<h1>hi</h1>")

    # A brand-new store over the same dir is exactly what a restart leaves.
    revived = DiffStore(data_dir).get(created["id"])
    assert revived == {"id": created["id"], "title": "My Diff", "html": "<h1>hi</h1>"}


def test_disk_backs_the_memory_lru(data_dir):
    """A diff evicted from the 50-entry LRU is still readable — a restored
    window may well be older than the 50 most recent."""
    store = DiffStore(data_dir)
    first = store.create("First", "<p>first</p>")
    for i in range(60):
        store.create(f"Filler {i}", f"<p>{i}</p>")

    assert first["id"] not in store._store  # evicted from memory
    assert store.get(first["id"])["html"] == "<p>first</p>"


def test_reading_a_missing_diff_is_still_a_miss(data_dir):
    assert DiffStore(data_dir).get("deadbeef") is None


def test_no_data_dir_keeps_the_old_memory_only_behaviour(tmp_path):
    """Persistence is opt-in on the fs:workspace-data grant — without it the
    store must still work, just without surviving a restart."""
    store = DiffStore(None)
    entry = store.create("Ephemeral", "<p>x</p>")
    assert store.get(entry["id"])["html"] == "<p>x</p>"
    assert DiffStore(None).get(entry["id"]) is None
    assert not list(tmp_path.iterdir())


def test_ids_cannot_escape_the_data_dir(data_dir):
    """`diff_id` is accepted straight off the wire by POST /diffs, so it must
    never reach the filesystem as a path fragment."""
    store = DiffStore(data_dir)
    store.create("Traversal", "<p>x</p>", diff_id="../../etc/passwd")

    written = list(Path(data_dir).rglob("*.json")) if Path(data_dir).exists() else []
    assert written == []
    # Still served from memory — refusing to persist is not refusing to work.
    assert store.get("../../etc/passwd")["html"] == "<p>x</p>"


def test_corrupt_file_is_dropped_rather_than_raised(data_dir):
    store = DiffStore(data_dir)
    entry = store.create("Corrupt", "<p>x</p>")
    path = Path(data_dir) / "diffs" / f"{entry['id']}.json"
    path.write_text("{ not json", encoding="utf-8")

    assert DiffStore(data_dir).get(entry["id"]) is None
    assert not path.exists()


def test_disk_cache_is_bounded(data_dir):
    store = DiffStore(data_dir)
    for i in range(230):
        store.create(f"Diff {i}", f"<p>{i}</p>")

    assert len(list((Path(data_dir) / "diffs").glob("*.json"))) <= 200


def test_written_entry_is_plain_json(data_dir):
    """Nothing here should need a migration to read — it's a cache of blobs."""
    entry = DiffStore(data_dir).create("Plain", "<p>x</p>")
    on_disk = json.loads((Path(data_dir) / "diffs" / f"{entry['id']}.json").read_text())
    assert on_disk == entry


def test_default_data_dir_follows_the_workspace_home_convention(monkeypatch):
    monkeypatch.setenv("AW_WORKSPACE_HOME", "/opt/aw-workspace/.aw-workspace")
    assert default_data_dir() == "/opt/aw-workspace/.aw-workspace/data/diff-tool"


def test_default_data_dir_falls_back_to_the_container_dir_not_home(monkeypatch):
    """`~` differs between the workspace process and a spawned agent-runner
    sharing the same mount; the container dir does not."""
    monkeypatch.delenv("AW_WORKSPACE_HOME", raising=False)
    monkeypatch.setenv("AW_WORKSPACE_CONTAINER_DIR", "/somewhere/else")
    assert default_data_dir() == "/somewhere/else/.aw-workspace/data/diff-tool"
