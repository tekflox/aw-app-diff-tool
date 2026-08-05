"""Diff viewer HTML generation, ported verbatim from the monolith's
``src/mcp/presentation/diff_viewer.py`` (unified-diff parsing + the
self-contained interactive HTML/CSS/JS generator: multi-file tabs,
unified/split view toggle, GitHub-style collapsible context regions,
inline word-diff highlighting, embedded Commit & Push panel).

Only change from the monolith version: the embedded JS's Commit & Push
panel now POSTs to a same-origin, app-relative ``COMMIT_PATH`` (this app's
own ``/commit`` route) instead of the monolith's hardcoded
``/api/git/commit`` + ``x-api-key`` header — the iframe is served under
this app's own mount and inherits the parent dashboard's origin/cookies
(same reasoning as the monolith's ``api_base=""`` relative-URL comment
below), so no API key is needed.
"""

import html
import os
import re
import subprocess


def parse_unified_diff(diff_text):
    """Parse a unified diff into structured hunks.

    Returns list of dicts: {old_start, old_count, new_start, new_count, header, lines}
    Each line: {type: 'context'|'added'|'removed', old_num, new_num, content}
    """
    hunks = []
    current_hunk = None
    old_num = 0
    new_num = 0

    for raw_line in diff_text.splitlines():
        m = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)', raw_line)
        if m:
            if current_hunk:
                hunks.append(current_hunk)
            old_num = int(m.group(1))
            new_num = int(m.group(3))
            current_hunk = {
                "old_start": old_num,
                "old_count": int(m.group(2) or 1),
                "new_start": new_num,
                "new_count": int(m.group(4) or 1),
                "header": raw_line,
                "context_label": m.group(5).strip(),
                "lines": [],
            }
            continue

        if current_hunk is None:
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            current_hunk["lines"].append({
                "type": "added",
                "old_num": None,
                "new_num": new_num,
                "content": raw_line[1:],
            })
            new_num += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            current_hunk["lines"].append({
                "type": "removed",
                "old_num": old_num,
                "new_num": None,
                "content": raw_line[1:],
            })
            old_num += 1
        elif raw_line.startswith("\\"):
            continue
        else:
            content = raw_line[1:] if raw_line.startswith(" ") else raw_line
            current_hunk["lines"].append({
                "type": "context",
                "old_num": old_num,
                "new_num": new_num,
                "content": content,
            })
            old_num += 1
            new_num += 1

    if current_hunk:
        hunks.append(current_hunk)

    return hunks


def _esc(text):
    """HTML-escape text."""
    return html.escape(text) if text else ""


def _read_file(file_path):
    """Read file lines, return list of strings (no trailing newline)."""
    try:
        with open(file_path, "r") as f:
            return [line.rstrip("\n") for line in f.readlines()]
    except (FileNotFoundError, PermissionError, UnicodeDecodeError):
        return None


def compute_git_diff(file_path, ref=None):
    """Run git diff and return the raw output."""
    abs_path = os.path.abspath(file_path)
    # Walk up to the nearest existing directory (handles deleted files whose
    # parent directory was also removed).
    cwd = os.path.dirname(abs_path)
    while cwd and cwd != "/" and not os.path.isdir(cwd):
        cwd = os.path.dirname(cwd)
    if not cwd or not os.path.isdir(cwd):
        return ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=cwd,
        )
        repo_root = result.stdout.strip()
    except Exception:
        repo_root = cwd

    rel_path = os.path.relpath(abs_path, repo_root)

    cmd = ["git", "diff"]
    if ref:
        cmd.append(ref)
    cmd.append("--")
    cmd.append(rel_path)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)
    if result.stdout:
        return result.stdout

    result = subprocess.run(
        ["git", "diff", "--no-index", "/dev/null", rel_path],
        capture_output=True, text=True, cwd=repo_root,
    )
    return result.stdout


def _get_diff_stats(hunks):
    """Count additions and removals."""
    added = sum(1 for h in hunks for l in h["lines"] if l["type"] == "added")
    removed = sum(1 for h in hunks for l in h["lines"] if l["type"] == "removed")
    return added, removed


