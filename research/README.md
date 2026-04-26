# Research Notes

This folder is a local research cache for Global Workspace Theory (GWT) and
Global Neuronal Workspace Theory (GNWT) work that can justify and challenge the
`gwt-context` design.

Cached on: 2026-04-26

## Current Papers

| Year | Paper | Local file | Source | Why it matters |
| --- | --- | --- | --- | --- |
| 2026 | Wenlong Shang, `"Theater of Mind" for LLMs: A Cognitive Architecture Based on Global Workspace Theory` | [`papers/2026-shang-theater-of-mind-gwa.pdf`](papers/2026-shang-theater-of-mind-gwa.pdf) | arXiv:2604.08206 | Directly maps GWT to LLM agent topology: stage/spotlight/audience, central broadcast hub, cognitive ticks, and multi-agent arbitration. |
| 2025 | Junya Nakanishi et al., `Hypothesis on the Functional Advantages of the Selection-Broadcast Cycle Structure` | [`papers/2025-nakanishi-selection-broadcast-cycle.pdf`](papers/2025-nakanishi-selection-broadcast-cycle.pdf) | arXiv:2505.13969 / Frontiers | Strongest support for treating selection + broadcast as a single cycle rather than separate retrieval and formatting steps. |
| 2025 | Hugo Chateau-Laurent and Rufin VanRullen, `Learning to Chain Operations by Routing Information Through a Global Workspace` | [`papers/2025-chateau-laurent-routing-through-global-workspace.pdf`](papers/2025-chateau-laurent-routing-through-global-workspace.pdf) | arXiv:2503.01906 | Shows a learnable router/workspace mechanism for chaining operations, relevant to multi-hop reasoning benchmarks. |
| 2025 | Pengbo Hu and Xiang Ying, `Unified Mind Model: Reimagining Autonomous Agents in the LLM Era` | [`papers/2025-hu-unified-mind-model.pdf`](papers/2025-hu-unified-mind-model.pdf) | arXiv:2503.03459 | Agent architecture that explicitly starts from GWT and maps workspace concepts onto perception, planning, reasoning, memory, reflection, and motivation. |
| 2025 | Wanghao Ye et al., `CogniPair: From LLM Chatbots to Conscious AI Agents` | [`papers/2025-ye-cognipair-gnwt-agents.pdf`](papers/2025-ye-cognipair-gnwt-agents.pdf) | arXiv:2506.03543 | Concrete GNWT-style multi-agent case study with specialized sub-agents, salience weighting, conflict resolution, goal tracking, and broadcast. |

## Link-Only Candidate

| Year | Paper | Source | Status |
| --- | --- | --- | --- |
| 2026 | Izak Tait, Benjamin Rode, Joshua Bensemann, `Evaluating Global Workspace Markers in Contemporary LLM Systems` | <https://www.preprints.org/manuscript/202601.1683/v1> | Very relevant marker/rubric paper. The PDF is CC BY 4.0 on Preprints.org, but direct non-browser download returned HTTP 403 during cache creation, so it is not stored here yet. |

## Design Implications For This Repo

- Keep the selection-broadcast cycle explicit. Retrieval alone is not a GWT
  mechanism; the architecture needs candidate generation, scoring, admission,
  eviction, and broadcast as separate observable steps.
- Preserve a bounded workspace. Capacity pressure is not incidental; it is what
  turns memory access into arbitration.
- Treat goals as first-class modulators. Goal state should affect selection,
  not just the text of the final prompt.
- Add benchmark trace artifacts before interpreting scores. The marker paper's
  evaluation framing implies we need traces for workspace state, candidate
  scores, selected/evicted items, tool calls, and goal changes.
- Avoid claiming consciousness. These sources are useful as architecture
  justification for selection, broadcast, and global availability. They do not
  prove or require phenomenal consciousness.

## Redistributing PDFs

The cached files were downloaded from open full-text sources. Before publishing
this repository or mirroring these files elsewhere, re-check each source license
from the upstream paper page and keep source attribution with the files.
