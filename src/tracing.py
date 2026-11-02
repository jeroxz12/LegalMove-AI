"""Observabilidad aislada del análisis: una falla de Langfuse nunca reemplaza el error ni el resultado del pipeline.

Cada falla de instrumentación se registra en el logger `legalmove.tracing`, que `count_tracing_errors()`
escucha junto con los loggers de Langfuse y OpenTelemetry.
"""

import logging
from contextlib import contextmanager

from langfuse import Langfuse

logger = logging.getLogger("legalmove.tracing")

# Loggers donde Langfuse, el exportador de OpenTelemetry y este módulo informan fallas de trazabilidad.
TRACING_LOGGERS = ("langfuse", "opentelemetry.exporter.otlp.proto.http.trace_exporter", logger.name)


@contextmanager
def observe(langfuse: Langfuse | None, name: str, **kwargs):
    """Abre una observación de Langfuse alrededor de una etapa.

    Sin Langfuse, o si la observación no se puede crear, la etapa corre igual y recibe `None`.
    Si la etapa falla, la observación queda con nivel ERROR y se propaga la excepción original.
    """
    if langfuse is None:
        yield None
        return
    try:
        manager = langfuse.start_as_current_observation(name=name, **kwargs)
        observation = manager.__enter__()
    except Exception as exc:
        report_failure(f"no se pudo crear la observación {name}", exc)
        yield None
        return

    try:
        yield observation
    except BaseException as exc:
        safe_update(observation, level="ERROR", status_message=f"{type(exc).__name__}: {exc}")
        _close(manager, name, exc)
        raise
    _close(manager, name, None)


def safe_update(observation, **kwargs) -> None:
    if observation is None:
        return
    try:
        observation.update(**kwargs)
    except Exception as exc:
        report_failure("no se pudo actualizar una observación", exc)


def current_trace_id(langfuse: Langfuse) -> str | None:
    try:
        return langfuse.get_current_trace_id()
    except Exception as exc:
        report_failure("no se pudo obtener el trace_id", exc)
        return None


def safe_flush(langfuse: Langfuse) -> None:
    try:
        langfuse.flush()
    except Exception as exc:
        report_failure("no se pudo enviar la traza a Langfuse", exc)


class ErrorCounter(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        self.count += 1


@contextmanager
def count_tracing_errors():
    """Cuenta los errores de trazabilidad registrados durante esta ejecución y retira el handler al terminar."""
    counter = ErrorCounter()
    loggers = [logging.getLogger(name) for name in TRACING_LOGGERS]
    for tracing_logger in loggers:
        tracing_logger.addHandler(counter)
    try:
        yield counter
    finally:
        for tracing_logger in loggers:
            tracing_logger.removeHandler(counter)


def _close(manager, name: str, error: BaseException | None) -> None:
    try:
        if error is None:
            manager.__exit__(None, None, None)
        else:
            manager.__exit__(type(error), error, error.__traceback__)
    except BaseException as exc:
        if exc is not error:
            report_failure(f"no se pudo cerrar la observación {name}", exc)


def report_failure(message: str, exc: BaseException) -> None:
    logger.error("%s: %s: %s", message, type(exc).__name__, exc)
