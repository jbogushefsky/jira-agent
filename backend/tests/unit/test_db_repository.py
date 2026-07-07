import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.db import repository as repo
from app.db.models import Flow, FlowStep, Ticket, TicketStatusHistory


class FakeResult:
    def __init__(self, scalar=None, scalars_list=None):
        self._scalar = scalar
        self._scalars_list = scalars_list if scalars_list is not None else []

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: self._scalars_list)


def make_session(execute_result=None, get_result=None):
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)
    session.get = AsyncMock(return_value=get_result)
    session.add = MagicMock()  # session.add() is sync on a real AsyncSession
    return session


def test_truncate_returns_none_for_none_payload():
    assert repo._truncate(None) is None


def test_truncate_passes_through_small_payload():
    payload = {"a": 1}
    assert repo._truncate(payload) is payload


def test_truncate_shrinks_oversized_payload(monkeypatch):
    monkeypatch.setattr(repo.settings, "max_step_output_bytes", 10)
    result = repo._truncate({"a": "x" * 100})
    assert result["truncated"] is True
    assert "preview" in result


async def test_upsert_ticket_creates_new_ticket():
    session = make_session(execute_result=FakeResult(scalar=None))
    ticket = await repo.upsert_ticket(
        session,
        jira_key="PROJ-1",
        jira_id="1",
        project_key="PROJ",
        summary="s",
        description="d",
        raw_fields={},
        status="In Progress",
        target_project_name="dice-roll",
    )
    assert ticket.jira_key == "PROJ-1"
    session.add.assert_called_once()
    session.flush.assert_awaited_once()


async def test_upsert_ticket_updates_existing_ticket():
    existing = Ticket(jira_key="PROJ-1", last_seen_status="To Do")
    session = make_session(execute_result=FakeResult(scalar=existing))

    ticket = await repo.upsert_ticket(
        session,
        jira_key="PROJ-1",
        jira_id="2",
        project_key="PROJ",
        summary="new summary",
        description="new desc",
        raw_fields={"a": 1},
        status="In Progress",
        target_project_name="dice-roll",
    )
    assert ticket is existing
    assert ticket.summary == "new summary"
    assert ticket.last_seen_status == "In Progress"
    session.add.assert_not_called()


async def test_record_status_change():
    session = make_session()
    ticket = Ticket(id=uuid.uuid4(), jira_key="PROJ-1", last_seen_status="To Do")
    history = await repo.record_status_change(session, ticket=ticket, from_status="To Do", to_status="In Progress")
    assert history.from_status == "To Do"
    assert history.to_status == "In Progress"
    assert ticket.last_seen_status == "In Progress"
    session.add.assert_called_once()


async def test_get_ticket_by_key_found_and_not_found():
    ticket = Ticket(jira_key="PROJ-1")
    assert await repo.get_ticket_by_key(make_session(FakeResult(scalar=ticket)), "PROJ-1") is ticket
    assert await repo.get_ticket_by_key(make_session(FakeResult(scalar=None)), "NOPE") is None


async def test_get_status_history_returns_ordered_list():
    row = TicketStatusHistory(from_status="To Do", to_status="In Progress")
    session = make_session(FakeResult(scalars_list=[row]))
    assert await repo.get_status_history(session, uuid.uuid4()) == [row]


async def test_list_processed_tickets_builds_items(monkeypatch):
    ticket = Ticket(jira_key="PROJ-1", summary="s", last_seen_status="In Dev", target_project_name="dice-roll")
    ticket.last_polled_at = datetime.now(timezone.utc)

    session = AsyncMock()
    count_result = MagicMock(scalar_one=MagicMock(return_value=1))
    session.execute = AsyncMock(side_effect=[count_result, FakeResult(scalars_list=[ticket])])

    flow = Flow(status="succeeded")
    flow.id = uuid.uuid4()
    flow.created_at = datetime.now(timezone.utc)
    monkeypatch.setattr(repo, "get_latest_flow", AsyncMock(return_value=flow))

    items, total = await repo.list_processed_tickets(session, status=None, project=None, limit=50, offset=0)
    assert total == 1
    assert items[0]["key"] == "PROJ-1"
    assert items[0]["overallFlowStatus"] == "succeeded"


async def test_list_processed_tickets_with_filters_and_no_latest_flow(monkeypatch):
    ticket = Ticket(jira_key="PROJ-2", summary="s", last_seen_status="To Do", target_project_name=None)
    ticket.last_polled_at = datetime.now(timezone.utc)

    session = AsyncMock()
    count_result = MagicMock(scalar_one=MagicMock(return_value=1))
    session.execute = AsyncMock(side_effect=[count_result, FakeResult(scalars_list=[ticket])])
    monkeypatch.setattr(repo, "get_latest_flow", AsyncMock(return_value=None))

    items, total = await repo.list_processed_tickets(session, status="To Do", project="proj", limit=10, offset=5)
    assert items[0]["overallFlowStatus"] == "unknown"
    assert items[0]["latestFlowId"] is None


