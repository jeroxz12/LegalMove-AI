import json
import logging
from contextlib import nullcontext

import httpx2
import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src import main as cli
from src import tracing
from src.config import load_settings
from src.errors import (
    AgentError,
    ExternalServiceError,
    IllegibleDocumentError,
    ImageParsingError,
)
from src.models import ContractChangeOutput

ORIGINAL = "data/test_contracts/documento_3__original.jpg"
AMENDMENT = "data/test_contracts/documento_3__enmienda.jpg"

CONTEXT_MAP = """## Tipo de adenda: REESCRITA

## Mapa de secciones
| ID original | ID en adenda | Propósito | Correspondencia |
|---|---|---|---|
| Cláusula 3 | Cláusula 3 | Precio del servicio | AMBOS |

## Observaciones
Ninguna"""

RESULT = ContractChangeOutput(
    sections_changed=["Cláusula 3"],
    topics_touched=["Precio"],
    summary_of_the_change='[MODIFICACIÓN] Cláusula 3 – Precio: de "USD 1.200" a "USD 1.250".',
)

ENV = {"OPENAI_API_KEY": "sk-test", "OPENAI_MAX_RETRIES": "0", "OPENAI_TIMEOUT_SECONDS": "5"}


def completion(content, finish_reason="stop"):
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }


class FakeOpenAI:
    """Responde como OpenAI según el tipo de llamada: Vision, mapa contextual o extracción."""

    def __init__(self, context_map=CONTEXT_MAP, extraction=None):
        self.context_map = context_map
        self.extraction = extraction or completion(RESULT.model_dump_json())
        self.calls = []

    def __call__(self, request):
        body = json.loads(request.content)
        if "image_url" in json.dumps(body):
            self.calls.append("vision")
            return httpx2.Response(200, json=completion("# CONTRATO\n\n## 3. Precio\nUSD 1.200"))
        if "response_format" in body:
            self.calls.append("extraction")
            return httpx2.Response(200, json=self.extraction)
        self.calls.append("contextualization")
        return httpx2.Response(200, json=completion(self.context_map))

    def client(self):
        return httpx2.Client(transport=httpx2.MockTransport(self))


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_TIMEOUT_SECONDS", "OPENAI_MAX_RETRIES",
                 "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(name, raising=False)
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)


def settings(langfuse_public_key=None):
    if langfuse_public_key is None:
        return load_settings(ENV, tracing_enabled=False)
    return load_settings({**ENV, "LANGFUSE_PUBLIC_KEY": langfuse_public_key, "LANGFUSE_SECRET_KEY": "sk-lf-test",
                          "LANGFUSE_HOST": "http://127.0.0.1:9"})


def in_memory_langfuse(public_key):
    exporter = InMemorySpanExporter()
    langfuse = Langfuse(public_key=public_key, secret_key="sk-lf-test", host="http://127.0.0.1:9",
                        span_exporter=exporter)
    return langfuse, exporter


# --- run_pipeline ---

def test_pipeline_runs_stages_in_order_and_traces_each_one():
    fake = FakeOpenAI()
    langfuse, exporter = in_memory_langfuse("pk-lf-test-main")
    trace_ids = []

    result = cli.run_pipeline(
        ORIGINAL, AMENDMENT, settings=settings("pk-lf-test-main"),
        vision_client=cli.build_vision_client(settings(), http_client=fake.client()),
        llm=cli.build_chat_model(settings(), http_client=fake.client()),
        langfuse=langfuse, on_trace_start=trace_ids.append,
    )
    langfuse.flush()

    assert result == RESULT
    assert fake.calls == ["vision", "vision", "contextualization", "extraction"]

    spans = exporter.get_finished_spans()
    assert {format(span.context.trace_id, "032x") for span in spans} == set(trace_ids)
    by_name = {span.name: span for span in spans}
    root = by_name["contract-analysis"]
    assert root.parent is None
    stages = ["parse_original_contract", "parse_amendment_contract", "contextualization_agent", "extraction_agent"]
    assert all(by_name[name].parent.span_id == root.context.span_id for name in stages)
    assert json.loads(root.attributes["langfuse.observation.output"]) == RESULT.model_dump()
    assert by_name["contextualization_agent"].attributes["langfuse.observation.output"] == CONTEXT_MAP
    assert json.loads(by_name["parse_original_contract"].attributes["langfuse.observation.output"]) == {
        "characters": len("# CONTRATO\n\n## 3. Precio\nUSD 1.200")
    }
    generations = [s for s in spans if s.attributes.get("langfuse.observation.type") == "generation"]
    assert len(generations) == 4


