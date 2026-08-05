// Integrated-mode entrypoint — dynamic-imported by aw-workspace-ui's
// loadComponentPlugin() once this app is installed with "ui:code" +
// "ui:slots:core.nav" + "ui:slots:core.window.body:diff.viewer" granted.
// Built by `npm run build` -> ui/dist/diff-tool-ui.mjs, referenced from
// aw-app.json's contributes.frontend.bundle. Same register(host)/JSX-factory
// pattern as aw-app-presentations/aw-app-whiteboard/aw-app-tasks's
// plugin.jsx.
//
// Owns BOTH contributions this app makes to the SPA:
//
// 1. DiffToolListener -> core.nav. Renders NOTHING (returns null) — there
//    is no standing "Diff" button in the top bar (per the 2026-08-05
//    decision: this app only opens via an agent's show_diff MCP call or
//    the git-repo-nav's expand arrow, never a nav entry a user clicks to
//    browse a list). It still needs to occupy a slot to stay mounted for
//    the lifetime of the SPA, because it owns the standing WebSocket that
//    makes the FIRST entry point work: when an agent (running headless,
//    possibly in a completely different session) calls show_diff, nobody
//    in the user's browser tab triggered that — the only way the window
//    opens automatically is this listener reacting to the diff_open
//    broadcast. The SECOND entry point (the git-nav arrow) doesn't need
//    this at all — it gets a diff_id straight back from its own POST
//    response and can call window.__awOpenAppWindow directly — but reusing
//    the same broadcast keeps both entry points on one code path.
//
// 2. DiffWindowBody -> core.window.body:diff.viewer. Like Presentations,
//    this app opens MANY windows at once — one per diff id. Uses the
//    2026-08-05 framework addition: window.__awOpenAppWindow(windowId,
//    instanceId, title) keys the window as `appwin:<windowId>:<instanceId>`
//    instead of the bare singleton `appwin:<windowId>`. Unlike
//    Presentations, the diff's own HTML is a static, fully-formed page (no
//    rename/share/export chrome needed) — the window body is a thin iframe
//    wrapper.

export function register(host) {
  const { useEffect } = host.React;

  // ------------------------------------------------------------------
  // 1. Headless WS listener -> core.nav (renders nothing, stays mounted)
  // ------------------------------------------------------------------
  function DiffToolListener() {
    useEffect(() => {
      let ws, reconnectTimer, closed = false;
      const connect = () => {
        try {
          ws = new WebSocket(host.app.wsUrl('/ws'));
          ws.onmessage = (event) => {
            let msg;
            try { msg = JSON.parse(event.data); } catch { return; }
            if (msg.type !== 'diff_open' || !msg.diff) return;
            window.__awOpenAppWindow?.('diff.viewer', msg.diff.id, msg.diff.title);
          };
          ws.onclose = () => { if (!closed) reconnectTimer = setTimeout(connect, 5000); };
          ws.onerror = () => { try { ws.close(); } catch {} };
        } catch {
          if (!closed) reconnectTimer = setTimeout(connect, 5000);
        }
      };
      connect();
      return () => {
        closed = true;
        clearTimeout(reconnectTimer);
        if (ws) { ws.onclose = null; try { ws.close(); } catch {} }
      };
    }, []);

    return null;
  }

  // ------------------------------------------------------------------
  // 2. Window body — one per open diff (instanceId = diff id)
  // ------------------------------------------------------------------
  // BasicWindow.jsx already supplies the window chrome (title, maximize,
  // close) around this slot — unlike Presentations (editable title, share,
  // export), a diff window needs no extra chrome of its own, so this is
  // just the iframe plus one genuinely new action (pop out to a real
  // browser window/tab, useful for a wide side-by-side split view).
  function DiffWindowBody({ instanceId }) {
    const diffId = instanceId;

    // Absolute URL required — <iframe src> and window.open() are resolved
    // directly by the browser, bypassing the fetch/XHR-only apiBase.js
    // rewrite shim a relative path depends on (same class of bug fixed in
    // Whiteboard/Presentations/RepoNav — see aw-workspace-ui's
    // pluginHost.js host.app.absoluteApiUrl doc comment).
    const htmlUrl = diffId ? host.app.absoluteApiUrl(`/diffs/${diffId}/html`) : null;

    return (
      <div className="flex flex-col bg-[var(--color-bg-secondary)] h-full">
        <div className="flex items-center justify-end px-2 py-1 border-b border-[var(--color-border)] shrink-0" onMouseDown={(e) => e.stopPropagation()}>
          <button
            onClick={() => { if (htmlUrl) window.open(htmlUrl, `diff-${diffId}`, 'popup=1,width=1100,height=750'); }}
            className="p-1.5 rounded hover:bg-white/10 transition-colors"
            title="Pop out to new window"
          >
            <svg className="w-4 h-4 text-[var(--color-text-muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" />
            </svg>
          </button>
        </div>
        <div className="flex-1 relative">
          {htmlUrl && (
            <iframe
              src={htmlUrl}
              className="absolute inset-0 w-full h-full bg-white border-0"
              title="Diff"
              sandbox="allow-scripts allow-same-origin allow-forms"
            />
          )}
        </div>
      </div>
    );
  }

  host.registerSlot('core.nav', DiffToolListener);
  host.registerWindow('diff.viewer', DiffWindowBody);
}

export default register;
