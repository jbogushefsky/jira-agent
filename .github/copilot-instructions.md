# Copilot Instructions for jira-agent

This is a LangGraph-orchestrated agent system that reacts to Jira ticket status changes via a FastAPI backend, integrating Claude Code CLI, MCP servers, and multiple AI-driven workflows.

## Quick Start Commands

All commands run from the `backend/` directory unless noted otherwise.

### Development
- **Install dependencies:** `pip install -e ".[dev]"` (installs with pytest, ruff, mypy)
- **Run tests:** `pytest` (200+ unit tests at ~99% coverage)
  - Single test: `pytest tests/unit/test_graph_graph.py::test_build_graph_structure`
  - With coverage: `pytest --cov=app --cov-report=term-missing`
- **Lint:** `ruff check .` (fix with `ruff check --fix .`)
- **Type check:** `mypy app`
- **Database migrations:** `alembic upgrade head` (create with `alembic revision --autogenerate -m "..."`)

### Running Locally
- **Backend REST/WS API:** `uvicorn app.main:app --reload --port 8000`
- **jira-agent-mcp service:** `uvicorn app.mcp_server.app:app --reload --port 8010`
- **Full stack (Docker):** From root, `docker compose up --build` (runs backend, jira-agent-mcp, mcp-atlassian, otel-collector, jaeger, prometheus)

**Setup required:** Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY`, `JIRA_URL`/`JIRA_USERNAME`/`JIRA_API_TOKEN`, `JIRA_PROJECT_KEYS`, `LANGCHAIN_API_KEY`. Postgres must be running on localhost:5432 (connects via `host.docker.internal` from containers).

## High-Level Architecture

### Poll → Transition → Flow Pattern
1. **Poller** (`app/poller/scheduler.py`) runs on an APScheduler interval, JQL-searches Jira for configured project keys
2. **Diff detection** (`app/poller/diff.py`) compares status against last-seen, fires flow if transition matches `Settings.trigger_statuses`
3. **Flow execution** (`app/graph/graph.py`) is a `StateGraph[GraphState]` with entry node `fetch_ticket_details` that branches into 5 independent chains, all converging on `finalize_flow`/`handle_failure`

### The Five Transitions
- **-> AI - Story Review:** Claude Code evaluates ticket, posts recommendations as Jira comment
- **-> AI - Build Story:** Claude Code generates implementation approach, overwrites ticket description
- **-> AI - Generate Test Scenarios:** LLM generates test scenarios with traceability IDs, appends matrix to description
- **-> AI - Requirement Review:** LLM reviews for ambiguous requirements, appends clarifying questions
- **-> In Dev:** Claude Code generates code changes + tests in sibling project folder (resolved from `Project: <name>` reference)

### Graph Routing Pattern
Nodes never raise on business failures—they return `{"error": "..."}` in their state update. The router (`app/graph/router.py`) reads this and redirects to `handle_failure` instead. Every node is wrapped in `nodes/common.with_step_tracking(step_name)`, which:
- Persists `FlowStep` row before/after execution
- Broadcasts `step_started`/`step_updated` over WebSocket for live UI
- Converts exceptions to `state["error"]` convention

### Persistence Layer
All app tables live in dedicated `jira_agent` Postgres schema (`app/db/models.py`):
- `tickets` → `ticket_status_history` → `flows` → `flow_steps`
- `test_scenarios` and `code_changes` hang off `flows`
- Unique index on `flows(ticket_id, transition_type, status)` prevents duplicate `pending`/`running` flows; poller treats `IntegrityError` as expected "skip duplicate" case

### Claude Code Integration
`app/graph/claude_cli.py::run_claude_code` shells out to real `claude` CLI as subprocess with JSON event stream parsing:
- Supports `--resume <session_id>` so `generate_tests` can continue the session `generate_code_changes` started
- Loads `CLAUDE.md` from target project automatically if it exists
- Runs with `cwd` at resolved project path (or scratch tempdir if no project)
- For `generate_code_changes`/`generate_tests`, project-specific CLAUDE.md is auto-discovered; for `evaluate_ticket`/`generate_approach`, prompts explicitly point at it

### Two Tracing Layers
- **LangSmith** (`observability/langsmith_setup.py`): Agent layer—traces every LangGraph node and Claude CLI calls; dashboard "view trace" links point here
- **OpenTelemetry** (`observability/otel_setup.py`): Infrastructure layer—HTTP spans via `FastAPIInstrumentor`, SQL spans via `SQLAlchemyInstrumentor`, exported to Jaeger (localhost:16687); **CRITICAL:** OpenTelemetry must be configured at module level in `main.py` before middleware setup—instrumenting from `lifespan()` silently fails

### Dual MCP Role (Split Across Services)
- **Backend consumes:** `mcp_jira/client.py` talks to `mcp-atlassian` container for Jira reads/writes
- **Backend exposes:** `mcp_server/server.py` is a FastMCP instance with `list_processed_tickets`, `get_ticket_flow`, etc.
  - Used to run in same process; now separate service `jira-agent-mcp` (port 8010) for independent scaling
  - Still shares codebase and Postgres; only `backend` runs Alembic migrations

### Frontend (Separate Project)
[jira-agent-ui](../jira-agent-ui) is standalone Vite + React + TanStack Query. Talks only to this backend's REST API (`app/api/rest.py`) via absolute `VITE_API_BASE_URL`. WebSocket surface (`app/api/ws.py`, `app/api/broadcaster.py`) exists but frontend doesn't yet use it.

## Key Conventions

### Error Handling in Graph Nodes
```python
# ✅ Correct: return error in state update
return {"error": "Failed to fetch ticket: ..."}

