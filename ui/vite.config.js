// Component-mode plugin bundle only — this app's diff HTML is
// server-rendered separately (see diff_app/routes.py's
// /diffs/{id}/html). Vite lib mode building src/plugin.jsx ->
// dist/diff-tool-ui.mjs, the bundle aw-app.json's
// contributes.frontend.bundle points at.
//
// esbuild's JSX transform (applied automatically to .jsx files) is
// repointed at host.h/host.React.Fragment instead of react's own
// createElement (jsxFactory's default), so every component in plugin.jsx —
// all declared INSIDE register(host), closing over `host` — compiles
// against the ONE shared React instance the plugin host provides (ADR "one
// shared React instance"; react/react-dom stay external, never bundled).
import { defineConfig } from 'vite';

export default defineConfig({
  esbuild: {
    jsxFactory: 'host.h',
    jsxFragment: 'host.React.Fragment',
  },
  build: {
    outDir: 'dist',
    lib: {
      entry: 'src/plugin.jsx',
      formats: ['es'],
      fileName: () => 'diff-tool-ui.mjs',
    },
    rollupOptions: {
      external: ['react', 'react-dom'],
    },
  },
});
