"""TestClient coverage for diff_app/routes.py's build_app(), plus a
regression test for the activate()-sets-broadcast-loop-directly fix (same
class of bug as aw-app-presentations' — see plugin.py's docstring).

Run: .venv/aw/bin/python -m pytest tests/test_routes.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diff_app import routes as routes_mod  # noqa: E402
from diff_app.storage import DiffStore  # noqa: E402


@pytest.fixture
def store():
    return DiffStore()


@pytest.fixture
def client(store):
    app = routes_mod.build_app(store)
    return TestClient(app)


def test_create_and_get_html(client):
    resp = client.post("/diffs", json={"title": "My Diff", "html": "<h1>hi</h1>"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    diff_id = body["diff_id"]

    html_resp = client.get(f"/diffs/{diff_id}/html")
    assert html_resp.status_code == 200
    assert "<h1>hi</h1>" in html_resp.text


def test_get_html_not_found(client):
    resp = client.get("/diffs/does-not-exist/html")
    assert resp.status_code == 404


def test_websocket_connects_and_registers_listener(client, store):
    # Broadcast delivery itself needs store._loop bound to the ASGI app's
    # own running loop (set by plugin.py's activate(), never by a bare
    # TestClient) — see test_activate_sets_broadcast_loop_without_relying_
    # on_asgi_startup below for that regression coverage. This just checks
    # the connection lifecycle: listener registered on connect, removed on
    # disconnect.
    with client.websocket_connect("/ws") as ws:
        assert len(store._listeners) == 1
    assert len(store._listeners) == 0


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=path, check=True)
    (path / "f.txt").write_text("line1\nline2\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def test_from_repo_and_commit(client, tmp_path, monkeypatch):
    repos_dir = tmp_path / "repos"
    repo = repos_dir / "myrepo"
    _init_repo(repo)
    monkeypatch.setenv("AW_APP_DIFF_TOOL_ROOT", str(tmp_path))

    (repo / "f.txt").write_text("line1\nline2\nline3\n")

    resp = client.post("/diffs/render", json={"repo": "myrepo", "title": "T"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    diff_id = body["diff_id"]

    html_resp = client.get(f"/diffs/{diff_id}/html")
    assert html_resp.status_code == 200
    assert "commit-panel" in html_resp.text
    assert "line3" in html_resp.text

    commit_resp = client.post("/commit", json={
        "repo_dir": "myrepo", "files": ["f.txt"], "message": "test commit", "push": False,
    })
    assert commit_resp.status_code == 200
    commit_body = commit_resp.json()
    assert commit_body["success"] is True
    assert commit_body["files_committed"] == 1


def test_from_repo_no_changes(client, tmp_path, monkeypatch):
    repos_dir = tmp_path / "repos"
    repo = repos_dir / "clean"
    _init_repo(repo)
    monkeypatch.setenv("AW_APP_DIFF_TOOL_ROOT", str(tmp_path))

    resp = client.post("/diffs/render", json={"repo": "clean"})
    assert resp.status_code == 200
    assert resp.json()["success"] is False


def test_commit_unknown_repo(client):
    resp = client.post("/commit", json={
        "repo_dir": "not-a-repo-anywhere", "files": ["f.txt"], "message": "m",
    })
    assert resp.status_code == 400


def test_activate_sets_broadcast_loop_without_relying_on_asgi_startup():
    import asyncio

    from diff_app.plugin import DiffToolAppPlugin

    class Ctx:
        def __init__(self):
            self._on_deactivate = None

        def on_deactivate(self, fn):
            self._on_deactivate = fn

        routes = type("R", (), {"register": staticmethod(lambda subapp: None)})()

    async def run():
        ctx = Ctx()
        plugin = DiffToolAppPlugin()
        await plugin.activate(ctx)
        assert plugin.store._loop is asyncio.get_running_loop()

    asyncio.run(run())
