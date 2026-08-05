function d(e) {
  const { useEffect: a } = e.React;
  function f() {
    return a(() => {
      let o, r, t = !1;
      const i = () => {
        try {
          o = new WebSocket(e.app.wsUrl("/ws")), o.onmessage = (s) => {
            var n;
            let l;
            try {
              l = JSON.parse(s.data);
            } catch {
              return;
            }
            l.type !== "diff_open" || !l.diff || (n = window.__awOpenAppWindow) == null || n.call(window, "diff-tool.viewer", l.diff.id, l.diff.title);
          }, o.onclose = () => {
            t || (r = setTimeout(i, 5e3));
          }, o.onerror = () => {
            try {
              o.close();
            } catch {
            }
          };
        } catch {
          t || (r = setTimeout(i, 5e3));
        }
      };
      return i(), () => {
        if (t = !0, clearTimeout(r), o) {
          o.onclose = null;
          try {
            o.close();
          } catch {
          }
        }
      };
    }, []), null;
  }
  function c({ instanceId: o }) {
    const r = o, t = r ? e.app.absoluteApiUrl(`/diffs/${r}/html`) : null;
    return /* @__PURE__ */ e.h("div", { className: "flex flex-col bg-[var(--color-bg-secondary)] h-full" }, /* @__PURE__ */ e.h("div", { className: "flex items-center justify-end px-2 py-1 border-b border-[var(--color-border)] shrink-0", onMouseDown: (i) => i.stopPropagation() }, /* @__PURE__ */ e.h(
      "button",
      {
        onClick: () => {
          t && window.open(t, `diff-${r}`, "popup=1,width=1100,height=750");
        },
        className: "p-1.5 rounded hover:bg-white/10 transition-colors",
        title: "Pop out to new window"
      },
      /* @__PURE__ */ e.h("svg", { className: "w-4 h-4 text-[var(--color-text-muted)]", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2" }, /* @__PURE__ */ e.h("path", { d: "M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" }), /* @__PURE__ */ e.h("polyline", { points: "15 3 21 3 21 9" }), /* @__PURE__ */ e.h("line", { x1: "10", y1: "14", x2: "21", y2: "3" }))
    )), /* @__PURE__ */ e.h("div", { className: "flex-1 relative" }, t && /* @__PURE__ */ e.h(
      "iframe",
      {
        src: t,
        className: "absolute inset-0 w-full h-full bg-white border-0",
        title: "Diff",
        sandbox: "allow-scripts allow-same-origin allow-forms"
      }
    )));
  }
  e.registerSlot("core.nav", f), e.registerWindow("diff-tool.viewer", c);
}
export {
  d as default,
  d as register
};
