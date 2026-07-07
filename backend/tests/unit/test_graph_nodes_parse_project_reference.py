import pytest

from app.graph.nodes import parse_project_reference as mod


async def test_parse_project_reference_resolves_path(monkeypatch, tmp_path):
    project_dir = tmp_path / "dice-roll"
    project_dir.mkdir()
    monkeypatch.setattr(mod, "resolve_project_path", lambda name: project_dir)

    result = await mod.parse_project_reference.__wrapped__({"ticket_key": "PROJ-1", "project_name": "dice-roll"})
    assert result["project_path"] == str(project_dir)
    assert result["project_name"] == "dice-roll"


async def test_parse_project_reference_raises_when_no_project_name():
    with pytest.raises(ValueError, match="no 'Project: <name>' reference"):
        await mod.parse_project_reference.__wrapped__({"ticket_key": "PROJ-2"})
