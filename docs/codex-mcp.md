# Codex MCP Setup

Use separate memory namespaces for global memory and project memory. The
recommended layout is:

```text
/home/netsky/.gwt-context-codex/
  global/
  projects/
    gwt-context/
```

Register the project-specific server for this repository:

```bash
codex mcp add gwt-context \
  --env GWT_EMBEDDING_PROVIDER=hash \
  --env GWT_EMBEDDING_MODEL=hash \
  --env GWT_EMBEDDING_DIM=32 \
  --env GWT_DATA_DIR=/home/netsky/.gwt-context-codex/projects/gwt-context \
  -- python -m gwt_context
```

Register a separate global memory server:

```bash
codex mcp add gwt-global \
  --env GWT_EMBEDDING_PROVIDER=hash \
  --env GWT_EMBEDDING_MODEL=hash \
  --env GWT_EMBEDDING_DIM=32 \
  --env GWT_DATA_DIR=/home/netsky/.gwt-context-codex/global \
  -- python -m gwt_context
```

Inspect the registration:

```bash
codex mcp get gwt-context
codex mcp get gwt-global
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
- `gwt-context` should hold facts specific to this repo.
- `gwt-global` should hold reusable personal or cross-project facts.
- Existing Codex sessions may keep already-started MCP processes alive; restart
  Codex after changing server definitions.

Clear one namespace safely:

```bash
python scripts/clear_codex_memory.py --project gwt-context
python scripts/clear_codex_memory.py --project gwt-context --yes
python scripts/clear_codex_memory.py --global --yes
```

The cleanup helper refuses to clear the memory root directly. It only clears
entries inside a selected namespace and recreates the namespace directory.

Remove servers if needed:

```bash
codex mcp remove gwt-context
codex mcp remove gwt-global
```
