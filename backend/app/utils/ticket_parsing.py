import re

from app.config import get_settings

_PROJECT_RE = re.compile(r"Project:\s*([A-Za-z0-9._\-]+)", re.IGNORECASE)
_AC_SECTION_RE = re.compile(
    r"acceptance criteria[:\s]*\n?(.*?)(?:\n\n|\Z)", re.IGNORECASE | re.DOTALL
)
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$", re.MULTILINE)

settings = get_settings()


def extract_project_reference(*texts: str | None) -> str | None:
    """Finds 'Project: <name>' in ticket text (summary/description)."""
    for text in texts:
        if not text:
            continue
        match = _PROJECT_RE.search(text)
        if match:
            return match.group(1).strip()
    return None


def extract_acceptance_criteria(raw_fields: dict, description: str | None) -> list[str]:
    """Prefers a configured Jira custom field; falls back to parsing the description."""
    field_id = settings.jira_acceptance_criteria_field
    if field_id:
        value = raw_fields.get(field_id)
        if isinstance(value, str) and value.strip():
            return _split_criteria(value)
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]

    if not description:
        return []
    section_match = _AC_SECTION_RE.search(description)
    body = section_match.group(1) if section_match else description
    bullets = _BULLET_RE.findall(body)
    if bullets:
        return [b.strip() for b in bullets if b.strip()]
    return _split_criteria(body)


def _split_criteria(text: str) -> list[str]:
    lines = [line.strip(" -*•\t") for line in text.splitlines()]
    return [line for line in lines if line]
