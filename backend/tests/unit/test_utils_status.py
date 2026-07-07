from app.utils.status import classify_transition


def test_classify_known_statuses_returns_transition_type():
    assert classify_transition("AI - Story Review") == "to_story_review"
    assert classify_transition("AI - Generate Test Scenarios") == "to_generate_test_scenarios"
    assert classify_transition("In Dev") == "to_in_dev"
    assert classify_transition("AI - Build Story") == "to_build_story"


def test_classify_unknown_status_returns_none():
    assert classify_transition("To Do") is None
    assert classify_transition("Done") is None
    assert classify_transition("") is None
