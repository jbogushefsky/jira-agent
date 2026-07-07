from pathlib import Path

from app.config import get_settings

settings = get_settings()


class ProjectNotFoundError(Exception):
    pass


def resolve_project_path(project_name: str) -> Path:
    root = Path(settings.workspaces_root).resolve()
    candidate = (root / project_name).resolve()

    if root not in candidate.parents and candidate != root:
        raise ProjectNotFoundError(f"'{project_name}' resolves outside the workspaces root")
    if candidate.name == "jira-agent":
        raise ProjectNotFoundError("refusing to target the jira-agent project's own folder")
    if not candidate.is_dir():
        raise ProjectNotFoundError(f"project folder not found: {candidate}")
    return candidate
