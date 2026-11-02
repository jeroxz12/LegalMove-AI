"""Verificaciones de integración sin credenciales ni llamadas pagas (docs/architecture.md, 10.1).

OpenAI se simula con un transporte HTTP en memoria y Langfuse exporta los spans a memoria;
la sección 6 solo intenta conectarse a un puerto local cerrado.

Importa `langfuse.openai` a propósito, para reproducir la duplicación que llevó a descartarlo
(D2). El código del proyecto no debe importarlo.

Uso: .venv/bin/python spikes/check_1b_offline.py
"""

import base64
import json
import logging
import time
from pathlib import Path

import httpx2
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langfuse.openai import OpenAI
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel, Field

IMAGE = Path("data/test_contracts/documento_3__original.jpg")
SPIKE_PUBLIC_KEY = "pk-lf-spike"


class SpikeOutput(BaseModel):
    sections_changed: list[str] = Field(description="Secciones modificadas")
    topics_touched: list[str] = Field(description="Temas afectados")
    summary_of_the_change: str = Field(description="Resumen")


def completion(content: str | None, finish_reason: str = "stop", refusal: str | None = None) -> dict:
    return {
        "id": "chatcmpl-spike",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content, "refusal": refusal},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }


class FakeOpenAI:
    """Transporte que responde como la API de OpenAI y guarda cada petición."""

    def __init__(self, response: dict | None = None):
        self.requests: list[tuple[str, dict]] = []
        self.response = response

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append((request.url.path, body))
        if self.response is not None:
            return httpx2.Response(200, json=self.response)
        if "response_format" in body:
            payload = {"sections_changed": ["Cláusula 3"], "topics_touched": ["Precio"],
                       "summary_of_the_change": "[MODIFICACIÓN] Cláusula 3 – Precio."}
            return httpx2.Response(200, json=completion(json.dumps(payload, ensure_ascii=False)))
        return httpx2.Response(200, json=completion("texto simulado"))

    def client(self) -> httpx2.Client:
        return httpx2.Client(transport=httpx2.MockTransport(self))


def chat_model(fake: FakeOpenAI, max_retries: int = 0) -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o", api_key="sk-fake", http_client=fake.client(),
                      max_retries=max_retries, timeout=5)


def header(title: str) -> None:
    print(f"\n=== {title}")


def check_trace_structure(langfuse: Langfuse, exporter: InMemorySpanExporter, image_b64: str) -> None:
    header("1. Traza única, jerarquía y duplicados (wrapper + callback)")
    fake = FakeOpenAI()
    vision = OpenAI(api_key="sk-fake", http_client=fake.client(), max_retries=0)
    llm = chat_model(fake)
    callback = CallbackHandler(public_key=SPIKE_PUBLIC_KEY)
    prompt = ChatPromptTemplate.from_messages([("system", "Sos un analista."), ("user", "{texto}")])

    with langfuse.start_as_current_observation(name="contract-analysis"):
        with langfuse.start_as_current_observation(name="parse_original_contract"):
            vision.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": "Transcribí el contrato."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ]}],
            )
        with langfuse.start_as_current_observation(name="contextualization_agent"):
            (prompt | llm).invoke({"texto": "original y adenda"}, config={"callbacks": [callback]})
        with langfuse.start_as_current_observation(name="extraction_agent"):
            (prompt | llm.with_structured_output(SpikeOutput)).invoke(
                {"texto": "mapa y textos"}, config={"callbacks": [callback]})
    langfuse.flush()

    spans = exporter.get_finished_spans()
    by_id = {s.context.span_id: s for s in spans}
    print(f"spans exportados: {len(spans)} | trace_ids distintos: {len({s.context.trace_id for s in spans})}")
    for s in sorted(spans, key=lambda s: s.start_time):
        parent = by_id.get(s.parent.span_id).name if s.parent and s.parent.span_id in by_id else "-"
        kind = s.attributes.get("langfuse.observation.type", "?")
        print(f"  {s.name:<28} tipo={kind:<10} padre={parent}")

    header("2. ¿La imagen en base64 llega a algún span?")
    needle = image_b64[:200]
    leaks = [s.name for s in spans for v in s.attributes.values() if isinstance(v, str) and needle in v]
    print(f"spans que contienen el base64: {leaks or 'ninguno'}")
    media_refs = [s.name for s in spans for v in s.attributes.values()
                  if isinstance(v, str) and "@@@langfuseMedia" in v]
    print(f"spans con referencia a media subida aparte: {media_refs or 'ninguno'}")

    header("3. Petición de structured output que envía LangChain")
    path, body = next((p, b) for p, b in fake.requests if "response_format" in b)
    rf = body["response_format"]
    schema = rf.get("json_schema", {}).get("schema", {})
    print(f"endpoint: {path} | response_format.type: {rf.get('type')} | strict: {rf.get('json_schema', {}).get('strict')}")
    print(f"required: {schema.get('required')} | additionalProperties: {schema.get('additionalProperties')}")


