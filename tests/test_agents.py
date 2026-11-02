import json
import subprocess
import sys

import httpx2
import pytest
from langchain_openai import ChatOpenAI
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.agents.contextualization_agent import ContextualizationAgent, check_context_map
from src.agents.extraction_agent import ExtractionAgent
from src.errors import AgentError, ExternalServiceError
from src.models import ContractChangeOutput

CONTEXT_MAP = """## Tipo de adenda: REESCRITA

## Mapa de secciones
| ID original | ID en adenda | Propósito | Correspondencia |
|---|---|---|---|
| Cláusula 1 | Cláusula 1 | Servicio prestado | AMBOS |
| Cláusula 3 | Cláusula 3 | Precio del servicio | AMBOS |

## Observaciones
Ninguna"""

EXTRACTION = {
    "sections_changed": ["Cláusula 3"],
    "topics_touched": ["Precio"],
    "summary_of_the_change": '[MODIFICACIÓN] Cláusula 3 – Precio: la tarifa mensual pasa de "USD 1.200" a "USD 1.250".',
}


def completion(content, *, finish_reason="stop", refusal=None):
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content, "refusal": refusal},
            "finish_reason": finish_reason,
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }


class FakeOpenAI:
    """Transporte HTTP que responde como la API de OpenAI y guarda el cuerpo de cada petición."""

    def __init__(self, response):
        self.response = response
        self.requests = []

    def __call__(self, request):
        self.requests.append(json.loads(request.content))
        if isinstance(self.response, int):
            return httpx2.Response(self.response, json={"error": {"message": "falla simulada"}})
        return httpx2.Response(200, json=self.response)

    def chat_model(self):
        return ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            api_key="sk-fake",
            http_client=httpx2.Client(transport=httpx2.MockTransport(self)),
            max_retries=0,
        )


# --- ContextualizationAgent ---

def test_contextualization_returns_map_and_sends_both_texts():
    fake = FakeOpenAI(completion(CONTEXT_MAP))

    context_map = ContextualizationAgent(fake.chat_model()).run("TEXTO ORIGINAL", "TEXTO ADENDA")

    assert context_map == CONTEXT_MAP
    system, user = fake.requests[0]["messages"]
    assert "Analista Senior" in system["content"]
    assert "TEXTO ORIGINAL" in user["content"] and "TEXTO ADENDA" in user["content"]
    assert fake.requests[0]["temperature"] == 0


@pytest.mark.parametrize(
    ("context_map", "expected"),
    [
        ("", "vacío"),
        ("Las cláusulas se corresponden.", "formato esperado"),
        (CONTEXT_MAP.replace("REESCRITA", "PARCIAL"), "formato esperado"),
        (CONTEXT_MAP.replace("Precio del servicio | AMBOS", "Precio del servicio | AMBIGUA"), "Cláusula 3"),
        ("## Tipo de adenda: REESCRITA\n## Mapa de secciones\n## Observaciones\nNinguna", "tabla esperada"),
        (CONTEXT_MAP.split("| Cláusula 1")[0], "no tiene filas"),
        (CONTEXT_MAP.replace("| Cláusula 1 | Cláusula 1 | Servicio prestado | AMBOS |",
                             "| Cláusula 1 | Servicio prestado | AMBOS |"), "3 columnas"),
        (CONTEXT_MAP.replace("Precio del servicio | AMBOS", "Precio del servicio | INCIERTA"), "desconocida"),
    ],
    ids=["empty", "no-format", "unknown-type", "ambiguous", "no-table", "no-rows", "missing-column",
         "unknown-correspondence"],
)
def test_invalid_context_maps_stop_the_pipeline(context_map, expected):
    with pytest.raises(AgentError, match=expected):
        check_context_map(context_map)


def test_ambiguous_word_outside_the_table_is_not_a_correspondence():
    check_context_map(CONTEXT_MAP.replace("Ninguna", "No hay filas AMBIGUA."))


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [("length", "incompleto"), ("content_filter", "no terminó normalmente")],
)
def test_context_map_that_did_not_finish_normally_is_an_agent_error(finish_reason, expected):
    fake = FakeOpenAI(completion(CONTEXT_MAP, finish_reason=finish_reason))

    with pytest.raises(AgentError, match=expected):
        ContextualizationAgent(fake.chat_model()).run("a", "b")