# ❌ Wrong: raising exceptions
raise ValueError("...")  # caught by decorator, converted to error automatically
```

### Step Tracking Decorator
Every node function that should appear in flow history must be decorated:
```python
@with_step_tracking("step-display-name")
async def my_node(state: GraphState) -> dict:
    # The decorator sets .step_name attribute on the function
```
`NODE_STEP_NAMES` maps node function names to their display step names (e.g., `evaluate_ticket` → `claude-code-evaluate`); these deliberately differ to allow flexible labeling.

### Project Resolution
- Tickets can reference target projects via `Project: <name>` in summary or description
- `utils/ticket_parsing.extract_project_reference()` extracts this
- `utils/project_paths.resolve_project_path()` maps to `/workspaces/<name>` (container-mounted host dir)
- Resolves only to siblings of `jira-agent`, never to `jira-agent` itself

### Test Scenario Traceability
When AI - Generate Test Scenarios writes scenarios:
- Each must have unique ID: `{JIRA-TICKET}-AC-##-TC-##` (acceptance criterion index, then scenario index within that criterion)
  - Example: `PROJ-42-AC-01-TC-01`, `PROJ-42-AC-01-TC-02`, `PROJ-42-AC-02-TC-01`
- Scenarios presented as matrix (ID / AC / Scenario / Given-When-Then) appended below existing description (retain all existing text above)
- Deterministic formatting done in `nodes/post_test_scenario_matrix.py` (not by LLM) so exact text preservation can't be undermined

### Ambiguity Review Output
- AI - Requirement Review appends clarifying questions to bottom of description (append, not replace)
- Each question has `Answer: _(pending)_` placeholder for stakeholder to fill in Jira
- If no ambiguity found, no-op (do not post empty section)
- Deterministic formatting in `nodes/post_ambiguity_questions.py` to ensure exact preservation of existing content

### AI - Build Story Description Replacement
- **Unique:** This is the only transition that replaces the entire description
- For tickets with keys starting with `PROJ-`, first line of new description must be exactly `Project: dice-roll`
- Other projects must not get this line added
- Rubric at `app/graph/prompts/ai_resolve_story_rubric.md` enforces this unconditionally

### SessionID Preservation for Claude Code Continuation
- `generate_code_changes` returns `session_id` in its state update
- `generate_tests` checks for `session_id` and passes `--resume <session_id>` to Claude CLI
- Falls back to feeding `git diff` if no `session_id` available