def check_refusal_and_truncation() -> None:
    header("4. Rechazo y respuesta truncada en structured output")
    cases = {
        "rechazo": completion(None, refusal="No puedo ayudar con eso."),
        "truncada": completion('{"sections_changed": ["Cláusula 3"], "topics_', finish_reason="length"),
    }
    for label, response in cases.items():
        llm = chat_model(FakeOpenAI(response))
        for include_raw in (False, True):
            try:
                result = llm.with_structured_output(SpikeOutput, include_raw=include_raw).invoke("x")
                summary = {k: type(v).__name__ for k, v in result.items()} if isinstance(result, dict) else type(result).__name__
                print(f"  {label:<9} include_raw={include_raw!s:<5} -> devuelve {summary}")
                if isinstance(result, dict) and result.get("parsing_error"):
                    print(f"            parsing_error: {type(result['parsing_error']).__name__}: {str(result['parsing_error'])[:90]}")
            except Exception as exc:
                print(f"  {label:<9} include_raw={include_raw!s:<5} -> lanza {type(exc).__module__}.{type(exc).__name__}: {str(exc)[:90]}")

    vision = OpenAI(api_key="sk-fake", http_client=FakeOpenAI(cases["truncada"]).client(), max_retries=0)
    choice = vision.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": "x"}]).choices[0]
    print(f"  SDK directo, truncada -> finish_reason={choice.finish_reason!r} (no lanza excepción)")


def check_retries() -> None:
    header("5. Intentos reales ante un fallo de conexión (max_retries=2)")

    class Refused:
        attempts = 0

        def __call__(self, request):
            Refused.attempts += 1
            raise httpx2.ConnectError("conexión rechazada", request=request)

    for label in ("SDK de OpenAI", "ChatOpenAI"):
        Refused.attempts = 0
        client = httpx2.Client(transport=httpx2.MockTransport(Refused()))
        started = time.monotonic()
        try:
            if label == "SDK de OpenAI":
                OpenAI(api_key="sk-fake", http_client=client, max_retries=2).chat.completions.create(
                    model="gpt-4o", messages=[{"role": "user", "content": "x"}])
            else:
                ChatOpenAI(model="gpt-4o", api_key="sk-fake", http_client=client, max_retries=2).invoke("x")
        except Exception as exc:
            elapsed = time.monotonic() - started
            print(f"  {label:<14} intentos={Refused.attempts} espera={elapsed:.1f}s excepción={type(exc).__module__}.{type(exc).__name__}")


def check_langfuse_unreachable() -> None:
    header("6. Langfuse inaccesible: chequeo inicial y envío final")
    records: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    for name in ("langfuse", "opentelemetry"):
        logging.getLogger(name).addHandler(Collect(level=logging.WARNING))

    client = Langfuse(public_key="pk-lf-unreachable", secret_key="sk-lf-unreachable",
                      host="http://127.0.0.1:9", timeout=2)
    try:
        print(f"  auth_check() -> {client.auth_check()}")
    except Exception as exc:
        print(f"  auth_check() -> lanza {type(exc).__module__}.{type(exc).__name__}: {str(exc)[:90]}")

    with client.start_as_current_observation(name="span-sin-destino"):
        pass
    started = time.monotonic()
    try:
        result = client.flush()
        print(f"  flush() -> devuelve {result!r} en {time.monotonic() - started:.1f}s, sin excepción")
    except Exception as exc:
        print(f"  flush() -> lanza {type(exc).__name__}: {exc}")
    print(f"  registros de log WARNING/ERROR emitidos: {len(records)}")
    for r in records[:3]:
        print(f"    [{r.levelname}] {r.name}: {r.getMessage()[:110]}")


def main() -> None:
    image_b64 = base64.b64encode(IMAGE.read_bytes()).decode()
    exporter = InMemorySpanExporter()
    langfuse = Langfuse(public_key=SPIKE_PUBLIC_KEY, secret_key="sk-lf-spike",
                        host="http://127.0.0.1:9", span_exporter=exporter)
    check_trace_structure(langfuse, exporter, image_b64)
    check_refusal_and_truncation()
    check_retries()
    check_langfuse_unreachable()


if __name__ == "__main__":
    main()