def generate_diff_html(files_data, repo_dir=None, commit_path=None):
    """Generate full diff viewer HTML for one or more files.

    files_data: list of {file_path, diff_text, file_lines (optional), rel_path (optional)}
    repo_dir: git repo root (enables commit UI)
    commit_path: same-origin, app-relative path this app's own POST /commit
      route is reachable at (e.g. "/api/apps/diff-tool/commit") — only used
      when repo_dir is set.
    Returns HTML string.
    """
    css = _generate_css()

    file_meta = []
    total_added = 0
    total_removed = 0

    tabs_html = ""
    content_html = ""

    for idx, fd in enumerate(files_data):
        file_path = fd["file_path"]
        diff_text = fd["diff_text"]
        file_lines = fd.get("file_lines") or _read_file(file_path) or []
        rel_path = fd.get("rel_path", os.path.basename(file_path))
        fname = os.path.basename(file_path)

        hunks = parse_unified_diff(diff_text)
        added, removed = _get_diff_stats(hunks)
        total_added += added
        total_removed += removed

        file_meta.append({"path": rel_path, "name": fname, "added": added, "removed": removed})

        active = "active" if idx == 0 else ""
        tabs_html += f'<button class="tab {active}" onclick="switchTab({idx})">{_esc(fname)} <span class="tab-stats">+{added} -{removed}</span></button>'

        hidden = "" if idx == 0 else "hidden"
        file_content = _generate_file_content(file_path, hunks, file_lines, added, removed, file_idx=idx)
        content_html += f'<div id="file-{idx}" class="file-panel {hidden}">{file_content}</div>'

    tabs_bar = ""
    if len(files_data) > 1:
        tabs_bar = f'<div class="tabs-bar">{tabs_html}</div>'

    commit_html = ""
    if repo_dir:
        if total_added > 0 and total_removed == 0:
            prefix = "feat"
        elif total_removed > 0 and total_added == 0:
            prefix = "refactor"
        else:
            prefix = "fix"
        file_names = ", ".join(m["name"] for m in file_meta[:3])
        if len(file_meta) > 3:
            file_names += f" +{len(file_meta) - 3} more"
        suggested_msg = f"{prefix}: update {file_names}"

        file_checkboxes = ""
        for i, m in enumerate(file_meta):
            file_checkboxes += f'''<label class="commit-file">
                <input type="checkbox" checked data-path="{_esc(m['path'])}" class="commit-file-cb">
                <span class="commit-fname">{_esc(m['name'])}</span>
                <span class="commit-fstats"><span class="add">+{m['added']}</span> <span class="del">-{m['removed']}</span></span>
            </label>'''

        commit_html = f'''
        <div class="commit-panel" id="commit-panel">
            <div class="commit-header">
                <span class="commit-title">Commit Changes</span>
                <span class="commit-summary">{len(file_meta)} files, +{total_added} -{total_removed}</span>
            </div>
            <div class="commit-files">{file_checkboxes}</div>
            <textarea class="commit-msg" id="commit-msg" placeholder="Commit message..." rows="5">{_esc(suggested_msg)}</textarea>
            <div class="commit-actions">
                <label class="commit-push-label">
                    <input type="checkbox" id="commit-push" checked>
                    Push after commit
                </label>
                <button class="commit-btn" id="commit-btn" onclick="doCommit()">Commit</button>
            </div>
            <div class="commit-result hidden" id="commit-result"></div>
        </div>'''

    js = _generate_js(repo_dir, commit_path)

    toggle_html = ""
    if repo_dir:
        toggle_html = '''<div class="commit-toggle-bar" id="commit-toggle" onclick="toggleCommitPanel()">
            <span class="commit-toggle-arrow" id="commit-arrow">▼</span>
            <span class="commit-toggle-label">Commit &amp; Push</span>
        </div>'''

    return f"""<!DOCTYPE html>
<html>
<head><style>{css}</style></head>
<body>
{tabs_bar}
<div class="diff-scroll">
{content_html}
</div>
{toggle_html}
{commit_html}
<script>{js}</script>
</body>
</html>"""


