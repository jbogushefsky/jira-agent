# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

LangGraph-orchestrated agents that react to Jira ticket status changes. A FastAPI backend polls Jira (via a self-hosted `mcp-atlassian` MCP server) on an interval, detects status transitions, and runs a LangGraph flow for each one, invoking the Claude Code CLI headlessly to do the actual thinking/coding:

- **-> AI - Requirement Review**: an LLM call reviews the description for ambiguous requirements and appends specific clarifying questions (with an "Answer: _(pending)_" placeholder per question) to the bottom of the ticket's description, retaining everything already there.
- **-> AI - Story Review**: Claude Code evaluates the ticket and posts recommendations back as a Jira comment.
- **-> AI - Build Story**: Claude Code works out an implementation approach (grounded in the target project's code, if one is referenced) and overwrites the ticket's description with it.
- **-> AI-Generate Test Scenarios**: an LLM call generates test scenarios (each with a unique traceability ID) covering every acceptance criterion, and appends them as a matrix at the bottom of the ticket's description.
- **-> In Dev**: Claude Code generates code changes (and tests) in a sibling project folder name. Each generated test must have the Test Scenario in its comments/documentation

Every step of every run is persisted (input/output/status/timing) in Postgres and traced in LangSmith. The
[jira-agent-ui](../jira-agent-ui) dashboard (a separate project) lists processed tickets and lets you
inspect each flow's steps. This project's own MCP server (so other MCP clients can query flow/ticket
history) runs as its own `jira-agent-mcp` service — see "Dual MCP role" below.

## Running it

- `docker compose up --build` — runs `backend` (8000), `jira-agent-mcp` (8010), and `mcp-atlassian`
  together. The dashboard is a separate project now — see [jira-agent-ui](../jira-agent-ui)'s own README.
  (`jira-agent-mcp` is on 8010, not 8001, because 8001 is already taken by dice-roll's backend on this
  machine.)
- Requires `.env` (copy from `.env.example`) with `ANTHROPIC_API_KEY`, `JIRA_URL`/`JIRA_USERNAME`/
  `JIRA_API_TOKEN`, `JIRA_PROJECT_KEYS`, and `LANGCHAIN_API_KEY`.
- Postgres is **not** containerized — the backend connects to the existing local `vectorjira` database on
  the host via `host.docker.internal`, and on boot runs Alembic migrations that add a `jira_agent` schema
  to it. Nothing else in that database is touched. `jira-agent-mcp` depends on `backend` being healthy
  first, since `backend` is what runs those migrations — `jira-agent-mcp` itself never runs Alembic.
- The backend container bind-mounts the whole `C:/joa/vscode` host directory to `/workspaces`
  (`WORKSPACES_ROOT`) — this is how "In Dev" flows get filesystem access to sibling project repos to run
  Claude Code against. `app/utils/project_paths.py` resolves `Project: <name>` to `/workspaces/<name>` and
  refuses to resolve to the `jira-agent` folder itself. `jira-agent-mcp` doesn't need this mount — it only
  reads Postgres — so it's the one difference between its docker-compose service definition and `backend`'s.

## Commands

Backend (from `backend/`):
- `pip install -e ".[dev]"` — install with dev deps (pytest, ruff, mypy).
- `uvicorn app.main:app --reload --port 8000` — run the REST/WS API locally outside Docker (needs `.env`
  and a reachable Postgres).
- `uvicorn app.mcp_server.app:app --reload --port 8010` — run the `jira-agent-mcp` service locally outside
  Docker (same env/Postgres requirements; this is the module `jira-agent-mcp`'s docker-compose `command`
  points at).
- `alembic upgrade head` / `alembic revision --autogenerate -m "..."` — run/create migrations
  (`app/db/migrations`).
- `pytest` / `pytest tests/unit/test_foo.py::test_bar` — run tests (`tests/unit`, `tests/integration`;
  `tests/unit` has the real suite — 200+ tests at ~99% coverage; `tests/integration` is still empty).
- `ruff check .` — lint. `mypy app` — type-check.

Frontend commands now live in [jira-agent-ui](../jira-agent-ui)'s own CLAUDE.md/README — this project no
longer has a `frontend/` directory.

## Architecture

**Poll -> transition -> flow.** `poller/scheduler.py` runs `poll_jira_job` on an APScheduler interval. It
JQL-searches Jira for the configured project keys, and for each issue diffs its status against the last
seen one (`poller/diff.py` `compute_transition`) to decide if a flow should fire (`to_story_review`,
`to_generate_test_scenarios`, `to_in_dev`, `to_build_story`, `to_requirement_review` — configured in
`Settings.trigger_statuses`). A ticket's target project comes
from a `Project: <name>` reference the poller extracts from the summary/description
(`utils/ticket_parsing.extract_project_reference`) and stores as `target_project_name`. When a transition
fires, the poller writes `Ticket`/`TicketStatusHistory`/`Flow` rows and fires `graph.run_flow` as a
detached `asyncio.create_task` (deferred-imported to avoid a poller<->graph import cycle) — the poll loop
itself never awaits a flow.

**The graph** (`app/graph/graph.py`) is a `StateGraph[GraphState]` (`app/graph/state.py`) with one entry
node (`fetch_ticket_details`) that branches by `transition` into five independent chains
(`evaluate_ticket -> post_recommendations`,
`generate_test_scenarios -> persist_test_scenarios -> post_test_scenario_matrix`,
`parse_project_reference -> generate_code_changes -> generate_tests`,
`generate_approach -> update_ticket_description`,
`review_requirement_ambiguity -> post_ambiguity_questions`), all converging on
`finalize_flow`/`handle_failure`. Routing lives in `app/graph/router.py`: nodes never raise on business
failures, they return `{"error": "..."}` in their update dict, and `continue_or_fail(next_node)` reads
`state["error"]` to redirect to `handle_failure` instead. Every node is wrapped in
`nodes/common.with_step_tracking(step_name)`, which persists a `FlowStep` row before/after each node call,
broadcasts `step_started`/`step_updated` over the `/ws/flows` WebSocket (`api/broadcaster.py`) for the
live UI, and is what converts a node exception into the `state["error"]` convention above.

**Claude Code as a subprocess.** `app/graph/claude_cli.py::run_claude_code` shells out to the real `claude`
CLI (`claude -p <prompt> --output-format stream-json --verbose ...`) with `cwd` set to whichever project
directory the node cares about, parses its newline-delimited JSON event stream, and raises
`ClaudeCliError`/`ClaudeCliTimeoutError` on failure (including errors that surface as a "successful" exit).
It supports `--resume <session_id>` so `generate_tests` can continue the same Claude Code session
`generate_code_changes` started (falling back to feeding it a `git diff` if no session id is available).
Because this is a real Claude Code invocation, any `CLAUDE.md` in the target project's root is picked up
automatically — `evaluate_ticket` explicitly points the model at it in its prompt; `generate_code_changes`/
`generate_tests` don't need to mention it, Claude Code loads it regardless of `cwd`. `evaluate_ticket` runs
with `cwd` at the resolved project path if one exists, otherwise a scratch tempdir with no filesystem
access — check for `project_path`/`project_name` being `None` when touching that node. `generate_approach`
follows the same project-or-tempdir pattern, but its prompt also inlines the rubric at
`app/graph/prompts/ai_resolve_story_rubric.md` (loaded from disk, not left to CLAUDE.md auto-discovery
— it needs to apply regardless of which project, if any, the ticket targets) and asks the model to return
the ticket's full replacement description in one shot; `update_ticket_description` then overwrites the
Jira description field with that text via `JiraMCPClient.update_description`.

**Persistence.** All app tables live in a dedicated `jira_agent` Postgres schema (`app/db/models.py`):
`tickets` -> `ticket_status_history` -> `flows` -> `flow_steps`, plus `test_scenarios` and `code_changes`
hanging off a flow. A `flows` unique index enforces only one `pending`/`running` flow per
`(ticket_id, transition_type)` at a time; `poller.scheduler` treats the resulting `IntegrityError` as an
expected "duplicate flow, skip" case, not an error.

**Workflow diagram (`GET /api/graph`).** `graph.py`'s `NODE_FUNCTIONS` dict is the single source of
truth for node registration in `build_graph()` — it's also used to derive `NODE_STEP_NAMES` (node id ->
`with_step_tracking` step_name, e.g. `evaluate_ticket` -> `claude-code-evaluate`; these deliberately
differ, so the mapping can't be assumed by string manipulation) by reading each node function's
`.step_name` attribute (set by the decorator in `nodes/common.py`). `finalize_flow`/`handle_failure`
aren't wrapped in `with_step_tracking`, so they're absent from `NODE_STEP_NAMES` — the frontend infers
whether they ran from the flow's overall `status` instead of a step record. `get_mermaid_definition()`
calls LangGraph's own `get_graph().draw_mermaid()` rather than hand-maintaining a duplicate diagram —
conditional edges (`add_conditional_edges`) render dashed with the `path_map` key as a label whenever it
differs from the destination node id (so `fetch_ticket_details`'s five-way branch shows `to_story_review`
etc., while `continue_or_fail`'s same-name-in-both-directions edges render as unlabeled dashed lines —
still visually distinct from the graph's few unconditional solid edges).
[jira-agent-ui](../jira-agent-ui)'s `components/flow/WorkflowDiagram.tsx` renders this with `mermaid.js`
client-side and highlights nodes
whose step_name appears in the active flow's steps by setting inline SVG styles directly, rather than
adding a CSS class — inline styles reliably beat mermaid's own generated `<style>` block on specificity.
One easy mistake here: the id mermaid assigns each node group is `<renderCallId>-flowchart-<nodeId>-<n>`,
not just `flowchart-<nodeId>-<n>` — a regex anchored at the string start silently matches nothing.

**Two tracing systems, two layers.** LangSmith (`observability/langsmith_setup.py`, wired up via env
vars in `lifespan()`) traces the *agent* layer — every LangGraph node and the Claude Code CLI subprocess
calls (`@traceable` in `graph/claude_cli.py`) — and is what the dashboard's "view trace" links point at.
OpenTelemetry (`observability/otel_setup.py`) traces the *infrastructure* layer instead:
`FastAPIInstrumentor` covers the REST/WS request surface, `SQLAlchemyInstrumentor` covers the SQL queries
behind it, exported via OTLP/gRPC to the `otel-collector` service and on to Jaeger (http://localhost:16687
— offset from dice-roll's Jaeger on 16686 so both projects' stacks can run at once). Unlike
`configure_langsmith` (called from `lifespan()` — fine, since LangChain only reads those env vars deep
inside route handlers, well after startup), `configure_opentelemetry(app)` is called at **module level**
in `main.py`, immediately after `app = FastAPI(...)` and before `app.add_middleware(...)`. That ordering
is load-bearing: Starlette builds and caches its middleware stack on the very first ASGI message the app
receives, which is its own lifespan-startup handshake — dispatched *before* the `lifespan()` generator's
body runs. Instrumenting from inside `lifespan()` (as originally tried) silently never wires the
instrumentation's middleware into the live stack: `SQLAlchemyInstrumentor`'s DB spans still work (it
hooks engine-level events, not middleware) but `FastAPIInstrumentor`'s HTTP spans never appear. The
[jira-agent-ui](../jira-agent-ui) has matching browser-side OpenTelemetry (`src/telemetry.ts`, imported
for its side effect at the top of `main.tsx`): page load and `fetch` spans, exported via OTLP/HTTP
straight to the collector (host port 4319, also offset from dice-roll's 4318). jira-agent-ui is now a
separate project/origin with no dev proxy (see its own CLAUDE.md/README) — it calls this backend's
absolute `VITE_API_BASE_URL` cross-origin, so trace-context headers still reach the backend (CORS
`allow_headers=["*"]` lets them through) and frontend/backend spans still join into one trace, but that
join is no longer same-origin the way dice-roll's setup is.

**Dual MCP role, now split across two services.** This backend *consumes* an MCP server
(`mcp_jira/client.py` talks to the `mcp-atlassian` container for Jira reads/writes) and this codebase also
*exposes* one (`mcp_server/server.py`, a `FastMCP` instance with `list_processed_tickets`/
`get_ticket_flow`/etc.) — but the two no longer share a process. The exposed one used to be mounted at
`/mcp` directly inside `main.py`; it now has its own ASGI entrypoint (`mcp_server/app.py`) and its own
docker-compose service, `jira-agent-mcp` (port 8010), so the MCP query surface can be built/deployed/
scaled independently of the poller/graph/REST service. Both still share this codebase and the same
Postgres database — `jira-agent-mcp` just isn't the one running Alembic migrations (`backend` is).

**jira-agent-ui** (a separate project, `../jira-agent-ui`) is a Vite + React + TanStack Query app: `api/`
holds typed REST clients, `hooks/` wraps them in query hooks (plus `usePollingInterval`/WebSocket-driven
refetching), `pages/` (`TicketsListPage`, `TicketFlowPage`) are the two views, `components/` split by
domain (`flow/`, `tickets/`, `layout/`, `shared/`). It talks only to this backend's REST API
(`app/api/rest.py`), never the graph or DB directly — via an absolute `VITE_API_BASE_URL` now that it's
not same-origin with this backend anymore (no frontend code actually opens the `/ws/flows` WebSocket yet,
despite `app/api/ws.py`/`app/api/broadcaster.py` existing to support it).


## JIRA Ticket Description Evaluation
Story Generation Instructions

When creating or refining a user story, produce a story that could be implemented by an engineer with minimal clarification.

The story should include the following sections.

1. User Story

Use the standard format.

As a <user/persona>, I want <capability> so that <business value>.

Identify the primary persona if one is not explicitly provided.

2. Business Context

Provide a brief explanation of:

Why this work is needed
The business problem being solved
Expected customer or business value
Any dependencies on other systems
3. Functional Requirements

Write clear, testable requirements.

Each requirement should:

Describe one behavior.
Use active language.
Avoid implementation details unless explicitly requested.
Be independently verifiable.
Include normal and edge-case behavior.

Example:

The system shall reject duplicate requests using the idempotency key.
The system shall retain audit records for all successful updates.
The system shall display validation errors inline.
4. Non-Functional Requirements

Include applicable requirements for:

Performance
Availability
Reliability
Scalability
Security
Privacy
Accessibility
Observability
Compliance
Localization
Browser/device support

Examples:

API response time shall be under 300 ms at the 95th percentile.
The solution shall emit structured logs.
All API endpoints shall require authentication.
Personally identifiable information shall never appear in logs.
5. Acceptance Criteria

Write thorough acceptance criteria using Given / When / Then.

Include:

Happy path
Validation failures
Error handling
Permission scenarios
Empty states
Duplicate requests
Retry behavior
Boundary conditions
Invalid inputs
Audit requirements
Logging requirements
Notifications
State transitions

Each acceptance criterion should verify one behavior.

Example:

Given a valid request
When the user submits the form
Then the record is created
And an audit event is written.

6. Edge Cases

Explicitly identify edge cases.

Examples:

Duplicate submissions
Missing required fields
Invalid data
Expired sessions
Network failures
Partial failures
Timeouts
Concurrent updates
Large datasets
Empty results
Unsupported values
7. Business Rules

List explicit business rules.

For example:

Users may edit only their own records.
Administrators may override validation.
Records older than 90 days are read-only.
Only one active configuration may exist.
8. Out of Scope

Clearly identify what is NOT included.

9. Technical Notes

If technical assumptions are provided, summarize:

APIs involved
Events published
Database changes
Feature flags
Backward compatibility
Migration considerations
10. Definition of Done

The story is complete only when:

All acceptance criteria pass.
Unit tests are added.
Integration tests pass.
Observability is implemented.
Security requirements are satisfied.
Documentation is updated.
Feature flag behavior is verified.
No known critical defects remain.
Acceptance Criteria Quality Rules

Every acceptance criterion must be:

Specific
Measurable
Testable
Independent
Unambiguous
Focused on observable behavior
Free of implementation assumptions unless required

Avoid vague language such as:

appropriately
correctly
efficiently
quickly
user-friendly
as needed
where possible

Instead use measurable expectations.

Requirements Quality Checklist

Before finishing, verify that the story answers:

Who is the user?
What problem is being solved?
Why is it valuable?
What happens when everything succeeds?
What happens when validation fails?
What happens when downstream services fail?
What happens when duplicate requests occur?
What permissions are required?
What should be logged?
What should be audited?
What metrics should be emitted?
What events are published?
What errors are shown?
What happens if data already exists?
What happens if no data exists?
What are the performance expectations?
What are the security expectations?
What is explicitly out of scope?

If any answer is missing, identify the gap rather than making assumptions.

Final Story Review

Before returning the story, evaluate it against these quality gates and report any deficiencies:

Quality Gate	Pass/Fail
Clear business value	
Requirements are testable	
Acceptance criteria cover happy path	
Acceptance criteria cover failures	
Edge cases included	
Security addressed	
Performance addressed	
Logging and observability addressed	
Audit requirements included	
Out of scope identified	
No ambiguous wording	
Ready for sprint planning	

If any quality gate fails, explain why and suggest what information is needed.  Make sure the recommendations are in a section called "AI RECOMMENDATIONS".  replace the previous content when adding the most current

## Test Scenario Traceability Matrix (generate-test-scenarios)

When the `generate-test-scenarios` step (fired on the "AI - Generate Test Scenarios" transition) writes test scenarios
for a ticket:

- Every scenario must carry a unique identifier for traceability, so an automated test can later be
  tagged or commented with a reference back to the scenario it implements. Use the convention
  `{jira-ticket-number}-AC-##-TC-##`: the first `##` is the sequential, two-digit, zero-padded index
  of the acceptance criterion the scenario covers (in listed order); the second `##` is the
  sequential, two-digit, zero-padded scenario number **within that acceptance criterion**, restarting
  at `01` for each new acceptance criterion. E.g. for `PROJ-42`: `PROJ-42-AC-01-TC-01`,
  `PROJ-42-AC-01-TC-02`, `PROJ-42-AC-02-TC-01`. Never reuse a full identifier within the same ticket.
- The full set of scenarios must be presented as a matrix (a table: ID / Acceptance Criterion /
  Scenario / Given-When-Then) appended to the **bottom** of the ticket's description.
- The ticket's existing description verbiage must be retained in full, unchanged, above the matrix —
  this is an append, not a replacement (contrast with the AI - Build Story rubric above, which replaces the
  whole description).

Same caveat as the AI - Build Story section above: the backend container only mounts `backend/`, so this
file isn't readable at runtime. The identifier-generation instruction is operationalized in
`backend/app/graph/prompts/test_scenario_instructions.md`, loaded into `app/llm/scenario_llm.py`'s
prompt so the LLM assigns `scenario_id` on each generated scenario. Building the matrix table and
appending it below the untouched existing description is done deterministically in
`app/graph/nodes/post_test_scenario_matrix.py` (not left to an LLM) so the "retain existing verbiage
exactly" requirement can't be undermined by imprecise text reproduction — it reads `state["description"]`
verbatim and appends below it, then calls `JiraMCPClient.update_description`.

## Project Reference Preservation (AI - Build Story, project key PROJ)

`PROJ-*` tickets must always route "In Dev" work to the `dice-roll` project. Since AI - Build Story
overwrites the whole description, and routing depends on a `Project: <name>` line surviving inside it
(`app/utils/ticket_parsing.extract_project_reference`), the AI - Build Story rubric must require that line
be regenerated every time, not just preserved by chance:

- If the ticket key starts with `PROJ-`, the new description's first line must be exactly
  `Project: dice-roll`.
- Tickets outside `PROJ` must not get this line added.

Operationalized in `backend/app/graph/prompts/ai_resolve_story_rubric.md` (the "Project reference
line" section, ordered before the User Story section so it lands as the literal first line of the
generated description). No ticket-key branching lives in `generate_approach.py` itself — the rubric
text is unconditional (it already includes the `PROJ-` prefix check), so the node stays a plain
"load rubric, send prompt" shape; only the rubric changes if another project key ever needs the same
treatment.

#when generating autmoated tests, make sure the automation tests reference the test scenario identifier in the test generation file.

## AI - Requirement Review

Triggered by moving a ticket to "AI - Requirement Review" (the live PROJ workflow's status name —
`Settings.trigger_statuses` must always match Jira's actual status name exactly, since the poller
matches on the literal string; this project's status names have been renamed more than once, so treat
`config.py`'s `trigger_statuses` dict, not this doc, as the source of truth if they ever drift).
Reviews the ticket's summary, description, and acceptance criteria for genuinely ambiguous
requirements — statements an engineer could reasonably interpret more than one way — and appends
specific, answerable clarifying questions to the bottom of the description, one per ambiguity found,
each with an `Answer: _(pending)_` placeholder so a stakeholder can fill it in directly in Jira.
Existing description content is retained in full above the new section (same append-don't-replace
approach as the test scenario matrix, not AI - Build Story's full-replace).

- `app/graph/prompts/ambiguity_review_instructions.md` — the actual rubric sent to the LLM: what
  counts as ambiguity worth flagging (vs. plain undecided scope), and the requirement that each
  question be concrete enough to close with a one- or two-sentence answer.
- `app/llm/ambiguity_llm.py` — direct `ChatAnthropic` structured-output call (same shape as
  `scenario_llm.py`; no Claude Code CLI / project checkout needed, since ambiguity review only looks
  at the ticket text itself) producing a list of `{requirement, question}` pairs.
- `graph/nodes/review_requirement_ambiguity.py` runs that LLM call; `graph/nodes/post_ambiguity_questions.py`
  builds the actual Markdown section **in code** (not left to the LLM) and appends it below
  `state["description"]` verbatim, then calls `JiraMCPClient.update_description` — the same
  deterministic-formatting-over-LLM-formatting choice made for the test scenario matrix, so "retain
  existing content exactly" can't be undermined by imprecise reproduction.
- If no ambiguity is found, `post_ambiguity_questions` is a no-op — it does not touch the description
  at all rather than posting an empty section.

