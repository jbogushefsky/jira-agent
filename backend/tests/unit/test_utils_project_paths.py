import pytest

from app.utils import project_paths
from app.utils.project_paths import ProjectNotFoundError, resolve_project_path


def test_resolve_existing_project_path(tmp_path, monkeypatch):
    monkeypatch.setattr(project_paths.settings, "workspaces_root", str(tmp_path))
    (tmp_path / "dice-roll").mkdir()
    assert resolve_project_path("dice-roll") == (tmp_path / "dice-roll").resolve()


def test_resolve_missing_project_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(project_paths.settings, "workspaces_root", str(tmp_path))
    with pytest.raises(ProjectNotFoundError, match="not found"):
        resolve_project_path("does-not-exist")


def test_resolve_refuses_jira_agent_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(project_paths.settings, "workspaces_root", str(tmp_path))
    (tmp_path / "jira-agent").mkdir()
    with pytest.raises(ProjectNotFoundError, match="own folder"):
        resolve_project_path("jira-agent")


def test_resolve_refuses_path_outside_root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(project_paths.settings, "workspaces_root", str(root))
    with pytest.raises(ProjectNotFoundError, match="outside"):
        resolve_project_path("../outside")


def test_resolve_project_equal_to_root_is_allowed_but_fails_isdir_or_name_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(project_paths.settings, "workspaces_root", str(tmp_path))
    # candidate == root is allowed by the outside-root check; "." resolves to root itself,
    # which is a real directory, so this should succeed.
    assert resolve_project_path(".") == tmp_path.resolve()
