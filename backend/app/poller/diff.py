from app.utils.status import classify_transition


def compute_transition(previous_status: str | None, current_status: str) -> str | None:
    """Returns this system's internal transition_type, or None if nothing should fire.

    A brand-new ticket (previous_status is None) only gets a baseline record — it does
    NOT trigger a flow, so the whole existing backlog isn't reprocessed on first boot.
    """
    if previous_status is None:
        return None
    if previous_status == current_status:
        return None
    return classify_transition(current_status)