async def test_list_processed_tickets_filters_by_project_key(monkeypatch):
    ticket = Ticket(jira_key="PROJ-1", summary="s", last_seen_status="In Dev", project_key="PROJ")
    ticket.last_polled_at = datetime.now(timezone.utc)

    session = AsyncMock()
    count_result = MagicMock(scalar_one=MagicMock(return_value=1))
    session.execute = AsyncMock(side_effect=[count_result, FakeResult(scalars_list=[ticket])])
    monkeypatch.setattr(repo, "get_latest_flow", AsyncMock(return_value=None))

    items, total = await repo.list_processed_tickets(session, project_key="PROJ", limit=50, offset=0)
    assert items[0]["projectKey"] == "PROJ"


async def test_get_latest_flow():
    flow = Flow(status="succeeded")
    assert await repo.get_latest_flow(make_session(FakeResult(scalar=flow)), uuid.uuid4()) is flow


async def test_create_flow():
    session = make_session()
    flow = await repo.create_flow(
        session, ticket_id=uuid.uuid4(), status_history_id=uuid.uuid4(), transition_type="to_in_dev"
    )
    assert flow.transition_type == "to_in_dev"
    assert flow.status == "pending"
    session.add.assert_called_once()


async def test_set_flow_status_updates_existing_flow_and_sets_completed_at():
    flow = Flow(status="running")
    session = make_session(get_result=flow)
    await repo.set_flow_status(session, uuid.uuid4(), status="succeeded", error_message="e", langsmith_run_id="r1")
    assert flow.status == "succeeded"
    assert flow.error_message == "e"
    assert flow.langsmith_run_id == "r1"
    assert flow.completed_at is not None


async def test_set_flow_status_noop_when_flow_missing():
    session = make_session(get_result=None)
    await repo.set_flow_status(session, uuid.uuid4(), status="failed")  # should not raise


async def test_set_flow_status_running_does_not_set_completed_at():
    flow = Flow(status="pending")
    session = make_session(get_result=flow)
    await repo.set_flow_status(session, uuid.uuid4(), status="running")
    assert flow.completed_at is None


async def test_set_flow_status_running_clears_stale_error_and_completed_at():
    # Simulates a replay: the flow previously failed (error_message + completed_at set), then
    # run_replay moves it back to "running" — the dashboard shouldn't keep showing the old error.
    flow = Flow(status="failed")
    flow.error_message = "unhandled graph invocation error"
    flow.completed_at = datetime.now(timezone.utc)
    session = make_session(get_result=flow)

    await repo.set_flow_status(session, uuid.uuid4(), status="running")

    assert flow.status == "running"
    assert flow.error_message is None
    assert flow.completed_at is None


async def test_set_flow_status_running_with_explicit_error_message_still_sets_it():
    flow = Flow(status="pending")
    session = make_session(get_result=flow)
    await repo.set_flow_status(session, uuid.uuid4(), status="running", error_message="explicit")
    assert flow.error_message == "explicit"


async def test_get_flows_for_ticket():
    flow = Flow(status="succeeded")
    assert await repo.get_flows_for_ticket(make_session(FakeResult(scalars_list=[flow])), "PROJ-1") == [flow]


async def test_get_flow_found():
    flow = Flow(status="succeeded")
    assert await repo.get_flow(make_session(get_result=flow), uuid.uuid4()) is flow


async def test_start_flow_step():
    session = make_session()
    step = await repo.start_flow_step(
        session, flow_id=uuid.uuid4(), step_name="fetch", step_order=1, input_payload={"a": 1}
    )
    assert step.step_name == "fetch"
    assert step.status == "running"
    session.add.assert_called_once()


async def test_finish_flow_step_computes_duration_with_naive_started_at():
    step = FlowStep(step_name="fetch", step_order=1, status="running")
    step.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session = make_session(get_result=step)

    result = await repo.finish_flow_step(session, uuid.uuid4(), status="succeeded", output={"ok": True})
    assert result.status == "succeeded"
    assert result.duration_ms >= 0


async def test_finish_flow_step_computes_duration_with_aware_started_at():
    step = FlowStep(step_name="fetch", step_order=1, status="running")
    step.started_at = datetime.now(timezone.utc)
    session = make_session(get_result=step)

    result = await repo.finish_flow_step(session, uuid.uuid4(), status="failed", error="boom")
    assert result.error == "boom"
    assert result.duration_ms >= 0


async def test_finish_flow_step_returns_none_when_missing():
    assert await repo.finish_flow_step(make_session(get_result=None), uuid.uuid4(), status="succeeded") is None


async def test_get_flow_steps():
    step = FlowStep(step_name="fetch", step_order=1)
    assert await repo.get_flow_steps(make_session(FakeResult(scalars_list=[step])), uuid.uuid4()) == [step]


async def test_get_step_found():
    step = FlowStep(step_name="fetch", step_order=1)
    assert await repo.get_step(make_session(get_result=step), uuid.uuid4()) is step


async def test_add_test_scenario():
    session = make_session()
    scenario = await repo.add_test_scenario(
        session,
        flow_id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        scenario_id="TC-01",
        acceptance_criterion="a",
        scenario_title="t",
        scenario_body="b",
    )
    assert scenario.scenario_id == "TC-01"
    session.add.assert_called_once()


async def test_add_code_change():
    session = make_session()
    change = await repo.add_code_change(
        session,
        flow_id=uuid.uuid4(),
        project_name="dice-roll",
        project_path="/workspaces/dice-roll",
        files_changed=None,
        summary="s",
        tests_summary="t",
    )
    assert change.project_name == "dice-roll"
    session.add.assert_called_once()
