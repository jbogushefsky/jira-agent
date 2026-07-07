import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import repository as repo
from app.db.session import session_scope
from app.logging_config import get_logger
from app.mcp_jira.client import get_jira_client
from app.poller.diff import compute_transition
from app.utils.ticket_parsing import extract_project_reference

logger = get_logger(__name__)
settings = get_settings()


def _build_jql() -> str:
    keys = settings.jira_project_key_list
    if keys:
        joined = ", ".join(keys)
        return f"project in ({joined}) ORDER BY updated DESC"
    # Jira Cloud rejects fully unbounded JQL ("unbounded JQL queries are not allowed") —
    # confirmed against a live instance. This restriction is the least-restrictive one that
    # still satisfies Jira, for when JIRA_PROJECT_KEYS isn't configured; set it for real use.
    return "project is not EMPTY ORDER BY updated DESC"


async def poll_jira_job() -> None:
    jira = get_jira_client()
    try:
        issues = await jira.search_issues(
            jql=_build_jql(),
            fields=["summary", "description", "status", "project"],
            max_results=200,
        )
    except Exception:
        logger.exception("jira_poll_failed")
        return

    for issue in issues:
        try:
            await _process_issue(issue)
        except Exception:
            logger.exception("issue_processing_failed", issue=issue.get("key"))


async def _process_issue(issue: dict) -> None:
    key = issue.get("key")
    fields = issue.get("fields", issue)
    if not key:
        return

    status = (fields.get("status") or {}).get("name") or fields.get("status")
    summary = fields.get("summary")
    description = fields.get("description")
    project_key = (fields.get("project") or {}).get("key")
    if not status:
        return

    project_hint = extract_project_reference(summary, description)

    async with session_scope() as session:
        existing = await repo.get_ticket_by_key(session, key)
        previous_status = existing.last_seen_status if existing else None

        ticket = await repo.upsert_ticket(
            session,
            jira_key=key,
            jira_id=issue.get("id"),
            project_key=project_key,
            summary=summary,
            description=description,
            raw_fields=fields,
            status=status,
            target_project_name=project_hint,
        )

        transition_type = compute_transition(previous_status, status)
        if transition_type is None:
            return

        history = await repo.record_status_change(
            session, ticket=ticket, from_status=previous_status, to_status=status
        )

        try:
            flow = await repo.create_flow(
                session,
                ticket_id=ticket.id,
                status_history_id=history.id,
                transition_type=transition_type,
            )
        except IntegrityError:
            logger.info("duplicate_active_flow_skipped", ticket_key=key, transition=transition_type)
            return

        flow_id = flow.id
        ticket_id = ticket.id

    logger.info("flow_triggered", ticket_key=key, transition=transition_type, flow_id=str(flow_id))

    from app.graph.graph import run_flow  # deferred import: avoids a poller<->graph import cycle

    asyncio.create_task(
        run_flow(
            flow_id=flow_id,
            ticket_id=ticket_id,
            ticket_key=key,
            transition_type=transition_type,
        )
    )


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        poll_jira_job,
        "interval",
        seconds=settings.poll_interval_seconds,
        max_instances=1,
        coalesce=True,
        id="poll_jira",
    )
    scheduler.start()
    return scheduler


def stop_scheduler(scheduler: AsyncIOScheduler) -> None:
    scheduler.shutdown(wait=False)
