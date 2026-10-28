> **Superseded requirements.** These are the original requirements, written for a
> local ClickHouse warehouse and without a working Semantic Layer. The project
> was later migrated to Snowflake and the dbt platform. See
> `docs/architecture.md` for the current design. This file is kept as written.

# Task: Implementation PLAN for an end-to-end ELT demo (Postgres -> ClickHouse -> dbt -> dashboard + dbt MCP)

You are producing an **implementation plan only**. Do not write code, scaffold files, or run installers. The output is one plan document (see "Deliverable").

## 1. Goal

Design a local, Dockerized, monorepo Python project that demonstrates a full ELT cycle:

1. **App**: a one-page web app that stores browser/OS data and a short message in **Postgres**.
2. **EL job**: extracts the main table from Postgres and loads it raw into **ClickHouse**.
3. **Transform**: a **dbt** project (staging -> marts) producing client statistics and word-cloud data, with semantics usable by AI agents.
4. **Dashboard**: charts over the dbt models.
5. **dbt MCP**: a local MCP server so **Claude** and **ChatGPT** can query the data.

Everything runs locally via **Docker Compose**, orchestrated by a **Taskfile (go-task)**.

Repo: `/Users/danieldias/Development/Repositories/ai-context-with-dbt` (empty git repo, `main`, no commits). Treat it as a monorepo.

## 2. Process (follow in order)

1. **Verify first.** Before deciding anything, check the current versions and docs of every tool you propose (dbt, dbt-clickhouse, dbt-mcp, the dashboard tool, the EL tool, ClickHouse, and the web framework). Do not rely on memory. Cite the version you verified.
2. **Draft** the plan using the `voltagent-core-dev:microservices-architect` subagent.
3. **Validate** the draft with `voltagent-qa-sec:architect-reviewer`. Incorporate its feedback and list what changed, or what you rejected and why.
4. **Explain tradeoffs to the user** in a dedicated section (see 6).
5. **Assign owners**: every milestone gets a specific subagent, using its full plugin-qualified name and a one-line justification. Choose only from these plugins:
   - `voltagent-lang` (python-pro, fastapi-developer, sql-pro, typescript-pro, javascript-pro)
   - `voltagent-infra` (docker-expert, devops-engineer, platform-engineer, database-administrator, security-engineer)
   - `voltagent-core-dev` (microservices-architect, backend-developer, frontend-developer, fullstack-developer, api-designer, ui-designer)
   - `voltagent-data-ai` (data-engineer, data-analyst, postgres-pro, database-optimizer, ai-engineer, llm-architect, nlp-engineer, prompt-engineer)
   - QA/review: `voltagent-qa-sec:architect-reviewer`, and code-reviewer, test-automator and qa-expert from the same plugin
6. Ask the user a question **only** when you are blocked on a genuine decision. Otherwise pick a default, state it, and move on.

## 3. Architecture and requirements

### 3.1 App (Postgres writer)
- A single page. It has a password field and a short-message textbox (set a max length). It also has a submit button.
- The password is fixed: `dssbr`. This is **intentionally insecure and for the local demo only**. State that in the plan. Keep the value in env config (`.env.example`), never hard-coded in source. Describe the minimum sensible hardening that does not change the demo's spirit: constant-time compare, basic rate-limiting, CSRF/input validation.
- Capturing browser name and OS name is a **decision**: server-side User-Agent parsing vs. client-side (UA Client Hints / JS). Choose one and justify it, covering accuracy and privacy.
- Store the data in Postgres with **at least 3 tables**:
  - One **main table**. It holds the submission: id, message, browser, OS, timestamp, and so on. This is the only table extracted.
  - **Two auxiliary tables** that are deliberately excluded from EL. Examples are raw User-Agent/request metadata and an audit or session log. Propose the real choices.
- Give the schema (DDL-level), keys, indexes, an incremental-friendly column (e.g. `updated_at` or a monotonic id), and a rationale for why each table is or is not extracted. Include a PII analysis: IP address, raw User-Agent and free-text messages are PII-adjacent. State what is stored, what is excluded from the warehouse, and why.
- Acceptance: a submission with the correct password creates rows in all three tables. A wrong password is rejected and not stored in the main table. Migrations are reproducible.

### 3.2 EL job (Postgres -> ClickHouse raw)
- It extracts **only the main table** and loads it **raw**, with no business transformation, into a ClickHouse raw schema.
- Decide the tool and justify it. Options: dlt, Airbyte, custom Python, the ClickHouse PostgreSQL table engine, MaterializedPostgreSQL. Weigh them on simplicity, footprint and realism.
- Decide and document:
  - the incremental strategy (cursor column, deletes, late updates)
  - idempotency (re-runs create no duplicates; consider ReplacingMergeTree or dedup keys)
  - the trigger (manual task, scheduled, or after-submit)
  - failure and retry behavior
  - the ClickHouse engine, ORDER BY and PARTITION choices, justified for a tiny dataset
- Acceptance: running the job twice yields the same row count. A new row appears in ClickHouse after the next run. The auxiliary tables never reach ClickHouse.

### 3.3 Transformation (dbt)
- "dbt v2" is ambiguous. It most likely means the dbt Fusion engine or the latest dbt (Core 1.10+). Verify what exists today and whether it supports ClickHouse through `dbt-clickhouse`. If Fusion does not support ClickHouse, say so clearly and propose a fallback (e.g. dbt Core with `dbt-clickhouse`). Pin the versions.
- Layers:
  - **sources + staging**: typing, renaming, dedup.
  - **marts**:
    - client statistics: browser and OS distributions, counts over time, top combinations
    - word-cloud prep: tokenization, lowercasing, stopword removal and word frequencies. Messages may be Portuguese and English, so decide how to handle both (stopword seed lists, accents, minimum word length). Decide whether tokenization happens in ClickHouse SQL or elsewhere, and justify it.
