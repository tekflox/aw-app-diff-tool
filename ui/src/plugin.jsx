// Integrated-mode entrypoint — dynamic-imported by aw-workspace-ui's
// loadComponentPlugin() once this app is installed with "ui:code" +
// "ui:slots:core.nav" + "ui:slots:core.window.body:diff-tool.viewer" granted.
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
// 2. DiffWindowActions -> core.window.titlebar:diff-tool.viewer. The pop-out
//    button, registered via host.registerWindowActions so it lands in the
//    HOST's title bar. It used to be a second full-width bar drawn above the
//    iframe in (3), back when a window's chrome was closed to apps — two
//    stacked headers for a single icon. Same move aw-app-whiteboard made.
//
// 3. DiffWindowBody -> core.window.body:diff-tool.viewer. Like Presentations,
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
            window.__awOpenAppWindow?.('diff-tool.viewer', msg.diff.id, msg.diff.title);
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

  // The diff's own HTML page is reached the same way from the title-bar
  // action and the body's iframe. Absolute URL required — <iframe src> and
  // window.open() are resolved directly by the browser, bypassing the
  // fetch/XHR-only apiBase.js rewrite shim a relative path depends on (same
  // class of bug fixed in Whiteboard/Presentations/RepoNav — see
  // aw-workspace-ui's pluginHost.js host.app.absoluteApiUrl doc comment).
  const diffHtmlUrl = (diffId) => (diffId ? host.app.absoluteApiUrl(`/diffs/${diffId}/html`) : null);

  // ------------------------------------------------------------------
  // 2. Title-bar actions — pop out to a real browser window
  // ------------------------------------------------------------------
  // A SIBLING slot contribution to the body below, not its parent: the host
  // renders this inside its own header (core.window.titlebar:diff-tool.viewer)
  // and the body under it. Nothing is shared between the two, so no
  // cross-component plumbing is needed here (unlike Whiteboard's export, which
  // has to reach the body's iframe) — both just derive the URL from instanceId.
  //
  // No Maximize/Close here on purpose — the host's header already has them.
  function DiffWindowActions({ instanceId }) {
    const htmlUrl = diffHtmlUrl(instanceId);
    if (!htmlUrl) return null;
    return (
      <button
        onClick={() => window.open(htmlUrl, `diff-${instanceId}`, 'popup=1,width=1100,height=750')}
        className="p-1 rounded hover:bg-white/10 text-[var(--color-text-muted)]"
        title="Pop out to new window"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" />
        </svg>
      </button>
    );
  }

  // ------------------------------------------------------------------
  // 3. Window body — one per open diff (instanceId = diff id)
  // ------------------------------------------------------------------
  // Just the iframe now: BasicWindow.jsx supplies the chrome (title, maximize,
  // close) and the pop-out button moved up into it, so the window has one
  // header instead of two and the diff gets that ~29px back.
  function DiffWindowBody({ instanceId }) {
    const htmlUrl = diffHtmlUrl(instanceId);

    return (
      <div className="flex flex-col bg-[var(--color-bg-secondary)] h-full">
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
  host.registerWindow('diff-tool.viewer', DiffWindowBody);
  // Needs an aw-workspace-ui new enough to expose it (and to render the
  // core.window.titlebar:<id> slot at all) — on an older host this is simply
  // absent, and the window keeps its single header with no app buttons
  // rather than throwing during register().
  host.registerWindowActions?.('diff-tool.viewer', DiffWindowActions);
}

export default register;
