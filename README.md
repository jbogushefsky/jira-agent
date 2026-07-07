# jira-agent

LangGraph-orchestrated agents that react to Jira ticket status changes, backed by a FastAPI service
(REST + WebSocket). The dashboard for inspecting every agent run lives in the separate
[jira-agent-ui](../jira-agent-ui) project; this project's own MCP server (for external MCP clients
querying processed tickets/flows) runs as its own `jira-agent-mcp` service, split out from the main
backend process — see "Running it" below.

## What it does

A background poller checks Jira (via a self-hosted `mcp-atlassian` MCP server) on an interval and
detects ticket status transitions:

- **-> AI - Story Review**: Claude Code evaluates the ticket and posts recommendations back as a Jira comment.
- **-> AI - Generate Test Scenarios**: generates test scenarios (each with a unique traceability ID) covering every
  acceptance criterion, and appends them as a matrix at the bottom of the ticket's description.
- **-> In Dev**: Claude Code generates the code changes (and tests) in the sibling project folder named
  by the ticket's `Project: <name>` field.
- **-> AI - Build Story**: Claude Code works out its implementation approach (grounded in the target project's
  code, if one is referenced) and replaces the ticket's description with it.
- **-> AI - Requirement Review**: reviews the description for ambiguous requirements and appends
  specific clarifying questions (with an answer placeholder) to the bottom of the description.

Every step of every run is persisted (inputs/outputs, timing, status) in Postgres and traced in LangSmith.
[jira-agent-ui](../jira-agent-ui) lists processed tickets, their agent flows, and lets you inspect each
step's exact input/output, talking only to this project's REST API. The `jira-agent-mcp` service exposes
this project's own MCP server (`list_processed_tickets`, `get_ticket_flow`, ...) for external MCP clients —
it shares this codebase and Postgres with the backend but runs as its own container/process.

## Running it

1. `cp .env.example .env` and fill in `ANTHROPIC_API_KEY`, `JIRA_URL`/`JIRA_USERNAME`/`JIRA_API_TOKEN`,
   `JIRA_PROJECT_KEYS`, and `LANGCHAIN_API_KEY`.
2. Target project repos that Claude Code will modify for "In Dev" tickets must live as sibling folders
   directly under `C:/joa/vscode/<project-name>` — matching the `Project: <name>` text in the ticket.
3. `docker compose up --build` — runs `backend` (8000), `jira-agent-mcp` (8010), and `mcp-atlassian` together.
4. Backend API: http://localhost:8000/api · MCP endpoint: http://localhost:8010/mcp
5. For the dashboard, run [jira-agent-ui](../jira-agent-ui) separately (its own `docker compose up --build`,
   http://localhost:5173) — it's a standalone project now and just needs this backend reachable on :8000.

Postgres is **not** containerized here — the backend connects to your existing local `vectorjira`
database on `localhost:5432` via `host.docker.internal`. On first boot the backend runs Alembic
migrations that add a new `jira_agent` schema to that database; nothing else in it is touched.
`jira-agent-mcp` depends on `backend` being healthy first, since `backend` is what runs those migrations.

See `docs/PLAN.md`-equivalent context in the original design plan for architecture details.