def test_contextualization_api_failure_is_an_external_service_error():
    with pytest.raises(ExternalServiceError, match="contextualización"):
        ContextualizationAgent(FakeOpenAI(500).chat_model()).run("a", "b")


# --- ExtractionAgent ---

def test_extraction_returns_validated_output_from_strict_schema_request():
    fake = FakeOpenAI(completion(json.dumps(EXTRACTION, ensure_ascii=False)))

    output = ExtractionAgent(fake.chat_model()).run(CONTEXT_MAP, "ORIGINAL", "ADENDA")

    assert output == ContractChangeOutput(**EXTRACTION)
    request = fake.requests[0]
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True
    user = request["messages"][1]["content"]
    assert CONTEXT_MAP in user and "ORIGINAL" in user and "ADENDA" in user


def test_no_changes_output_is_valid():
    payload = {"sections_changed": [], "topics_touched": [], "summary_of_the_change": "No se detectaron cambios"}
    fake = FakeOpenAI(completion(json.dumps(payload)))

    output = ExtractionAgent(fake.chat_model()).run(CONTEXT_MAP, "a", "a")

    assert output.sections_changed == [] and output.summary_of_the_change == "No se detectaron cambios"


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (completion(None, refusal="No puedo ayudar con eso."), "se negó"),
        (completion('{"sections_changed": ["Cláusula 3"], "topics_', finish_reason="length"), "incompleta"),
        (completion(json.dumps({**EXTRACTION, "sections_changed": ["Cláusula 3", "Cláusula 3"]})),
         "repetidos en sections_changed: Cláusula 3"),
        (completion(json.dumps({"sections_changed": ["Cláusula 3"]})), "no cumple ContractChangeOutput"),
        (completion('{"sections_changed": ["Cláusula 3"]', finish_reason="content_filter"), "filtro de contenido"),
        (completion(None), "respuesta vacía"),
        (completion(json.dumps({**EXTRACTION, "summary_of_the_change": "No se detectaron cambios"})),
         "el resumen dice"),
    ],
    ids=["refusal", "truncated", "duplicates", "schema", "content-filter", "empty", "contradictory"],
)
def test_invalid_extractions_are_agent_errors_with_distinct_messages(response, expected):
    with pytest.raises(AgentError, match=expected):
        ExtractionAgent(FakeOpenAI(response).chat_model()).run(CONTEXT_MAP, "a", "b")


def test_extraction_api_failure_is_an_external_service_error():
    with pytest.raises(ExternalServiceError, match="extracción"):
        ExtractionAgent(FakeOpenAI(429).chat_model()).run(CONTEXT_MAP, "a", "b")


# --- Trazabilidad ---

def test_each_agent_call_is_one_generation_inside_its_span():
    exporter = InMemorySpanExporter()
    langfuse = Langfuse(public_key="pk-lf-test-agents", secret_key="sk-lf-test-agents",
                        host="http://127.0.0.1:9", span_exporter=exporter)
    callback = CallbackHandler(public_key="pk-lf-test-agents")
    context_llm = FakeOpenAI(completion(CONTEXT_MAP)).chat_model()
    extraction_llm = FakeOpenAI(completion(json.dumps(EXTRACTION, ensure_ascii=False))).chat_model()

    with langfuse.start_as_current_observation(name="contract-analysis"):
        with langfuse.start_as_current_observation(name="contextualization_agent"):
            ContextualizationAgent(context_llm).run("a", "b", callbacks=[callback])
        with langfuse.start_as_current_observation(name="extraction_agent"):
            ExtractionAgent(extraction_llm).run(CONTEXT_MAP, "a", "b", callbacks=[callback])
    langfuse.flush()

    spans = exporter.get_finished_spans()
    by_id = {span.context.span_id: span for span in spans}

    def stage_of(span):
        while span.parent and span.name not in ("contextualization_agent", "extraction_agent"):
            span = by_id[span.parent.span_id]
        return span.name

    assert len({span.context.trace_id for span in spans}) == 1
    generations = [s for s in spans if s.attributes.get("langfuse.observation.type") == "generation"]
    assert sorted(stage_of(g) for g in generations) == ["contextualization_agent", "extraction_agent"]
    assert all(json.loads(g.attributes["langfuse.observation.usage_details"])["total"] == 120 for g in generations)


def test_agents_do_not_import_the_langfuse_openai_wrapper():
    code = ("import sys, src.agents.contextualization_agent, src.agents.extraction_agent; "
            "print('langfuse.openai' in sys.modules)")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "False"