def _generate_file_content(file_path, hunks, file_lines, added, removed, file_idx=0):
    """Generate the content for a single file with expand/collapse in both views."""
    total = len(file_lines) if file_lines else "?"

    CONTEXT = 3
    unified_html = ""
    _fprefix = f"f{file_idx}"
    collapse_id = 0
    current_new = 1

    def _emit_unified_hunk(h):
        """Render a hunk's lines in unified format (context + removed + added)."""
        out = ""
        for l in h["lines"]:
            cls = l["type"]
            old = l["old_num"] or ""
            new = l["new_num"] or ""
            marker = "+" if cls == "added" else ("-" if cls == "removed" else " ")
            content = _esc(l["content"]) or " "
            if cls == "added":
                content = f'<span class="hl-add">{content}</span>'
            elif cls == "removed":
                content = f'<span class="hl-del">{content}</span>'
            out += f'<div class="diff-line {cls}"><div class="ln">{old}</div><div class="ln">{new}</div><div class="lc"><span class="m">{marker}</span>{content}</div></div>'
        return out

    if file_lines:
        for hi, h in enumerate(hunks):
            hunk_start = h["new_start"]
            ctx_start = max(1, hunk_start - CONTEXT)

            if current_new < ctx_start:
                count = ctx_start - current_new
                cid = f"{_fprefix}-u{collapse_id}"
                collapse_id += 1
                unified_html += f'<div class="collapse-bar" onclick="toggleCollapse(\'{cid}\')"><span class="collapse-icon" id="cicon-{cid}">&#9654;</span> {count} lines ({current_new}-{ctx_start - 1})</div>'
                unified_html += f'<div class="collapse-content hidden" id="ccontent-{cid}">'
                for n in range(current_new, ctx_start):
                    content = _esc(file_lines[n - 1]) if n <= len(file_lines) else " "
                    unified_html += f'<div class="diff-line context"><div class="ln">{n}</div><div class="ln">{n}</div><div class="lc"><span class="m"> </span>{content or " "}</div></div>'
                unified_html += '</div>'

            for n in range(ctx_start, hunk_start):
                if n >= current_new and n <= len(file_lines):
                    content = _esc(file_lines[n - 1]) or " "
                    unified_html += f'<div class="diff-line context"><div class="ln">{n}</div><div class="ln">{n}</div><div class="lc"><span class="m"> </span>{content}</div></div>'

            unified_html += f'<div class="hunk-header">{_esc(h["header"])}</div>'
            unified_html += _emit_unified_hunk(h)

            hunk_end_new = hunk_start + h["new_count"]
            ctx_end = min(len(file_lines) + 1, hunk_end_new + CONTEXT)
            next_hunk_start = hunks[hi + 1]["new_start"] if hi + 1 < len(hunks) else len(file_lines) + 1
            ctx_end = min(ctx_end, max(1, next_hunk_start - CONTEXT))
            for n in range(hunk_end_new, ctx_end):
                if n <= len(file_lines):
                    content = _esc(file_lines[n - 1]) or " "
                    unified_html += f'<div class="diff-line context"><div class="ln">{n}</div><div class="ln">{n}</div><div class="lc"><span class="m"> </span>{content}</div></div>'
            current_new = ctx_end

        if current_new <= len(file_lines):
            count = len(file_lines) - current_new + 1
            cid = f"{_fprefix}-u{collapse_id}"
            collapse_id += 1
            unified_html += f'<div class="collapse-bar" onclick="toggleCollapse(\'{cid}\')"><span class="collapse-icon" id="cicon-{cid}">&#9654;</span> {count} lines ({current_new}-{len(file_lines)})</div>'
            unified_html += f'<div class="collapse-content hidden" id="ccontent-{cid}">'
            for n in range(current_new, len(file_lines) + 1):
                content = _esc(file_lines[n - 1]) or " "
                unified_html += f'<div class="diff-line context"><div class="ln">{n}</div><div class="ln">{n}</div><div class="lc"><span class="m"> </span>{content}</div></div>'
            unified_html += '</div>'
    else:
        for h in hunks:
            unified_html += f'<div class="hunk-header">{_esc(h["header"])}</div>'
            unified_html += _emit_unified_hunk(h)

    split_html = ""
    collapse_id = 0

    def _render_split_hunk(h):
        """Render a hunk as paired left/right rows."""
        rows = []
        left_buf = []
        right_buf = []

        for l in h["lines"]:
            if l["type"] == "context":
                rows.extend(_pair_buffers(left_buf, right_buf))
                left_buf, right_buf = [], []
                content = _esc(l["content"]) or " "
                rows.append(f'<div class="split-row"><div class="side context"><div class="ln">{l["old_num"] or ""}</div><div class="lc">{content}</div></div><div class="side context"><div class="ln">{l["new_num"] or ""}</div><div class="lc">{content}</div></div></div>')
            elif l["type"] == "removed":
                left_buf.append(l)
            elif l["type"] == "added":
                right_buf.append(l)

        rows.extend(_pair_buffers(left_buf, right_buf))
        return "\n".join(rows)

    def _pair_buffers(left_buf, right_buf):
        """Pair up removed (left) and added (right) lines, padding the shorter side."""
        rows = []
        max_len = max(len(left_buf), len(right_buf))
        for j in range(max_len):
            left = left_buf[j] if j < len(left_buf) else None
            right = right_buf[j] if j < len(right_buf) else None
            l_cls = "removed" if left else "empty-side"
            r_cls = "added" if right else "empty-side"
            l_num = left["old_num"] if left else ""
            r_num = right["new_num"] if right else ""
            l_content = _esc(left["content"]) if left else " "
            r_content = _esc(right["content"]) if right else " "
            if left and left["type"] == "removed":
                l_content = f'<span class="hl-del">{l_content or " "}</span>'
            if right and right["type"] == "added":
                r_content = f'<span class="hl-add">{r_content or " "}</span>'
            if not l_content.strip():
                l_content = " "
            if not r_content.strip():
                r_content = " "
            rows.append(f'<div class="split-row"><div class="side {l_cls}"><div class="ln">{l_num}</div><div class="lc">{l_content}</div></div><div class="side {r_cls}"><div class="ln">{r_num}</div><div class="lc">{r_content}</div></div></div>')
        return rows

    if file_lines:
        current_new = 1
        for hi, h in enumerate(hunks):
            hunk_start = h["new_start"]
            ctx_start = max(1, hunk_start - CONTEXT)
            if current_new < ctx_start:
                count = ctx_start - current_new
                cid = f"{_fprefix}-s{collapse_id}"
                collapse_id += 1
                split_html += f'<div class="collapse-bar" onclick="toggleCollapse(\'{cid}\')"><span class="collapse-icon" id="cicon-{cid}">&#9654;</span> {count} lines ({current_new}-{ctx_start - 1})</div>'
                split_html += f'<div class="collapse-content hidden" id="ccontent-{cid}">'
                for n in range(current_new, ctx_start):
                    content = _esc(file_lines[n - 1]) if n <= len(file_lines) else " "
                    split_html += f'<div class="split-row"><div class="side context"><div class="ln">{n}</div><div class="lc">{content or " "}</div></div><div class="side context"><div class="ln">{n}</div><div class="lc">{content or " "}</div></div></div>'
                split_html += '</div>'

            for n in range(ctx_start, hunk_start):
                if n >= current_new and n <= len(file_lines):
                    content = _esc(file_lines[n - 1]) or " "
                    split_html += f'<div class="split-row"><div class="side context"><div class="ln">{n}</div><div class="lc">{content}</div></div><div class="side context"><div class="ln">{n}</div><div class="lc">{content}</div></div></div>'

            split_html += f'<div class="hunk-header">{_esc(h["header"])}</div>'
            split_html += _render_split_hunk(h)

            hunk_end_new = hunk_start + h["new_count"]
            ctx_end = min(len(file_lines) + 1, hunk_end_new + CONTEXT)
            next_hunk_start = hunks[hi + 1]["new_start"] if hi + 1 < len(hunks) else len(file_lines) + 1
            ctx_end = min(ctx_end, max(1, next_hunk_start - CONTEXT))
            for n in range(hunk_end_new, ctx_end):
                if n <= len(file_lines):
                    content = _esc(file_lines[n - 1]) or " "
                    split_html += f'<div class="split-row"><div class="side context"><div class="ln">{n}</div><div class="lc">{content}</div></div><div class="side context"><div class="ln">{n}</div><div class="lc">{content}</div></div></div>'
            current_new = ctx_end

        if current_new <= len(file_lines):
            count = len(file_lines) - current_new + 1
            cid = f"{_fprefix}-s{collapse_id}"
            collapse_id += 1
            split_html += f'<div class="collapse-bar" onclick="toggleCollapse(\'{cid}\')"><span class="collapse-icon" id="cicon-{cid}">&#9654;</span> {count} lines ({current_new}-{len(file_lines)})</div>'
            split_html += f'<div class="collapse-content hidden" id="ccontent-{cid}">'
            for n in range(current_new, len(file_lines) + 1):
                content = _esc(file_lines[n - 1]) or " "
                split_html += f'<div class="split-row"><div class="side context"><div class="ln">{n}</div><div class="lc">{content}</div></div><div class="side context"><div class="ln">{n}</div><div class="lc">{content}</div></div></div>'
            split_html += '</div>'
    else:
        for h in hunks:
            split_html += f'<div class="hunk-header">{_esc(h["header"])}</div>'
            split_html += _render_split_hunk(h)

    return f"""
    <div class="file-header">
        <div class="file-info">
            <div class="file-path">{_esc(file_path)}</div>
            <div class="file-stats"><span class="add">+{added}</span> <span class="del">-{removed}</span> &bull; {total} lines</div>
        </div>
        <div class="view-toggle">
            <button class="vbtn" onclick="setFileView(this, 'unified')">Unified</button>
            <button class="vbtn active" onclick="setFileView(this, 'split')">Split</button>
        </div>
    </div>
    <div class="view-unified hidden">{unified_html}</div>
    <div class="view-split">{split_html}</div>
    <div class="file-footer">
        <span class="dot dot-add"></span> {added} additions
        <span class="dot dot-del"></span> {removed} removals
        <span style="margin-left:auto;color:#58a6ff">{len(hunks)} hunks</span>
    </div>
    """


