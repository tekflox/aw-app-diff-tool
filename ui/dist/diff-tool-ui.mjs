function p(e) {
  var f;
  const { useEffect: d } = e.React;
  function s() {
    return d(() => {
      let t, i, o = !1;
      const n = () => {
        try {
          t = new WebSocket(e.app.wsUrl("/ws")), t.onmessage = (l) => {
            var a;
            let r;
            try {
              r = JSON.parse(l.data);
            } catch {
              return;
            }
            r.type !== "diff_open" || !r.diff || (a = window.__awOpenAppWindow) == null || a.call(window, "diff-tool.viewer", r.diff.id, r.diff.title);
          }, t.onclose = (l) => {
            if (l.code === 4401 || l.code === 4403 || l.code === 4426) {
              try {
                window.dispatchEvent(new Event("aw-auth-failed"));
              } catch {
              }
              return;
            }
            o || (i = setTimeout(n, 5e3));
          }, t.onerror = () => {
            try {
              t.close();
            } catch {
            }
          };
        } catch {
          o || (i = setTimeout(n, 5e3));
        }
      };
      return n(), () => {
        if (o = !0, clearTimeout(i), t) {
          t.onclose = null;
          try {
            t.close();
          } catch {
          }
        }
      };
    }, []), null;
  }
  const c = (t) => t ? e.app.absoluteApiUrl(`/diffs/${t}/html`) : null;
  function u({ instanceId: t }) {
    const i = c(t);
    return i ? /* @__PURE__ */ e.h(
      "button",
      {
        onClick: () => window.open(i, `diff-${t}`, "popup=1,width=1100,height=750"),
        className: "p-1 rounded hover:bg-white/10 text-[var(--color-text-muted)]",
        title: "Pop out to new window"
      },
      /* @__PURE__ */ e.h("svg", { width: "14", height: "14", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2" }, /* @__PURE__ */ e.h("path", { d: "M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" }), /* @__PURE__ */ e.h("polyline", { points: "15 3 21 3 21 9" }), /* @__PURE__ */ e.h("line", { x1: "10", y1: "14", x2: "21", y2: "3" }))
    ) : null;
  }
  function w({ instanceId: t }) {
    const i = c(t);
    return /* @__PURE__ */ e.h("div", { className: "flex flex-col bg-[var(--color-bg-secondary)] h-full" }, /* @__PURE__ */ e.h("div", { className: "flex-1 relative" }, i && /* @__PURE__ */ e.h(
      "iframe",
      {
        src: i,
        className: "absolute inset-0 w-full h-full bg-white border-0",
        title: "Diff",
        sandbox: "allow-scripts allow-same-origin allow-forms"
      }
    )));
  }
  e.registerSlot("core.nav", s), e.registerWindow("diff-tool.viewer", w), (f = e.registerWindowActions) == null || f.call(e, "diff-tool.viewer", u);
}
export {
  p as default,
  p as register
};
