"""Facade over the sooperset/mcp-atlassian MCP server via langchain-mcp-adapters.

We use langchain-mcp-adapters (not the raw `mcp` SDK) because it returns LangChain
StructuredTool objects that plug directly into LangGraph nodes and get automatic
nested LangSmith tracing for free.

Tool names below (jira_get_issue / jira_search / jira_add_comment) are mcp-atlassian's
documented tool names as of the version pinned in docker-compose.yml. Confirm via
`await client.get_tools()` if mcp-atlassian is upgraded and these calls start failing.
"""

import json
import unicodedata

from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()

_GET_ISSUE_TOOL = "jira_get_issue"
_SEARCH_TOOL = "jira_search"
_ADD_COMMENT_TOOL = "jira_add_comment"
_UPDATE_ISSUE_TOOL = "jira_update_issue"

# LLM output defaults to "smart" typographic Unicode punctuation (curly quotes, em/en dashes,
# ellipsis, non-breaking spaces) that Jira's wiki-markup/ADF conversion can render as mangled or
# unexpected characters — normalize to the plain-ASCII equivalent every writer already expects.
_SMART_CHAR_REPLACEMENTS = {
    "‘": "'",  # left single quotation mark
    "’": "'",  # right single quotation mark / apostrophe
    "‚": ",",  # single low-9 quotation mark
    "“": '"',  # left double quotation mark
    "”": '"',  # right double quotation mark
    "–": "-",  # en dash
    "—": "-",  # em dash
    "…": "...",  # horizontal ellipsis
    " ": " ",  # non-breaking space
}


def _sanitize_for_jira(text: str) -> str:
    for smart, plain in _SMART_CHAR_REPLACEMENTS.items():
        text = text.replace(smart, plain)
    # Strip any remaining control characters (Unicode category "Cc") — newline/tab are the only
    # ones with a legitimate place in ticket text.
    return "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch) != "Cc")


class JiraMCPClient:
    def __init__(self) -> None:
        self._client = MultiServerMCPClient(
            {
                "jira": {
                    "url": settings.mcp_atlassian_url,
                    "transport": "streamable_http",
                }
            }
        )
        self._tools_by_name: dict[str, StructuredTool] | None = None

    async def _tools(self) -> dict[str, StructuredTool]:
        if self._tools_by_name is None:
            tools = await self._client.get_tools()
            self._tools_by_name = {tool.name: tool for tool in tools}
            logger.info("jira_mcp_tools_loaded", tool_names=list(self._tools_by_name.keys()))
        return self._tools_by_name

    async def _call(self, tool_name: str, **kwargs) -> dict:
        tools = await self._tools()
        tool = tools.get(tool_name)
        if tool is None:
            raise RuntimeError(
                f"mcp-atlassian did not expose a '{tool_name}' tool; "
                f"available: {list(tools.keys())}"
            )
        result = await tool.ainvoke(kwargs)
        return self._normalize(tool_name, result)

    @staticmethod
    def _normalize(tool_name: str, result) -> dict:
        # mcp-atlassian's real responses (confirmed against a live instance) come back as a
        # list of MCP content blocks — [{"type": "text", "text": "<json-or-error-string>"}] —
        # not a bare string/dict as langchain-mcp-adapters docs might suggest. Unwrap that here
        # so every call site gets plain parsed JSON.
        if isinstance(result, list):
            texts = [b.get("text") for b in result if isinstance(b, dict) and b.get("type") == "text"]
            combined = "\n".join(t for t in texts if t)
            return JiraMCPClient._parse_or_raise(tool_name, combined)
        if isinstance(result, str):
            return JiraMCPClient._parse_or_raise(tool_name, result)
        return result

    @staticmethod
    def _parse_or_raise(tool_name: str, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Only text that ISN'T valid JSON gets scanned for error wording. mcp-atlassian's real
        # failure responses (a bad tool call — wrong param name/type) come back as a plain-text
        # pydantic validation dump, never as JSON — confirmed live this was the false-positive
        # bug: a *successful* jira_update_issue response is valid JSON whose "issue.description"
        # field can legitimately contain the words "error"/"validation error" as ticket content
        # (e.g. an AI - Build Story-generated story discussing API error handling), and the old
        # substring scan ran across that whole JSON blob before ever trying to parse it.
        lowered = text.strip().lower()
        if lowered.startswith("error") or "validation error" in lowered:
            raise RuntimeError(f"mcp-atlassian tool '{tool_name}' failed: {text}")
        return {"raw": text}

    async def get_issue(self, key: str) -> dict:
        return await self._call(_GET_ISSUE_TOOL, issue_key=key)

    async def search_issues(self, jql: str, fields: list[str], max_results: int = 100) -> list[dict]:
        # mcp-atlassian's jira_search tool wants `fields` as a comma-separated string, not a list
        # (confirmed against a live instance — passing a list raises a pydantic validation error).
        result = await self._call(_SEARCH_TOOL, jql=jql, fields=",".join(fields), limit=max_results)
        if isinstance(result, dict):
            return result.get("issues", result.get("results", []))
        return result if isinstance(result, list) else []

    async def add_comment(self, key: str, body: str) -> None:
        # mcp-atlassian's jira_add_comment tool names this param `body`, not `comment`
        # (confirmed live: the wrong name raised a pydantic validation error that was
        # silently swallowed as "success" until the error-detection heuristic above was fixed).
        await self._call(_ADD_COMMENT_TOOL, issue_key=key, body=_sanitize_for_jira(body))

    async def update_description(self, key: str, description: str) -> None:
        # mcp-atlassian's jira_update_issue tool wants `fields` as a JSON-encoded string, not a
        # dict (same string-not-native-type quirk as jira_search's `fields` param) — confirmed
        # live: passing a dict raised "fields Input should be a valid string [type=string_type]".
        await self._call(
            _UPDATE_ISSUE_TOOL,
            issue_key=key,
            fields=json.dumps({"description": _sanitize_for_jira(description)}),
        )


_jira_client: JiraMCPClient | None = None


def get_jira_client() -> JiraMCPClient:
    global _jira_client
    if _jira_client is None:
        _jira_client = JiraMCPClient()
    return _jira_client
