# Codex MCP Setup

Register the local server with hash embeddings and an isolated Codex data dir:

```bash
codex mcp add gwt-context \
  --env GWT_EMBEDDING_PROVIDER=hash \
  --env GWT_EMBEDDING_MODEL=hash \
  --env GWT_EMBEDDING_DIM=32 \
  --env GWT_DATA_DIR=/home/netsky/.gwt-context-codex \
  -- python -m gwt_context
```

Inspect the registration:

```bash
codex mcp get gwt-context
codex mcp list
```

Run the same server path through a real stdio MCP smoke:

```bash
python -m gwt_context.mcp_client_smoke
```

Notes:

- The command uses the public MCP protocol, not in-process FastMCP internals.
- Existing Codex sessions may need a restart before newly added MCP tools are
  available in the tool list.
- `GWT_DATA_DIR=/home/netsky/.gwt-context-codex` keeps manual Codex memory out
  of the repository and out of benchmark artifacts.

Remove the server if needed:

```bash
codex mcp remove gwt-context
```
