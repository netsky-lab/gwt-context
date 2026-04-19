# ROADMAP

## Current Focus

- P4: Define and lock down target clean architecture boundaries (done in this task).
- P5: Refactor application layer to depend on ports/ABCs from `src/gwt_context/interfaces/ports.py`.
- P6: Clean MCP boundary so tools/resources use only application ports and read-model DTOs.
- P7: Stabilize benchmark harness dependencies and reliability.
- P8: Execute benchmark matrix on RunPod Gemma endpoint.

## Constraint for Dependency Changes

- Do not move runtime behavior in this task; this roadmap expects documentation and interface intent first.
- Preserve `server.py` as composition root and avoid introducing concrete infrastructure dependencies in MCP and domain layers.

