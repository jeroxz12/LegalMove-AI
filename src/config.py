"""Configuración de la aplicación a partir de variables de entorno.

`load_settings` recibe las variables por parámetro en lugar de leer `os.environ`:
quien la invoca decide de dónde salen (el entorno real en `main.py`, un dict en los tests).
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from src.errors import ConfigError

DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 60.0
DEFAULT_OPENAI_MAX_RETRIES = 2


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(repr=False)
    openai_model: str
    openai_timeout_seconds: float
    openai_max_retries: int
    tracing_enabled: bool
    langfuse_public_key: str | None = field(default=None, repr=False)
    langfuse_secret_key: str | None = field(default=None, repr=False)
    langfuse_host: str | None = None


def load_settings(env: Mapping[str, str], *, tracing_enabled: bool = True) -> Settings:
    """Valida las variables y devuelve `Settings`, o lanza `ConfigError` con todos los problemas juntos.

    Los mensajes nombran las variables con problemas pero nunca muestran el valor de una clave.
    """
    problems: list[str] = []

    openai_api_key = _required(env, "OPENAI_API_KEY", problems)
    openai_model = _optional(env, "OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
    openai_timeout_seconds = _timeout(env, problems)
    openai_max_retries = _max_retries(env, problems)

    langfuse_public_key = langfuse_secret_key = langfuse_host = None
    if tracing_enabled:
        langfuse_public_key = _required(env, "LANGFUSE_PUBLIC_KEY", problems)
        langfuse_secret_key = _required(env, "LANGFUSE_SECRET_KEY", problems)
        langfuse_host = _required(env, "LANGFUSE_HOST", problems)
        if langfuse_host and not langfuse_host.startswith(("http://", "https://")):
            problems.append(f"LANGFUSE_HOST debe empezar con http:// o https:// (valor: {langfuse_host!r})")

    if problems:
        raise ConfigError(problems)

    return Settings(
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        openai_timeout_seconds=openai_timeout_seconds,
        openai_max_retries=openai_max_retries,
        tracing_enabled=tracing_enabled,
        langfuse_public_key=langfuse_public_key,
        langfuse_secret_key=langfuse_secret_key,
        langfuse_host=langfuse_host,
    )


def _optional(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


def _required(env: Mapping[str, str], name: str, problems: list[str]) -> str | None:
    value = _optional(env, name)
    if value is None:
        problems.append(f"{name} falta o está vacía")
    return value


def _timeout(env: Mapping[str, str], problems: list[str]) -> float:
    raw = _optional(env, "OPENAI_TIMEOUT_SECONDS")
    if raw is None:
        return DEFAULT_OPENAI_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        value = None
    if value is None or not math.isfinite(value) or value <= 0:
        problems.append(f"OPENAI_TIMEOUT_SECONDS debe ser un número mayor que 0 (valor: {raw!r})")
        return DEFAULT_OPENAI_TIMEOUT_SECONDS
    return value


def _max_retries(env: Mapping[str, str], problems: list[str]) -> int:
    raw = _optional(env, "OPENAI_MAX_RETRIES")
    if raw is None:
        return DEFAULT_OPENAI_MAX_RETRIES
    try:
        value = int(raw)
    except ValueError:
        value = None
    if value is None or value < 0:
        problems.append(f"OPENAI_MAX_RETRIES debe ser un entero mayor o igual a 0 (valor: {raw!r})")
        return DEFAULT_OPENAI_MAX_RETRIES
    return value
