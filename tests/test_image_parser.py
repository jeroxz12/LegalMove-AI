import base64
import json
import subprocess
import sys
from pathlib import Path

import httpx2
import openai
import pytest
from langfuse import Langfuse
from openai.types.chat import ChatCompletion
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.errors import ExternalServiceError, IllegibleDocumentError, ImageParsingError, InputValidationError
from src.image_parser import (
    MAX_OUTPUT_TOKENS,
    encode_image_to_base64,
    parse_contract_image,
    validate_image_path,
)

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"contenido-jpeg" * 10
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"contenido-png" * 10
REAL_IMAGE = Path("data/test_contracts/documento_3__original.jpg")


def chat_completion(content, *, finish_reason="stop", refusal=None):
    return ChatCompletion.model_validate({
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content, "refusal": refusal},
            "finish_reason": finish_reason,
        }],
        "usage": {"prompt_tokens": 800, "completion_tokens": 150, "total_tokens": 950},
    })


class FakeOpenAI:
    """Expone `chat.completions.create` como el cliente real y guarda los argumentos recibidos."""

    def __init__(self, result):
        self.result = result
        self.calls = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def jpeg_file(tmp_path):
    path = tmp_path / "contrato.jpg"
    path.write_bytes(JPEG_BYTES)
    return path


@pytest.fixture(scope="module")
def tracing():
    exporter = InMemorySpanExporter()
    langfuse = Langfuse(
        public_key="pk-lf-test-parser",
        secret_key="sk-lf-test-parser",
        host="http://127.0.0.1:9",
        span_exporter=exporter,
    )
    return langfuse, exporter


def exported_spans(tracing):
    langfuse, exporter = tracing
    langfuse.flush()
    spans = exporter.get_finished_spans()
    exporter.clear()
    return spans


# --- Validación de la imagen ---

def test_valid_jpeg_and_png_are_accepted(tmp_path):
    for name, data in (("a.jpg", JPEG_BYTES), ("b.jpeg", JPEG_BYTES), ("c.PNG", PNG_BYTES)):
        path = tmp_path / name
        path.write_bytes(data)
        assert validate_image_path(str(path)) == path


@pytest.mark.parametrize(
    ("name", "data", "expected"),
    [
        ("contrato.gif", JPEG_BYTES, "formato no admitido"),
        ("vacio.jpg", b"", "vacío"),
        ("falso.png", JPEG_BYTES, "no corresponde a una imagen image/png"),
        ("texto.jpg", b"esto no es una imagen", "no corresponde a una imagen image/jpeg"),
    ],
)
def test_invalid_files_are_rejected(tmp_path, name, data, expected):
    path = tmp_path / name
    path.write_bytes(data)

    with pytest.raises(InputValidationError, match=expected):
        validate_image_path(path)


def test_missing_file_and_directory_are_rejected(tmp_path):
    for path in (tmp_path / "no-existe.jpg", tmp_path):
        with pytest.raises(InputValidationError, match="No existe"):
            validate_image_path(path)


def test_file_over_size_limit_is_rejected(jpeg_file):
    with pytest.raises(InputValidationError, match="máximo"):
        validate_image_path(jpeg_file, max_bytes=10)


@pytest.mark.parametrize("method", ["open", "stat"])
def test_unreadable_file_is_an_input_error(monkeypatch, jpeg_file, method):
    original = getattr(Path, method)

    def failing(self, *args, **kwargs):
        if self == jpeg_file:
            raise PermissionError("permiso denegado")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, method, failing)

    with pytest.raises(InputValidationError, match="no se pudo leer"):
        validate_image_path(jpeg_file)


def test_encode_returns_base64_and_mime(jpeg_file):
    image_b64, mime_type = encode_image_to_base64(jpeg_file)

    assert mime_type == "image/jpeg"
    assert base64.b64decode(image_b64) == JPEG_BYTES


# --- Llamada a Vision (cliente simulado) ---

def test_successful_transcription_sends_image_and_returns_text(jpeg_file):
    client = FakeOpenAI(chat_completion("# CONTRATO\n\n## 1. Objeto\nTexto."))

    text = parse_contract_image(jpeg_file, client=client, model="gpt-4o")

    assert text == "# CONTRATO\n\n## 1. Objeto\nTexto."
    call = client.calls[0]
    assert call["model"] == "gpt-4o"
    assert call["temperature"] == 0
    assert call["max_completion_tokens"] == MAX_OUTPUT_TOKENS
    image_part = call["messages"][1]["content"][1]["image_url"]
    assert image_part["url"] == f"data:image/jpeg;base64,{base64.b64encode(JPEG_BYTES).decode()}"
    assert image_part["detail"] == "high"


