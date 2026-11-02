import pytest

from src.config import (
    DEFAULT_OPENAI_MAX_RETRIES,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OPENAI_TIMEOUT_SECONDS,
    load_settings,
)
from src.errors import ConfigError

OPENAI_KEY = "sk-test-openai-secret"
LANGFUSE_SECRET = "sk-lf-test-secret"
LANGFUSE_PUBLIC = "pk-lf-test-public"


def valid_env(**overrides: str) -> dict[str, str]:
    env = {
        "OPENAI_API_KEY": OPENAI_KEY,
        "LANGFUSE_PUBLIC_KEY": LANGFUSE_PUBLIC,
        "LANGFUSE_SECRET_KEY": LANGFUSE_SECRET,
        "LANGFUSE_HOST": "https://cloud.langfuse.com",
    }
    env.update(overrides)
    return env


def config_problems(env: dict[str, str], **kwargs) -> list[str]:
    with pytest.raises(ConfigError) as exc_info:
        load_settings(env, **kwargs)
    return exc_info.value.problems


def test_complete_config_applies_defaults():
    settings = load_settings(valid_env())

    assert settings.openai_api_key == OPENAI_KEY
    assert settings.openai_model == DEFAULT_OPENAI_MODEL
    assert settings.openai_timeout_seconds == DEFAULT_OPENAI_TIMEOUT_SECONDS
    assert settings.openai_max_retries == DEFAULT_OPENAI_MAX_RETRIES
    assert settings.tracing_enabled is True
    assert settings.langfuse_host == "https://cloud.langfuse.com"


def test_optional_values_override_defaults():
    env = valid_env(OPENAI_MODEL="gpt-4o-mini", OPENAI_TIMEOUT_SECONDS="45", OPENAI_MAX_RETRIES="1")

    settings = load_settings(env)

    assert settings.openai_model == "gpt-4o-mini"
    assert settings.openai_timeout_seconds == 45.0
    assert settings.openai_max_retries == 1


def test_missing_openai_key_is_reported():
    env = valid_env()
    del env["OPENAI_API_KEY"]

    assert config_problems(env) == ["OPENAI_API_KEY falta o está vacía"]


def test_all_missing_langfuse_variables_are_reported_together():
    env = {"OPENAI_API_KEY": OPENAI_KEY}

    problems = config_problems(env)

    assert len(problems) == 3
    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        assert any(name in problem for problem in problems)


def test_langfuse_is_not_required_when_tracing_is_disabled():
    settings = load_settings({"OPENAI_API_KEY": OPENAI_KEY}, tracing_enabled=False)

    assert settings.tracing_enabled is False
    assert settings.langfuse_public_key is None
    assert settings.langfuse_host is None


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_value_counts_as_missing(blank):
    assert config_problems(valid_env(OPENAI_API_KEY=blank)) == ["OPENAI_API_KEY falta o está vacía"]


@pytest.mark.parametrize("raw", ["abc", "0", "-5", "nan", "inf"])
def test_invalid_timeout_is_rejected(raw):
    problems = config_problems(valid_env(OPENAI_TIMEOUT_SECONDS=raw))

    assert len(problems) == 1
    assert "OPENAI_TIMEOUT_SECONDS" in problems[0]


@pytest.mark.parametrize("raw", ["1.5", "-1", "dos"])
def test_invalid_max_retries_is_rejected(raw):
    problems = config_problems(valid_env(OPENAI_MAX_RETRIES=raw))

    assert len(problems) == 1
    assert "OPENAI_MAX_RETRIES" in problems[0]


def test_langfuse_host_requires_http_scheme():
    problems = config_problems(valid_env(LANGFUSE_HOST="cloud.langfuse.com"))

    assert len(problems) == 1
    assert "LANGFUSE_HOST" in problems[0]


def test_secrets_are_not_exposed():
    settings = load_settings(valid_env())
    error_text = str(ConfigError(config_problems(valid_env(OPENAI_API_KEY="", OPENAI_MAX_RETRIES="x"))))

    for secret in (OPENAI_KEY, LANGFUSE_SECRET, LANGFUSE_PUBLIC):
        assert secret not in repr(settings)
        assert secret not in error_text


def test_reads_only_the_mapping_it_receives(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "valor-del-entorno-real")

    problems = config_problems({}, tracing_enabled=False)

    assert problems == ["OPENAI_API_KEY falta o está vacía"]


def test_invalid_langfuse_host_is_ignored_when_tracing_is_disabled():
    env = valid_env(LANGFUSE_HOST="cloud.langfuse.com")

    settings = load_settings(env, tracing_enabled=False)

    assert settings.tracing_enabled is False
    assert settings.langfuse_host is None