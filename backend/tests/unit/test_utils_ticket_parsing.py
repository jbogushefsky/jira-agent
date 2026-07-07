from app.utils import ticket_parsing
from app.utils.ticket_parsing import extract_acceptance_criteria, extract_project_reference


def test_extract_project_reference_from_summary():
    assert extract_project_reference("Project: dice-roll", None) == "dice-roll"


def test_extract_project_reference_from_description_when_summary_missing():
    assert extract_project_reference(None, "Some text\nProject: my-app\nmore") == "my-app"


def test_extract_project_reference_case_insensitive_and_trims_whitespace():
    assert extract_project_reference("project:   Foo-Bar", None) == "Foo-Bar"


def test_extract_project_reference_none_when_absent():
    assert extract_project_reference("no reference here", "still none") is None


def test_extract_project_reference_all_none_inputs():
    assert extract_project_reference(None, None) is None


def test_extract_acceptance_criteria_from_bulleted_description():
    description = "Acceptance Criteria:\n- one\n- two\n- three\n\nOther section"
    assert extract_acceptance_criteria({}, description) == ["one", "two", "three"]


def test_extract_acceptance_criteria_numbered_bullets():
    description = "Acceptance criteria\n1. first\n2. second"
    assert extract_acceptance_criteria({}, description) == ["first", "second"]


def test_extract_acceptance_criteria_no_description_returns_empty():
    assert extract_acceptance_criteria({}, None) == []


def test_extract_acceptance_criteria_no_bullets_falls_back_to_plain_lines():
    description = "Acceptance Criteria:\njust one plain line"
    assert extract_acceptance_criteria({}, description) == ["just one plain line"]


def test_extract_acceptance_criteria_prefers_configured_field_string(monkeypatch):
    monkeypatch.setattr(ticket_parsing.settings, "jira_acceptance_criteria_field", "customfield_100")
    raw_fields = {"customfield_100": "line one\nline two"}
    assert extract_acceptance_criteria(raw_fields, "ignored description") == ["line one", "line two"]


def test_extract_acceptance_criteria_configured_field_as_list(monkeypatch):
    monkeypatch.setattr(ticket_parsing.settings, "jira_acceptance_criteria_field", "customfield_100")
    raw_fields = {"customfield_100": ["a", "b", ""]}
    assert extract_acceptance_criteria(raw_fields, None) == ["a", "b"]


def test_extract_acceptance_criteria_configured_field_empty_falls_back_to_description(monkeypatch):
    monkeypatch.setattr(ticket_parsing.settings, "jira_acceptance_criteria_field", "customfield_100")
    raw_fields = {"customfield_100": ""}
    description = "Acceptance Criteria:\n- from description"
    assert extract_acceptance_criteria(raw_fields, description) == ["from description"]