def _generate_css():
    return """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { height: 100%; }
    body { background: #0c0d11; color: #d4d4d8; font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace; font-size: 13px; line-height: 1.5; display: flex; flex-direction: column; }
    .diff-scroll { flex: 1; overflow-y: auto; min-height: 0; }

    /* Tabs — pierre-style flat tabs */
    .tabs-bar { background: #18191e; border-bottom: 1px solid #27282e; padding: 0 8px; display: flex; overflow-x: auto; gap: 0; }
    .tab { padding: 10px 16px; font-size: 12px; font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: none; color: #71717a; border: none; border-bottom: 2px solid transparent; cursor: pointer; white-space: nowrap; transition: color 0.15s; }
    .tab.active { color: #e4e4e7; border-bottom-color: #6366f1; }
    .tab:hover:not(.active) { color: #a1a1aa; }
    .tab-stats { font-size: 10px; color: #52525b; margin-left: 6px; }
    .tab.active .tab-stats { color: #71717a; }

    /* File header — clean, minimal */
    .file-header { background: #18191e; border-bottom: 1px solid #27282e; padding: 10px 16px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 10; }
    .file-path { font-size: 13px; font-weight: 500; color: #e4e4e7; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
    .file-stats { font-size: 12px; color: #71717a; margin-top: 2px; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
    .file-stats .add { color: #4ade80; font-weight: 600; }
    .file-stats .del { color: #f87171; font-weight: 600; }
    .view-toggle { display: flex; border: 1px solid #27282e; border-radius: 6px; overflow: hidden; }
    .vbtn { padding: 5px 14px; font-size: 11px; font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0c0d11; color: #71717a; border: none; cursor: pointer; transition: all 0.15s; }
    .vbtn:not(:last-child) { border-right: 1px solid #27282e; }
    .vbtn.active { background: #6366f1; color: #fff; }
    .vbtn:hover:not(.active) { background: #1e1f26; color: #a1a1aa; }

    /* Hunk header — pierre-style blue bar */
    .hunk-header { background: #1a1c2e; color: #818cf8; padding: 5px 16px; font-size: 11px; border-top: 1px solid #27282e; letter-spacing: 0.01em; }

    /* Lines — vertical bar indicator style (pierre-inspired) */
    .diff-line { display: flex; min-height: 20px; line-height: 20px; }
    .ln { width: 48px; text-align: right; padding: 0 8px; color: #3f3f46; flex-shrink: 0; font-size: 11px; user-select: none; }
    .lc { flex: 1; padding: 0 12px; white-space: pre; overflow-x: auto; font-size: 13px; border-left: 3px solid transparent; }
    .m { display: none; } /* hide +/- markers, use bar indicator instead */

    /* Context */
    .context { background: #0c0d11; }
    .context .lc { color: #71717a; border-left-color: transparent; }
    .context:hover { background: #12131a; }

    /* Added — green bar + tinted background */
    .added { background: #0c1f17; }
    .added .ln { color: #4ade80; }
    .added .lc { color: #bbf7d0; border-left-color: #22c55e; }
    .added:hover { background: #0f2a1d; }

    /* Removed — red bar + tinted background */
    .removed { background: #1f0c0e; }
    .removed .ln { color: #f87171; }
    .removed .lc { color: #fecaca; border-left-color: #ef4444; }
    .removed:hover { background: #2a0f12; }

    /* Inline word highlights */
    .hl-add { background: rgba(34, 197, 94, 0.2); border-radius: 2px; padding: 0 2px; }
    .hl-del { background: rgba(239, 68, 68, 0.2); border-radius: 2px; padding: 0 2px; }

    /* Split view */
    .split-row { display: flex; min-height: 20px; line-height: 20px; }
    .side { flex: 1; display: flex; min-width: 0; }
    .side + .side { border-left: 1px solid #27282e; }
    .empty-side { background: #16171d; }
    .empty-side .ln { color: transparent; }
    .empty-side .lc { color: transparent; border-left-color: transparent; }

    /* Collapse bars — pierre-style hunk separator */
    .collapse-bar {
        background: #16171d; color: #6366f1; padding: 6px 16px; font-size: 11px;
        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
        cursor: pointer; user-select: none; border-top: 1px solid #27282e;
        border-bottom: 1px solid #27282e; display: flex; align-items: center; gap: 8px;
        transition: background 0.15s;
    }
    .collapse-bar:hover { background: #1c1d24; }
    .collapse-icon { display: inline-flex; align-items: center; justify-content: center;
        width: 18px; height: 18px; border-radius: 4px; background: #27282e;
        font-size: 8px; transition: all 0.2s; color: #a1a1aa; }
    .collapse-icon.open { transform: rotate(90deg); background: #6366f1; color: #fff; }

    /* Footer */
    .file-footer { display: flex; gap: 16px; padding: 8px 16px; background: #18191e;
        border-top: 1px solid #27282e; font-size: 11px; color: #71717a; align-items: center;
        font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
    .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }
    .dot-add { background: #22c55e; }
    .dot-del { background: #ef4444; }

    /* Commit toggle bar */
    .commit-toggle-bar { background: #18191e; border-top: 1px solid #27282e; padding: 6px 16px; display: flex; align-items: center; cursor: pointer; user-select: none; flex-shrink: 0; }
    .commit-toggle-bar:hover { background: #1e1f26; }
    .commit-toggle-arrow { color: #6366f1; font-size: 11px; margin-right: 8px; transition: transform 0.2s; display: inline-block; }
    .commit-toggle-bar.collapsed .commit-toggle-arrow { transform: rotate(-90deg); }
    .commit-toggle-label { font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 12px; color: #a1a1aa; font-weight: 500; }

    /* Commit panel */
    .commit-panel { background: #18191e; border-top: 2px solid #6366f1; padding: 16px; flex-shrink: 0; }
    .commit-panel.hidden { display: none !important; }
    .commit-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }
    .commit-title { font-size: 14px; font-weight: 600; color: #e4e4e7; }
    .commit-summary { font-size: 12px; color: #71717a; }
    .commit-files { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; max-height: 150px; overflow-y: auto; }
    .commit-file { display: flex; align-items: center; gap: 8px; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 12px; color: #a1a1aa; }
    .commit-file:hover { background: #1e1f26; }
    .commit-file-cb { accent-color: #6366f1; }
    .commit-fname { flex: 1; font-family: ui-monospace, monospace; font-size: 12px; color: #d4d4d8; }
    .commit-fstats { font-size: 11px; }
    .commit-fstats .add { color: #4ade80; }
    .commit-fstats .del { color: #f87171; }
    .commit-msg { width: 100%; background: #111318; border: 1px solid #27282e; border-radius: 6px; padding: 8px 12px; color: #e4e4e7; font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 13px; resize: vertical; min-height: 5lh; outline: none; }
    .commit-msg:focus { border-color: #6366f1; }
    .commit-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; }
    .commit-push-label { font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 12px; color: #a1a1aa; display: flex; align-items: center; gap: 6px; cursor: pointer; }
    .commit-push-label input { accent-color: #6366f1; }
    .commit-btn { background: #6366f1; color: #fff; border: none; padding: 8px 24px; border-radius: 6px; font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 13px; font-weight: 600; cursor: pointer; transition: background 0.15s; }
    .commit-btn:hover { background: #4f46e5; }
    .commit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .commit-result { margin-top: 10px; padding: 10px 12px; border-radius: 6px; font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 12px; }
    .commit-result.success { background: rgba(34,197,94,0.1); color: #4ade80; border: 1px solid rgba(34,197,94,0.2); }
    .commit-result.error { background: rgba(239,68,68,0.1); color: #f87171; border: 1px solid rgba(239,68,68,0.2); }

    .hidden { display: none !important; }
    """


