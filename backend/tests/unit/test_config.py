from app.config import Settings, get_settings


def test_database_url_builds_asyncpg_dsn():
    settings = Settings(
        postgres_user="u", postgres_password="p", postgres_host="h", postgres_port=5432, postgres_db="d"
    )
    assert settings.database_url == "postgresql+asyncpg://u:p@h:5432/d"


def test_jira_project_key_list_splits_and_strips():
    settings = Settings(jira_project_keys=" PROJ, OTHER ,, ")
    assert settings.jira_project_key_list == ["PROJ", "OTHER"]


def test_jira_project_key_list_empty_when_unset():
    settings = Settings(jira_project_keys="")
    assert settings.jira_project_key_list == []


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_default_trigger_statuses_cover_all_transitions():
    settings = Settings()
    assert set(settings.trigger_statuses.values()) == {
        "to_story_review",
        "to_generate_test_scenarios",
        "to_in_dev",
        "to_build_story",
        "to_requirement_review",
    }