def test_invalid_image_never_calls_the_api(tmp_path):
    client = FakeOpenAI(chat_completion("texto"))

    with pytest.raises(InputValidationError):
        parse_contract_image(tmp_path / "no-existe.png", client=client, model="gpt-4o")
    assert client.calls == []


@pytest.mark.parametrize(
    ("response", "error", "expected"),
    [
        (chat_completion(None, refusal="No puedo ayudar."), ImageParsingError, "se negó"),
        (chat_completion("# CONTRATO\n## 1.", finish_reason="length"), ImageParsingError, "incompleta"),
        (chat_completion("# CONTRATO\n## 1.", finish_reason="content_filter"), ImageParsingError,
         "no terminó normalmente"),
        (chat_completion("   "), ImageParsingError, "vacía"),
        (chat_completion("## 3. Precio\nUSD [ILEGIBLE] mensuales"), IllegibleDocumentError, "1 fragmento"),
        (chat_completion("[ILEGIBLE]"), IllegibleDocumentError, "ILEGIBLE"),
    ],
)
def test_unusable_transcriptions_raise_clear_errors(jpeg_file, response, error, expected):
    with pytest.raises(error, match=expected):
        parse_contract_image(jpeg_file, client=FakeOpenAI(response), model="gpt-4o")


@pytest.mark.parametrize(
    "api_error",
    [
        openai.APITimeoutError(request=httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")),
        openai.APIConnectionError(request=httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")),
    ],
)
def test_api_errors_become_external_service_errors(jpeg_file, api_error):
    with pytest.raises(ExternalServiceError, match="contrato.jpg"):
        parse_contract_image(jpeg_file, client=FakeOpenAI(api_error), model="gpt-4o")


# --- Instrumentación con Langfuse (exportador en memoria) ---

def test_generation_records_metadata_but_never_the_image(tracing):
    langfuse, _ = tracing
    image_b64 = base64.b64encode(REAL_IMAGE.read_bytes()).decode()

    with langfuse.start_as_current_observation(name="parse_original_contract"):
        parse_contract_image(REAL_IMAGE, client=FakeOpenAI(chat_completion("# CONTRATO")), model="gpt-4o",
                             langfuse=langfuse)

    spans = exported_spans(tracing)
    generations = [s for s in spans if s.attributes.get("langfuse.observation.type") == "generation"]
    assert len(generations) == 1
    generation = generations[0]
    assert generation.parent.span_id == next(s for s in spans if s.name == "parse_original_contract").context.span_id

    recorded_input = json.loads(generation.attributes["langfuse.observation.input"])
    assert recorded_input["image"] == {
        "file_name": REAL_IMAGE.name,
        "size_bytes": REAL_IMAGE.stat().st_size,
        "mime_type": "image/jpeg",
    }
    assert generation.attributes["langfuse.observation.output"] == "# CONTRATO"
    assert json.loads(generation.attributes["langfuse.observation.usage_details"]) == {
        "input": 800, "output": 150, "total": 950,
    }
    for span in spans:
        for value in span.attributes.values():
            if isinstance(value, str):
                assert image_b64[:200] not in value
                assert "@@@langfuseMedia" not in value


def test_failed_transcription_is_recorded_as_error(tracing, jpeg_file):
    langfuse, _ = tracing

    with pytest.raises(IllegibleDocumentError):
        parse_contract_image(jpeg_file, client=FakeOpenAI(chat_completion("[ILEGIBLE]")), model="gpt-4o",
                             langfuse=langfuse)

    generation = next(s for s in exported_spans(tracing) if s.name == "vision-transcription")
    assert generation.attributes["langfuse.observation.level"] == "ERROR"
    assert "ILEGIBLE" in generation.attributes["langfuse.observation.status_message"]


def test_project_code_does_not_import_the_langfuse_openai_wrapper():
    result = subprocess.run(
        [sys.executable, "-c", "import sys, src.image_parser; print('langfuse.openai' in sys.modules)"],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "False"