def _generate_js(repo_dir=None, commit_path=None):
    import json as _json
    repo_dir_js = _json.dumps(repo_dir or "")
    commit_path_js = _json.dumps(commit_path or "/commit")

    return f"""
    const REPO_DIR = {repo_dir_js};
    const COMMIT_PATH = {commit_path_js};

    function toggleCommitPanel() {{
        const panel = document.getElementById('commit-panel');
        const bar = document.getElementById('commit-toggle');
        if (!panel || !bar) return;
        const hidden = panel.classList.toggle('hidden');
        bar.classList.toggle('collapsed', hidden);
    }}

    function switchTab(idx) {{
        document.querySelectorAll('.tab').forEach((t, i) => t.classList.toggle('active', i === idx));
        document.querySelectorAll('.file-panel').forEach((p, i) => p.classList.toggle('hidden', i !== idx));
    }}

    function setFileView(btn, mode) {{
        const panel = btn.closest('.file-panel') || document.body;
        const u = panel.querySelector('.view-unified');
        const s = panel.querySelector('.view-split');
        if (u) u.classList.toggle('hidden', mode !== 'unified');
        if (s) s.classList.toggle('hidden', mode !== 'split');
        panel.querySelectorAll('.vbtn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }}

    function toggleCollapse(id) {{
        const content = document.getElementById('ccontent-' + id);
        const icon = document.getElementById('cicon-' + id);
        if (content) content.classList.toggle('hidden');
        if (icon) icon.classList.toggle('open');
    }}

    async function doCommit() {{
        const btn = document.getElementById('commit-btn');
        const resultEl = document.getElementById('commit-result');
        const msg = document.getElementById('commit-msg').value.trim();
        const push = document.getElementById('commit-push').checked;

        if (!msg) {{
            resultEl.textContent = 'Commit message is required';
            resultEl.className = 'commit-result error';
            resultEl.classList.remove('hidden');
            return;
        }}

        const files = [];
        document.querySelectorAll('.commit-file-cb:checked').forEach(cb => {{
            files.push(cb.dataset.path);
        }});

        if (files.length === 0) {{
            resultEl.textContent = 'No files selected';
            resultEl.className = 'commit-result error';
            resultEl.classList.remove('hidden');
            return;
        }}

        btn.disabled = true;
        btn.textContent = push ? 'Committing & pushing...' : 'Committing...';
        resultEl.classList.add('hidden');

        try {{
            const resp = await fetch(COMMIT_PATH, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    repo_dir: REPO_DIR,
                    files: files,
                    message: msg,
                    push: push,
                }}),
            }});
            const data = await resp.json();

            if (data.success) {{
                resultEl.innerHTML = '<strong>✓ ' + (push ? 'Committed & pushed' : 'Committed') + '</strong>'
                    + '<br>' + data.commit_hash + ' on ' + data.branch
                    + '<br>' + data.files_committed + ' files';
                resultEl.className = 'commit-result success';
                btn.textContent = '✓ Done';
            }} else {{
                resultEl.textContent = data.error || 'Unknown error';
                resultEl.className = 'commit-result error';
                btn.textContent = 'Commit';
                btn.disabled = false;
            }}
        }} catch (e) {{
            resultEl.textContent = 'Network error: ' + e.message;
            resultEl.className = 'commit-result error';
            btn.textContent = 'Commit';
            btn.disabled = false;
        }}
        resultEl.classList.remove('hidden');
    }}
    """