def test_ambiguous_map_stops_before_extraction_and_marks_the_trace_as_error():
    fake = FakeOpenAI(context_map=CONTEXT_MAP.replace("| AMBOS |", "| AMBIGUA |"))
    langfuse, exporter = in_memory_langfuse("pk-lf-test-main-error")

    with pytest.raises(AgentError, match="ambigua"):
        cli.run_pipeline(
            ORIGINAL, AMENDMENT, settings=settings("pk-lf-test-main-error"),
            vision_client=cli.build_vision_client(settings(), http_client=fake.client()),
            llm=cli.build_chat_model(settings(), http_client=fake.client()),
            langfuse=langfuse,
        )
    langfuse.flush()

    assert "extraction" not in fake.calls
    by_name = {span.name: span for span in exporter.get_finished_spans()}
    assert "extraction_agent" not in by_name
    for name in ("contract-analysis", "contextualization_agent"):
        assert by_name[name].attributes["langfuse.observation.level"] == "ERROR"


# --- main: códigos de salida ---

def test_valid_analysis_without_tracing_prints_json_and_warns(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_pipeline", lambda *args, **kwargs: RESULT)

    assert cli.main([ORIGINAL, AMENDMENT, "--sin-trazas"]) == cli.EXIT_OK

    out, err = capsys.readouterr()
    assert ContractChangeOutput.model_validate_json(out) == RESULT
    assert "--sin-trazas" in err


def test_missing_configuration_exits_2(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY")

    assert cli.main([ORIGINAL, AMENDMENT]) == cli.EXIT_INVALID_INPUT
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_invalid_image_exits_2_without_running_the_pipeline(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "run_pipeline", lambda *a, **k: pytest.fail("no debe ejecutarse"))

    assert cli.main([ORIGINAL, str(tmp_path / "no-existe.jpg"), "--sin-trazas"]) == cli.EXIT_INVALID_INPUT
    out, err = capsys.readouterr()
    assert out == "" and "InputValidationError" in err


@pytest.mark.parametrize(
    ("error", "exit_code"),
    [
        (IllegibleDocumentError("ilegible"), cli.EXIT_INVALID_INPUT),
        (ImageParsingError("vacía"), cli.EXIT_EXTERNAL_SERVICE),
        (ExternalServiceError("timeout"), cli.EXIT_EXTERNAL_SERVICE),
        (AgentError("schema"), cli.EXIT_INVALID_ANALYSIS),
        (RuntimeError("bug"), cli.EXIT_UNEXPECTED),
    ],
)
def test_pipeline_errors_map_to_exit_codes_and_print_no_json(monkeypatch, capsys, error, exit_code):
    def failing_pipeline(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, "run_pipeline", failing_pipeline)

    assert cli.main([ORIGINAL, AMENDMENT, "--sin-trazas"]) == exit_code
    out, err = capsys.readouterr()
    assert out == "" and str(error) in err


def test_unreachable_langfuse_exits_3_before_calling_openai(monkeypatch, capsys):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test-unreachable")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://127.0.0.1:9")
    monkeypatch.setattr(cli, "run_pipeline", lambda *a, **k: pytest.fail("no debe ejecutarse"))

    assert cli.main([ORIGINAL, AMENDMENT]) == cli.EXIT_EXTERNAL_SERVICE
    assert "Langfuse" in capsys.readouterr().err


def test_tracing_failure_keeps_the_json_and_exits_5(monkeypatch, capsys):
    langfuse = Langfuse(public_key="pk-lf-test-export-fails", secret_key="sk-lf-test",
                        host="http://127.0.0.1:9", timeout=1)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test-export-fails")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://127.0.0.1:9")
    monkeypatch.setattr(cli, "_connect_langfuse", lambda settings: langfuse)

    def traced_pipeline(*args, langfuse, on_trace_start, **kwargs):
        with langfuse.start_as_current_observation(name="contract-analysis"):
            on_trace_start(langfuse.get_current_trace_id())
            return RESULT

    monkeypatch.setattr(cli, "run_pipeline", traced_pipeline)

    assert cli.main([ORIGINAL, AMENDMENT]) == cli.EXIT_TRACING_FAILURE
    out, err = capsys.readouterr()
    assert ContractChangeOutput.model_validate_json(out) == RESULT
    assert "AVISO" in err and "Langfuse" in err
    for name in tracing.TRACING_LOGGERS:
        assert not any(isinstance(h, tracing.ErrorCounter) for h in logging.getLogger(name).handlers)


# --- Reintentos (una sola capa, en el SDK) ---

def test_each_client_makes_three_attempts_with_two_retries():
    retry_settings = load_settings({**ENV, "OPENAI_MAX_RETRIES": "2"}, tracing_enabled=False)
    attempts = {"vision": 0, "llm": 0}

    def refusing(kind):
        def handler(request):
            attempts[kind] += 1
            raise httpx2.ConnectError("conexión rechazada", request=request)
        return httpx2.Client(transport=httpx2.MockTransport(handler))

    vision = cli.build_vision_client(retry_settings, http_client=refusing("vision"))
    llm = cli.build_chat_model(retry_settings, http_client=refusing("llm"))

    with pytest.raises(ExternalServiceError):
        cli.parse_contract_image(ORIGINAL, client=vision, model="gpt-4o")
    with pytest.raises(ExternalServiceError):
        cli.ContextualizationAgent(llm).run("a", "b")

    assert attempts == {"vision": 3, "llm": 3}


