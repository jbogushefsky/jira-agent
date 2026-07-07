from app.poller.diff import compute_transition


def test_new_ticket_returns_none():
    assert compute_transition(None, "AI - Story Review") is None


def test_same_status_returns_none():
    assert compute_transition("AI - Story Review", "AI - Story Review") is None


def test_known_transition_returns_type():
    assert compute_transition("To Do", "AI - Story Review") == "to_story_review"
    assert compute_transition("AI - Story Review", "AI - Build Story") == "to_build_story"


def test_unrecognized_status_returns_none():
    assert compute_transition("AI - Story Review", "Blocked") is None
