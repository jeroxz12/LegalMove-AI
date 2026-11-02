import os

import pytest

# Variables del entorno que cambian el muestreo, el destino o el proxy de los clientes que crean los tests.
_ENVIRONMENT_PREFIXES = ("OTEL_", "LANGFUSE_")
_PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")

_ORIGINAL_ENVIRON = dict(os.environ)


def pytest_configure(config) -> None:
    for name in list(os.environ):
        if name.startswith(_ENVIRONMENT_PREFIXES) or name.upper() in _PROXY_VARIABLES:
            del os.environ[name]


@pytest.fixture
def original_environ() -> dict[str, str]:
    """Entorno previo a la limpieza, para las pruebas de integración que ejecutan la CLI en un subproceso."""
    return dict(_ORIGINAL_ENVIRON)