# --- Salida inválida del modelo, de punta a punta ---

def use_fake_openai(monkeypatch, fake):
    build_vision, build_llm = cli.build_vision_client, cli.build_chat_model
    monkeypatch.setattr(cli, "build_vision_client", lambda s: build_vision(s, http_client=fake.client()))
    monkeypatch.setattr(cli, "build_chat_model", lambda s: build_llm(s, http_client=fake.client()))


@pytest.mark.parametrize(
    "extraction",
    [
        completion(json.dumps({"sections_changed": ["Cláusula 3"], "topics_touched": ["Precio"],
                               "summary_of_the_change": "No se detectaron cambios"})),
        completion('{"sections_changed": ["Cláusula 3"]', finish_reason="content_filter"),
        completion(None),
    ],
    ids=["contradictory", "content-filter", "empty"],
)
def test_unusable_extraction_exits_4_without_json(monkeypatch, capsys, extraction):
    use_fake_openai(monkeypatch, FakeOpenAI(extraction=extraction))

    assert cli.main([ORIGINAL, AMENDMENT, "--sin-trazas"]) == cli.EXIT_INVALID_ANALYSIS
    out, err = capsys.readouterr()
    assert out == "" and "AgentError" in err


# --- Fallas de instrumentación: nunca reemplazan al análisis ---

class BrokenLangfuse:
    """Langfuse que falla en las operaciones indicadas."""

    def __init__(self, *failures):
        self.failures = set(failures)

    def _maybe_fail(self, operation):
        if operation in self.failures:
            raise RuntimeError(f"langfuse falló en {operation}")

    def start_as_current_observation(self, **kwargs):
        self._maybe_fail("create")
        return nullcontext(BrokenObservation(self))

    def get_current_trace_id(self):
        self._maybe_fail("trace_id")
        return "a" * 32

    def flush(self):
        self._maybe_fail("flush")

    def get_trace_url(self, trace_id):
        return None


class BrokenObservation:
    def __init__(self, langfuse):
        self.langfuse = langfuse

    def update(self, **kwargs):
        self.langfuse._maybe_fail("update")


def run_with(langfuse, fake):
    return cli.run_pipeline(
        ORIGINAL, AMENDMENT, settings=settings(),
        vision_client=cli.build_vision_client(settings(), http_client=fake.client()),
        llm=cli.build_chat_model(settings(), http_client=fake.client()),
        langfuse=langfuse,
    )


@pytest.mark.parametrize("failures", [("create",), ("update", "trace_id")], ids=["create", "update"])
def test_instrumentation_failures_do_not_stop_a_valid_analysis(failures):
    with tracing.count_tracing_errors() as errors:
        assert run_with(BrokenLangfuse(*failures), FakeOpenAI()) == RESULT
    assert errors.count > 0


def test_instrumentation_failure_does_not_replace_the_analysis_error():
    fake = FakeOpenAI(context_map=CONTEXT_MAP.replace("| AMBOS |", "| AMBIGUA |"))

    with pytest.raises(AgentError, match="ambigua"):
        run_with(BrokenLangfuse("update"), fake)


def test_flush_failure_after_valid_analysis_keeps_json_and_exits_5(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_settings", lambda env, tracing_enabled: settings())
    monkeypatch.setattr(cli, "_connect_langfuse", lambda s: BrokenLangfuse("flush"))
    monkeypatch.setattr(cli, "run_pipeline", lambda *a, **k: RESULT)

    assert cli.main([ORIGINAL, AMENDMENT]) == cli.EXIT_TRACING_FAILURE
    out, err = capsys.readouterr()
    assert ContractChangeOutput.model_validate_json(out) == RESULT
    assert "AVISO" in err


def test_analysis_error_prevails_over_flush_failure_and_both_are_reported(monkeypatch, capsys):
    def failing_pipeline(*args, **kwargs):
        raise AgentError("schema inválido")

    monkeypatch.setattr(cli, "load_settings", lambda env, tracing_enabled: settings())
    monkeypatch.setattr(cli, "_connect_langfuse", lambda s: BrokenLangfuse("flush"))
    monkeypatch.setattr(cli, "run_pipeline", failing_pipeline)

    assert cli.main([ORIGINAL, AMENDMENT]) == cli.EXIT_INVALID_ANALYSIS
    out, err = capsys.readouterr()
    assert out == "" and "schema inválido" in err and "AVISO" in err


def test_langfuse_constructor_failure_exits_3(monkeypatch, capsys):
    def broken_constructor(**kwargs):
        raise ValueError("configuración de Langfuse inválida")

    monkeypatch.setattr(cli, "Langfuse", broken_constructor)

    assert cli._connect_langfuse(settings("pk-lf-test-constructor")) is None
    assert "Langfuse" in capsys.readouterr().err