### Workflow Diagram Generation
- `GET /api/graph` derives from LangGraph's own `get_graph().draw_mermaid()`, not hand-maintained
- `NODE_STEP_NAMES` dict is single source of truth for node registration
- Conditional edges render dashed with `path_map` key as label (e.g., `to_story_review`, `to_generate_test_scenarios`)
- Frontend (`jira-agent-ui/components/flow/WorkflowDiagram.tsx`) highlights nodes via inline SVG styles (not CSS classes, to beat mermaid's specificity)

## When Modifying Key Areas

### Adding a New LLM Call (Non-Claude-Code)
- Create structured-output LLM call in `app/llm/` (similar to `scenario_llm.py`, `ambiguity_llm.py`)
- Use `ChatAnthropic` directly with `structured_output` mode
- Create graph node in `app/graph/nodes/` to call it
- Add node to `NODE_FUNCTIONS` dict in `graph.py` to register it
- Wrap with `@with_step_tracking("step-name")`

### Adding a New Claude Code Integration
- Create node function in `app/graph/nodes/`
- Call `run_claude_code()` with appropriate `cwd` (project_path if exists, else scratch tempdir)
- If node should reuse a session, save `session_id` from previous node and pass `--resume <session_id>`
- Wrap with `@with_step_tracking("step-name")`
- Add to `NODE_FUNCTIONS` dict

### Modifying Database Schema
- Edit `app/db/models.py` to update SQLAlchemy model
- Run `alembic revision --autogenerate -m "description"`
- Review the generated migration in `app/db/migrations/`
- Run `alembic upgrade head` to apply locally before committing

### Adding/Modifying a Jira Operation
- Use `JiraMCPClient` from `mcp_jira/client.py` (wraps MCP calls to `mcp-atlassian`)
- Examples: `get_issue()`, `update_description()`, `add_comment()`, `get_custom_field_value()`
- Errors bubble up as exceptions; caller is responsible for error handling (typically returns `{"error": "..."}` in graph node)

### Testing Claude Code Invocations
- Use `tests/unit/test_claude_cli.py` as reference
- Mock `subprocess.run()` to avoid real CLI calls
- Verify JSON event stream parsing
- Test session ID preservation when relevant

## Test Coverage Expectations
- Unit tests in `tests/unit/` (200+ tests, ~99% coverage)
- Test file naming: `test_<module_path>.py` (e.g., `test_graph_nodes_fetch_ticket_details.py` for `app/graph/nodes/fetch_ticket_details.py`)
- Test coverage enforced at 90% minimum (configured in `pyproject.toml`)
- `tests/integration/` exists but is still empty (focus on unit tests for now)

## Environment & Debugging

### Local Development
- Postgres must be running before `docker compose up --build`
- Backend API healthcheck: `curl http://localhost:8000/api/health`
- MCP healthcheck: `curl http://localhost:8010/health`
- Jaeger UI: http://localhost:16687
- Prometheus: http://localhost:9091
- Backend debugpy (VS Code): attach to localhost:5678

### Docker Compose Networking
- Backend/MCP communicate with Jira via `mcp-atlassian` service (http://mcp-atlassian:9000/mcp)
- Backend communicates with Postgres via `host.docker.internal` (host gateway)
- Services on `jira-agent-net` bridge network

### Observability
- LangSmith traces: check `LANGCHAIN_PROJECT` (default: `jira-agent-dev`)
- OpenTelemetry spans: Jaeger, Prometheus
- Structured logs: `structlog` configured in `app/logging_config.py`

## Integration with Separate Frontend Project
[jira-agent-ui](../jira-agent-ui) is a standalone project:
- Runs on separate `docker compose up --build` in its own directory
- Talks to backend REST API only (not graph or DB directly)
- Environment: `VITE_API_BASE_URL` (absolute URL, e.g., http://localhost:8000)
- Real-time flow updates via WebSocket `/ws/flows` (infrastructure exists, not yet used by frontend)

## MCP Servers for Development

The following MCP servers can be configured in your IDE to enhance development workflows:

### Postgres MCP
For querying the `jira_agent` schema directly during debugging:
- **Use case:** Inspect `tickets`, `flows`, `flow_steps`, `test_scenarios` tables; check migration status
- **Connection:** localhost:5432, database `vectorjira`, user/password from `.env`
- **Helpful queries:** 
  - Get recent flows: `SELECT * FROM jira_agent.flows ORDER BY created_at DESC LIMIT 5;`
  - Check flow steps: `SELECT fs.* FROM jira_agent.flow_steps fs WHERE fs.flow_id = <id>;`

### Filesystem MCP
For exploring test files and understanding code organization:
- **Use case:** Search `tests/unit/` for existing test patterns before writing new tests
- **Root directory:** `backend/`

### GitHub MCP
For managing issues and PRs (if applicable):
- **Use case:** Linking code changes to issues, reviewing/approving PRs, tracking project board status
- **Note:** Requires GitHub CLI (`gh`) and authentication; configure with repository owner/name if not already set
