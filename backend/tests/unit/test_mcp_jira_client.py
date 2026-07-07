import json

import pytest

from app.mcp_jira.client import JiraMCPClient, _sanitize_for_jira, get_jira_client


class FakeTool:
    def __init__(self, result):
        self._result = result
        self.calls = []

    async def ainvoke(self, kwargs):
        self.calls.append(kwargs)
        return self._result


@pytest.fixture
def client():
    return JiraMCPClient()


def _wire(client, tools: dict):
    client._tools_by_name = tools


async def test_get_issue_returns_parsed_json(client):
    tool = FakeTool([{"type": "text", "text": '{"key": "PROJ-1"}'}])
    _wire(client, {"jira_get_issue": tool})

    result = await client.get_issue("PROJ-1")

    assert result == {"key": "PROJ-1"}
    assert tool.calls[0] == {"issue_key": "PROJ-1"}


async def test_search_issues_passes_comma_joined_fields(client):
    tool = FakeTool([{"type": "text", "text": '{"issues": [{"key": "PROJ-1"}]}'}])
    _wire(client, {"jira_search": tool})

    result = await client.search_issues("project = PROJ", ["summary", "status"], max_results=10)

    assert result == [{"key": "PROJ-1"}]
    assert tool.calls[0]["fields"] == "summary,status"
    assert tool.calls[0]["limit"] == 10


async def test_search_issues_handles_results_key(client):
    tool = FakeTool([{"type": "text", "text": '{"results": [{"key": "X-1"}]}'}])
    _wire(client, {"jira_search": tool})

    assert await client.search_issues("jql", ["summary"]) == [{"key": "X-1"}]


async def test_search_issues_returns_list_passthrough(client):
    tool = FakeTool([{"type": "text", "text": "[]"}])
    _wire(client, {"jira_search": tool})

    assert await client.search_issues("jql", ["summary"]) == []


async def test_add_comment_calls_tool_with_body_param(client):
    tool = FakeTool([{"type": "text", "text": "{}"}])
    _wire(client, {"jira_add_comment": tool})

    await client.add_comment("PROJ-1", "hello")

    assert tool.calls[0] == {"issue_key": "PROJ-1", "body": "hello"}


async def test_update_description_sends_json_encoded_fields(client):
    tool = FakeTool([{"type": "text", "text": "{}"}])
    _wire(client, {"jira_update_issue": tool})

    await client.update_description("PROJ-1", "new description")

    assert tool.calls[0]["issue_key"] == "PROJ-1"
    assert json.loads(tool.calls[0]["fields"]) == {"description": "new description"}


async def test_add_comment_sanitizes_smart_characters(client):
    tool = FakeTool([{"type": "text", "text": "{}"}])
    _wire(client, {"jira_add_comment": tool})

    smart_text = "It’s a “good” change — ship it…"
    await client.add_comment("PROJ-1", smart_text)

    assert tool.calls[0]["body"] == "It's a \"good\" change - ship it..."


async def test_update_description_sanitizes_smart_characters(client):
    tool = FakeTool([{"type": "text", "text": "{}"}])
    _wire(client, {"jira_update_issue": tool})

    smart_text = "Range: 5–10 — see note"
    await client.update_description("PROJ-1", smart_text)

    sent = json.loads(tool.calls[0]["fields"])
    assert sent["description"] == "Range: 5-10 - see note"


def test_sanitize_for_jira_replaces_smart_punctuation():
    text = "‘single’ “double” –en—em…"
    assert _sanitize_for_jira(text) == "'single' \"double\" -en-em..."


def test_sanitize_for_jira_replaces_non_breaking_space():
    text = "no break"
    assert _sanitize_for_jira(text) == "no break"


def test_sanitize_for_jira_strips_control_characters_but_keeps_newlines_and_tabs():
    text = "line one\nline\ttwo\x00\x07end"
    result = _sanitize_for_jira(text)
    assert result == "line one\nline\ttwoend"
    assert "\x00" not in result
    assert "\x07" not in result


def test_sanitize_for_jira_leaves_plain_ascii_unchanged():
    assert _sanitize_for_jira("Plain ASCII text, nothing to change.") == "Plain ASCII text, nothing to change."


async def test_call_raises_when_tool_missing(client):
    _wire(client, {})
    with pytest.raises(RuntimeError, match="did not expose"):
        await client._call("jira_get_issue", issue_key="X")


async def test_call_raises_on_error_response(client):
    tool = FakeTool([{"type": "text", "text": "Error: invalid issue"}])
    _wire(client, {"jira_get_issue": tool})
    with pytest.raises(RuntimeError, match="failed"):
        await client._call("jira_get_issue", issue_key="X")


async def test_call_raises_on_validation_error_text(client):
    tool = FakeTool([{"type": "text", "text": "1 validation error for call[foo]"}])
    _wire(client, {"jira_get_issue": tool})
    with pytest.raises(RuntimeError, match="failed"):
        await client._call("jira_get_issue", issue_key="X")


async def test_call_does_not_false_positive_on_error_wording_inside_valid_json(client):
    # Regression test: a *successful* response whose JSON payload happens to contain the words
    # "error" / "validation error" as legitimate field content (e.g. a ticket description that
    # discusses API error handling) must not be mistaken for a real mcp-atlassian failure.
    payload = json.dumps(
        {
            "message": "Issue updated successfully",
            "issue": {"description": "Then the backend shall return a validation error message."},
        }
    )
    tool = FakeTool([{"type": "text", "text": payload}])
    _wire(client, {"jira_update_issue": tool})

    result = await client._call("jira_update_issue", issue_key="X", fields="{}")

    assert result["message"] == "Issue updated successfully"


def test_normalize_handles_plain_string_json():
    assert JiraMCPClient._normalize("tool", '{"a": 1}') == {"a": 1}


def test_normalize_handles_unparseable_string():
    assert JiraMCPClient._normalize("tool", "not json") == {"raw": "not json"}


def test_normalize_passthrough_for_dict():
    assert JiraMCPClient._normalize("tool", {"already": "dict"}) == {"already": "dict"}


def test_normalize_handles_unparseable_list_text():
    assert JiraMCPClient._normalize("tool", [{"type": "text", "text": "not json"}]) == {"raw": "not json"}


def test_normalize_combines_multiple_text_blocks():
    blocks = [{"type": "text", "text": "part1"}, {"type": "text", "text": "part2"}]
    assert JiraMCPClient._normalize("tool", blocks) == {"raw": "part1\npart2"}


async def test_tools_fetches_and_caches(client):
    class FakeToolObj:
        def __init__(self, name):
            self.name = name

    class FakeMCPClient:
        def __init__(self):
            self.calls = 0

        async def get_tools(self):
            self.calls += 1
            return [FakeToolObj("jira_get_issue")]

    fake_mcp_client = FakeMCPClient()
    client._client = fake_mcp_client

    tools = await client._tools()
    assert "jira_get_issue" in tools

    tools_again = await client._tools()
    assert tools_again is tools
    assert fake_mcp_client.calls == 1


def test_get_jira_client_singleton():
    assert get_jira_client() is get_jira_client()
