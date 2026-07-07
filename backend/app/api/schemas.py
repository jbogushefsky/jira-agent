from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ConfigResponse(BaseModel):
    jiraBaseUrl: str
    langsmithBaseUrl: str
    triggerStatuses: list[str]
    pollIntervalSeconds: int
    jiraProjectKeys: list[str]


class GraphDefinitionResponse(BaseModel):
    mermaid: str
    nodeStepNames: dict[str, str]


class TicketListItem(BaseModel):
    key: str
    title: str | None
    jiraStatus: str
    project: str | None
    projectKey: str | None = None
    lastProcessedAt: datetime
    overallFlowStatus: str
    latestFlowId: str | None


class TicketListResponse(BaseModel):
    items: list[TicketListItem]
    total: int
    limit: int
    offset: int


class StatusHistoryEntry(BaseModel):
    fromStatus: str | None
    toStatus: str
    detectedAt: datetime


class TicketDetailResponse(BaseModel):
    key: str
    title: str | None
    jiraStatus: str
    project: str | None
    jiraUrl: str
    statusHistory: list[StatusHistoryEntry]


class FlowSummary(BaseModel):
    flowId: str
    triggerStatus: str
    startedAt: datetime | None
    finishedAt: datetime | None
    status: str
    stepCount: int


class FlowStepSummary(BaseModel):
    id: str
    name: str
    order: int
    status: str
    startedAt: datetime
    finishedAt: datetime | None
    durationMs: int | None


class FlowStepDetail(BaseModel):
    id: str
    flowId: str
    name: str
    status: str
    startedAt: datetime
    finishedAt: datetime | None
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    error: str | None
    langsmithTraceUrl: str | None


class ReplayResponse(BaseModel):
    status: str
