---
layout: null
title: gwt-context
---
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>gwt-context</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #15171a;
      --muted: #5b6572;
      --line: #d8dee7;
      --paper: #f7f8fa;
      --panel: #ffffff;
      --accent: #16686f;
      --accent-2: #7a4f13;
      --code: #172033;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--paper);
      line-height: 1.55;
    }

    a {
      color: var(--accent);
      text-decoration: none;
    }

    a:hover {
      text-decoration: underline;
    }

    .shell {
      width: min(1120px, calc(100% - 40px));
      margin: 0 auto;
    }

    .topbar {
      border-bottom: 1px solid var(--line);
      background: rgba(247, 248, 250, 0.92);
      position: sticky;
      top: 0;
      z-index: 2;
      backdrop-filter: blur(12px);
    }

    .topbar .shell {
      min-height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
    }

    .brand {
      font-weight: 700;
      letter-spacing: 0;
    }

    nav {
      display: flex;
      gap: 18px;
      flex-wrap: wrap;
      font-size: 14px;
    }

    .hero {
      padding: 78px 0 52px;
      border-bottom: 1px solid var(--line);
      background:
        linear-gradient(120deg, rgba(22, 104, 111, 0.10), transparent 44%),
        linear-gradient(270deg, rgba(122, 79, 19, 0.10), transparent 38%);
    }

    .hero-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(340px, 0.9fr);
      gap: 42px;
      align-items: center;
    }

    .eyebrow {
      margin: 0 0 14px;
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    h1 {
      max-width: 800px;
      margin: 0;
      font-size: clamp(44px, 7vw, 86px);
      line-height: 0.96;
      letter-spacing: 0;
    }

    .lead {
      max-width: 680px;
      margin: 24px 0 0;
      color: var(--muted);
      font-size: 20px;
    }

    .actions {
      margin-top: 32px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }

    .button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      padding: 0 18px;
      border: 1px solid var(--ink);
      color: var(--ink);
      background: transparent;
      font-weight: 700;
      border-radius: 6px;
    }

    .button.primary {
      background: var(--ink);
      color: #fff;
    }

    .workspace {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      box-shadow: 0 18px 48px rgba(23, 32, 51, 0.08);
    }

    .workspace-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .pulse {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: var(--accent);
    }

    .row {
      display: grid;
      grid-template-columns: 112px 1fr;
      gap: 14px;
      padding: 14px 0;
      border-top: 1px solid var(--line);
      font-size: 14px;
    }

    .row:first-of-type {
      border-top: 0;
    }

    .label {
      color: var(--muted);
      font-weight: 700;
    }

    code,
    pre {
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    }

    pre {
      margin: 16px 0 0;
      overflow: auto;
      border-radius: 8px;
      background: var(--code);
      color: #eef4ff;
      padding: 18px;
      font-size: 13px;
      line-height: 1.5;
    }

    section {
      padding: 56px 0;
      border-bottom: 1px solid var(--line);
    }

    h2 {
      margin: 0 0 16px;
      font-size: 28px;
      line-height: 1.15;
      letter-spacing: 0;
    }

    .section-lead {
      max-width: 760px;
      margin: 0 0 28px;
      color: var(--muted);
      font-size: 17px;
    }

    .cards {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }

    .card {
      min-height: 180px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
    }

    .card h3 {
      margin: 0 0 10px;
      font-size: 18px;
      letter-spacing: 0;
    }

    .card p {
      margin: 0;
      color: var(--muted);
      font-size: 15px;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: var(--panel);
    }

    .metric {
      padding: 20px;
      border-left: 1px solid var(--line);
    }

    .metric:first-child {
      border-left: 0;
    }

    .metric strong {
      display: block;
      font-size: 28px;
      line-height: 1.1;
    }

    .metric span {
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: 14px;
    }

    .split {
      display: grid;
      grid-template-columns: minmax(0, 0.92fr) minmax(0, 1.08fr);
      gap: 34px;
      align-items: start;
    }

    .links {
      display: grid;
      gap: 10px;
    }

    .link-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 0;
      border-bottom: 1px solid var(--line);
      color: var(--ink);
      font-weight: 700;
    }

    .link-row span {
      color: var(--muted);
      font-weight: 500;
      font-size: 14px;
    }

    footer {
      padding: 30px 0 46px;
      color: var(--muted);
      font-size: 14px;
    }

    @media (max-width: 860px) {
      .hero-grid,
      .split,
      .cards,
      .metrics {
        grid-template-columns: 1fr;
      }

      .hero {
        padding-top: 52px;
      }

      .metrics {
        border-bottom: 0;
      }

      .metric {
        border-left: 0;
        border-bottom: 1px solid var(--line);
      }

      .topbar .shell {
        align-items: flex-start;
        flex-direction: column;
        padding: 16px 0;
      }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="shell">
      <div class="brand">gwt-context</div>
      <nav>
        <a href="#runtime">Runtime</a>
        <a href="#evidence">Evidence</a>
        <a href="#docs">Docs</a>
        <a href="https://github.com/netsky-lab/gwt-context">GitHub</a>
      </nav>
    </div>
  </header>

  <main>
    <section class="hero">
      <div class="shell hero-grid">
        <div>
          <p class="eyebrow">MCP memory runtime</p>
          <h1>Working memory for agents, shaped like attention.</h1>
          <p class="lead">
            `gwt-context` is a Global Workspace Theory-inspired MCP server:
            facts compete for a bounded workspace, broadcasts fan out to
            independent processors, and accepted proposals drive the next
            memory actions.
          </p>
          <div class="actions">
            <a class="button primary" href="quickstart.html">Quickstart</a>
            <a class="button" href="honest-gwt-report.html">Read the GWT claim</a>
          </div>
        </div>

        <aside class="workspace" aria-label="Runtime demo summary">
          <div class="workspace-title">
            <span>Last dogfood run</span>
            <span class="pulse" aria-hidden="true"></span>
          </div>
          <div class="row">
            <div class="label">Question</div>
            <div>What does Paper Alpha cite cite?</div>
          </div>
          <div class="row">
            <div class="label">Workspace</div>
            <div>Paper Alpha, Paper Beta, Paper Gamma, collection evidence</div>
          </div>
          <div class="row">
            <div class="label">Bus</div>
            <div>1 accepted proposal, 2 inhibited repeats, 5 subscribers OK</div>
          </div>
          <div class="row">
            <div class="label">Answer</div>
            <div><strong>Paper Gamma</strong></div>
          </div>
        </aside>
      </div>
    </section>

    <section id="runtime">
      <div class="shell">
        <h2>What runs today</h2>
        <p class="section-lead">
          The current runtime is not just a vector search wrapper. It has a
          bounded workspace, ignition threshold, recurrent link activation,
          bus arbitration, subscriber budgets, and MCP tools for exact memory
          operations.
        </p>
        <div class="cards">
          <article class="card">
            <h3>Selection before recall</h3>
            <p>
              Candidates enter a preconscious buffer, compete through
              specialists, and only high-activation winners become globally
              visible in the workspace.
            </p>
          </article>
          <article class="card">
            <h3>Broadcast bus</h3>
            <p>
              Structured resolve, semantic recall, relation continuation,
              contradiction checks, and follow-up critique read the same
              broadcast and propose actions.
            </p>
          </article>
          <article class="card">
            <h3>Traceable memory ops</h3>
            <p>
              Backup, restore, reset, dedup import, working-memory compaction,
              exact collection queries, and admission reasons are available
              through MCP.
            </p>
          </article>
        </div>
      </div>
    </section>

    <section id="evidence">
      <div class="shell">
        <h2>Current RC evidence</h2>
        <p class="section-lead">
          Latest bounded sanity was run on 2026-04-28 against the configured
          OpenAI-compatible Qwen endpoint, with bus-on and bus-off slices.
        </p>
        <div class="metrics">
          <div class="metric">
            <strong>201</strong>
            <span>pytest cases passing</span>
          </div>
          <div class="metric">
            <strong>100%</strong>
            <span>RULER sanity, bus on/off</span>
          </div>
          <div class="metric">
            <strong>100%</strong>
            <span>LongBench sanity, bus on/off</span>
          </div>
          <div class="metric">
            <strong>0 / 0</strong>
            <span>subscriber timeout / error</span>
          </div>
        </div>
      </div>
    </section>

    <section id="install">
      <div class="shell split">
        <div>
          <h2>Try it locally</h2>
          <p class="section-lead">
            Use hash embeddings for deterministic local checks and MCP client
            smoke tests without downloading embedding models.
          </p>
        </div>
        <div>
<pre><code>pip install -e ".[dev,bench]"
GWT_EMBEDDING_PROVIDER=hash \
GWT_EMBEDDING_MODEL=hash \
python -m gwt_context.smoke

python -m gwt_context.mcp_client_smoke</code></pre>
        </div>
      </div>
    </section>

    <section id="docs">
      <div class="shell split">
        <div>
          <h2>Docs</h2>
          <p class="section-lead">
            Start with the honest report before repeating the GWT claim. It
            names what is real in the runtime and what still needs independent
            processor loops.
          </p>
        </div>
        <div class="links">
          <a class="link-row" href="honest-gwt-report.html">Honest GWT report <span>claim and limits</span></a>
          <a class="link-row" href="dogfood-report.html">Dogfood report <span>MCP and Qwen evidence</span></a>
          <a class="link-row" href="release-readiness.html">Release readiness <span>gates and commands</span></a>
          <a class="link-row" href="gwt-runtime-contracts.html">Runtime contracts <span>state boundaries</span></a>
          <a class="link-row" href="mcp-tool-contracts.html">MCP tool contracts <span>payload shapes</span></a>
          <a class="link-row" href="releases/v0.3.0.html">v0.3.0 RC notes <span>current release candidate</span></a>
        </div>
      </div>
    </section>
  </main>

  <footer>
    <div class="shell">
      Built for agent memory experiments. Static demo page; design intentionally minimal.
    </div>
  </footer>
</body>
</html>
