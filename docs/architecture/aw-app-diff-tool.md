---
repo: architecture
path: docs/architecture/aw-app-diff-tool.md
source: generated
edited: false
checksum: sha256:e7e06d4c16675ad5920ec3302325afde44e7f13e83a1a710a895791aa91ae90f
---
# Diff Tool

- **repo**: aw-app-diff-tool
- **layer**: app
- **technologies**: python, react
- **health** (derived): planned

Interactive git diff viewer + commit panel, decoupled from the monolith. Two entry points: an agent's show_diff MCP tool call, or the git repo nav's expand arrow. Multi-file tabs, unified/split view, GitHub-style collapsible context, inline word-diff highlighting, and an embedded Commit & Push panel.

## Connections
- `http` → **aw-workspace** — routes mounted at /api/apps/diff-tool
- `stdio-mcp` → **mcp-gateway** — MCP surface aggregated by the gateway

## MCP tools
- `show_diff`

## Requirements
_none documented_
