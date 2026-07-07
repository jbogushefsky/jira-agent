from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Claude / Anthropic
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-5"

    # Jira
    jira_url: str = ""
    jira_username: str = ""
    jira_api_token: str = ""
    jira_project_keys: str = ""
    jira_acceptance_criteria_field: str = ""
    mcp_atlassian_url: str = "http://mcp-atlassian:9000/mcp"

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "jira-agent-dev"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # Postgres (existing host instance, not containerized by this project)
    postgres_host: str = "host.docker.internal"
    postgres_port: int = 5432
    postgres_db: str = "vectorjira"
    postgres_user: str = "postgres"
    postgres_password: str = "admin"

    # Poller / agent behavior
    poll_interval_seconds: int = 30
    workspaces_root: str = "/workspaces"
    trigger_statuses: dict[str, str] = {
        "AI - Story Review": "to_story_review",
        "AI - Generate Test Scenarios": "to_generate_test_scenarios",
        "In Dev": "to_in_dev",
        "AI - Build Story": "to_build_story",
        "AI - Requirement Review": "to_requirement_review",
    }
    max_step_output_bytes: int = 200_000
    claude_cli_timeout_seconds: int = 900

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def jira_project_key_list(self) -> list[str]:
        return [k.strip() for k in self.jira_project_keys.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
