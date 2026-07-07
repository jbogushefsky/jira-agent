from app.config import get_settings

settings = get_settings()


def classify_transition(to_status: str) -> str | None:
    """Maps a Jira status name to this system's internal transition_type, or None
    if the status isn't one we react to."""
    return settings.trigger_statuses.get(to_status)
