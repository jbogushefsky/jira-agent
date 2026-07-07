from app.graph.nodes.common import with_step_tracking
from app.graph.state import GraphState
from app.utils.project_paths import resolve_project_path


@with_step_tracking("parse-project-reference")
async def parse_project_reference(state: GraphState) -> dict:
    project_name = state.get("project_name")
    if not project_name:
        raise ValueError(
            f"ticket {state['ticket_key']} moved to 'In Dev' but no 'Project: <name>' "
            "reference was found in its summary/description"
        )
    project_path = resolve_project_path(project_name)
    return {"project_name": project_name, "project_path": str(project_path)}
