from typing import Literal, TypedDict


class GraphState(TypedDict, total=False):
    flow_id: str
    ticket_id: str
    ticket_key: str
    transition: Literal[
        "to_story_review", "to_generate_test_scenarios", "to_in_dev", "to_build_story", "to_requirement_review"
    ]
    current_status: str
    ticket_fields: dict
    summary: str | None
    description: str | None
    acceptance_criteria: list[str]
    project_name: str | None
    project_path: str | None
    recommendations: str | None
    test_scenarios: list[dict]
    code_change_summary: str | None
    generated_description: str | None
    ambiguity_questions: list[dict]
    test_generation_summary: str | None
    claude_session_id: str | None
    error: str | None
    step_order: int