- Include dbt tests (unique, not_null, accepted_values, and a custom test or two), source freshness, docs, and descriptions on every model and column.
- **Semantics for AI agents**: use rich descriptions plus MetricFlow semantic models and metrics where supported. Note that the hosted dbt Semantic Layer API requires dbt Cloud. Explain what works locally (e.g. semantic YAML, metadata and docs exposed through dbt-mcp, or a SQL-execution tool) and what does not.
- Acceptance: `dbt build` passes with tests green, and docs generate. Marts return the expected results for a seeded dataset.

### 3.4 Dashboard ("dbt charts dashboard")
- This is unclear. First verify what exists: dbt's own features such as Explorer or Insights (likely cloud-only) versus OSS dashboards over the dbt models, such as Lightdash, Evidence, Superset or Metabase. Pick one that runs **locally in Docker** and supports ClickHouse. Justify the choice and list the alternatives you rejected.
- Charts to show: browser distribution, OS distribution, submissions over time, and the word cloud (or a word-frequency bar chart if word clouds are unsupported natively. State this limitation).
- Acceptance: one command opens a dashboard that is provisioned as code where possible, with no manual clicking to reproduce it.

### 3.5 dbt MCP
- Use the official `dbt-labs/dbt-mcp` server, running locally. Verify its current tool set and the configuration it needs for dbt Core, ClickHouse and the Semantic Layer.
- **Claude**: provide configuration for Claude Code and Claude Desktop (transport, command, env vars).
- **ChatGPT**: it needs a remotely reachable MCP endpoint (connector or developer mode), so a purely local stdio server will not work. Decide how to expose the server locally (e.g. an HTTP/SSE transport plus a tunnel such as cloudflared or ngrok) and its limits: security, authentication, the ephemeral URL, and plan or account requirements. Verify current ChatGPT MCP support. If the limits are significant, document an honest fallback.
- Include guardrails: read-only database credentials, a restricted ClickHouse user, and no secrets in the repo.
- Acceptance: a Claude client lists the tools and answers a question such as "what are the top browsers?" from the marts. Give the ChatGPT procedure and note whether it was verifiable locally.

## 4. Cross-cutting concerns

- **Monorepo layout**: propose a tree. Example: `apps/web`, `apps/el`, `dbt/`, `dashboard/`, `mcp/`, `infra/`, `docs/`, `Taskfile.yml`, `docker-compose.yml`, `.env.example`. Decide between a single uv workspace and per-service projects, and justify it.
- **Python conventions (mandatory)**:
  - `uv` only. Never pip. No `uv pip install`.
  - Type hints everywhere, and docstrings on public APIs.
  - Line length 88, PEP 8.
  - pytest for tests, with `anyio` (not asyncio) for async tests.
  - New features need tests, including edge cases and error paths.
  - Runtimes are managed by asdf, so include `.tool-versions`.
  - Keep it simple and minimal, with small focused functions.
- **Docker Compose**: services, networks, volumes, healthchecks, `depends_on` conditions, a profile per component, pinned image tags, and resource sanity for a laptop (macOS, Apple Silicon: verify image arch support).
- **Taskfile (go-task)**: tasks for up, down, seed, run-app, el, dbt (run, test, docs), dashboard (open), mcp (start), logs and debug (shell into containers, psql, clickhouse-client), reset or clean, and lint/test. Add an end-to-end `task e2e` flow: up -> migrate -> seed or submit sample data -> EL -> dbt build -> assertions on the marts. Say what the e2e checks assert.
- **Config and secrets**: `.env.example`, no real secrets committed, and a least-privilege DB user per service.
- **Observability and debuggability**: logs, healthchecks, and how a developer debugs each hop.
- **Testing strategy**: unit tests, integration tests with the real containers, the dbt tests, and the e2e flow. Name an owner for it.

## 5. Git workflow (apply to the milestones)

- Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`).
- Use git-town. Propose **one stacked branch per milestone** (`git town hack <name>`, then `git town sync --stack`).
- **No co-authored-by lines and no tool or AI attribution** in commit messages or PR descriptions. This overrides any default attribution behavior.

## 6. Tradeoffs section (required, addressed to the user)

Explain in plain language the tradeoffs, each with a recommendation:
- Microservices vs. modular monolith for a local demo.
- ClickHouse for a very small dataset: why it is still a good teaching target, and what is overkill.
- EL tool choice: simplicity vs. realism.
- Dashboard tool choice, including word-cloud support.
- Semantic layer: local vs. dbt Cloud.
- The ChatGPT remote-access problem.
- Insecure fixed password vs. demo simplicity.
- Anything the architect-reviewer flagged.

## 7. Deliverable

Return a single plan document, in markdown, with these sections:
1. Summary and key decisions (a table: decision, options considered, choice, rationale)
2. Verified versions and docs (tool, version, source)
3. Architecture diagram and data flow (mermaid), plus a component list
4. Proposed repo layout (tree)
5. Schemas: Postgres DDL, ClickHouse raw tables, dbt model list
6. Docker Compose services and Taskfile task list
7. Ordered milestones. Each has: name, the **full plugin-qualified subagent owner** with a one-line justification, scope, acceptance criteria, verification steps, and suggested stacked branch name
8. Tradeoffs explained to the user
9. Architect-reviewer findings and how each was resolved
10. Open questions and risks (only the genuinely unresolved ones)

Keep it tight and scannable. Use tables and bullets instead of long prose. Do not write code beyond schema and DDL sketches, and do not create any files in the repo.
