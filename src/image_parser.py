"""Validación de imágenes de contratos y transcripción con GPT-4o Vision."""

import base64
from contextlib import nullcontext
from pathlib import Path

import openai
from langfuse import Langfuse

from src.errors import (
    ExternalServiceError,
    IllegibleDocumentError,
    ImageParsingError,
    InputValidationError,
    LegalMoveError,
)

ILLEGIBLE_MARKER = "[ILEGIBLE]"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_OUTPUT_TOKENS = 4096

_FORMATS = {
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
}

VISION_SYSTEM_PROMPT = f"""Sos un transcriptor de documentos legales. Tu única tarea es transcribir fielmente el texto de la imagen de un contrato.

Reglas:
1. Transcribí todo el texto visible, en el idioma original y en el mismo orden.
2. Conservá exactamente números, montos, monedas, porcentajes, fechas, nombres propios y la numeración de las cláusulas. No normalices formatos: por ejemplo, "USD 12.000" se mantiene como "USD 12.000".
3. Usá Markdown para la jerarquía: "#" para el título del documento y "##" para cada cláusula o sección, con su número y título tal como aparecen. El contenido va en párrafos normales.
4. Si un fragmento no se puede leer con certeza, escribí {ILLEGIBLE_MARKER} en su lugar. Nunca completes ni adivines texto.
5. No resumas, no interpretes, no corrijas el documento y no agregues comentarios.
6. Si la imagen no contiene texto legible, respondé únicamente {ILLEGIBLE_MARKER}.

Respondé solo con la transcripción."""

VISION_USER_PROMPT = "Transcribí el contrato de esta imagen."


def validate_image_path(image_path: str | Path, *, max_bytes: int = MAX_IMAGE_BYTES) -> Path:
    path = Path(image_path)
    if not path.is_file():
        raise InputValidationError(f"No existe el archivo de imagen: {path}")

    image_format = _FORMATS.get(path.suffix.lower())
    if image_format is None:
        raise InputValidationError(f"{path.name}: formato no admitido; se aceptan JPEG y PNG")

    size = path.stat().st_size
    if size == 0:
        raise InputValidationError(f"{path.name}: el archivo está vacío")
    if size > max_bytes:
        raise InputValidationError(f"{path.name}: pesa {size} bytes y el máximo es {max_bytes}")

    mime_type, signature = image_format
    with path.open("rb") as file:
        header = file.read(len(signature))
    if header != signature:
        raise InputValidationError(f"{path.name}: el contenido no corresponde a una imagen {mime_type}")
    return path


def encode_image_to_base64(image_path: Path) -> tuple[str, str]:
    mime_type, _ = _FORMATS[image_path.suffix.lower()]
    try:
        data = image_path.read_bytes()
    except OSError as exc:
        raise InputValidationError(f"{image_path.name}: no se pudo leer el archivo ({exc})") from exc
    return base64.b64encode(data).decode("ascii"), mime_type


def parse_contract_image(
    image_path: str | Path,
    *,
    client: openai.OpenAI,
    model: str,
    langfuse: Langfuse | None = None,
) -> str:
    """Transcribe la imagen de un contrato a Markdown.

    Con `langfuse`, registra una generación dentro del span activo. De la imagen solo
    se registran nombre, tamaño y tipo MIME: el base64 nunca llega a Langfuse.
    """
    path = validate_image_path(image_path)
    image_b64, mime_type = encode_image_to_base64(path)
    image_info = {"file_name": path.name, "size_bytes": path.stat().st_size, "mime_type": mime_type}

    observation = (
        langfuse.start_as_current_observation(
            name="vision-transcription",
            as_type="generation",
            model=model,
            input={"system": VISION_SYSTEM_PROMPT, "user": VISION_USER_PROMPT, "image": image_info},
            model_parameters={"temperature": 0, "max_completion_tokens": MAX_OUTPUT_TOKENS, "detail": "high"},
        )
        if langfuse
        else nullcontext()
    )

    with observation as generation:
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                max_completion_tokens=MAX_OUTPUT_TOKENS,
                messages=[
                    {"role": "system", "content": VISION_SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": VISION_USER_PROMPT},
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime_type};base64,{image_b64}",
                            "detail": "high",
                        }},
                    ]},
                ],
            )
        except openai.APIError as exc:
            error = ExternalServiceError(f"OpenAI no pudo transcribir {path.name}: {type(exc).__name__}: {exc}")
            _record_error(generation, error)
            raise error from exc

        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        if generation:
            generation.update(
                output=text,
                usage_details=_usage_details(response.usage),
                metadata={"finish_reason": choice.finish_reason},
            )

        try:
            _check_transcription(path.name, text, choice)
        except LegalMoveError as error:
            _record_error(generation, error)
            raise

    return text


def _check_transcription(file_name: str, text: str, choice) -> None:
    if choice.message.refusal:
        raise ImageParsingError(f"El modelo se negó a transcribir {file_name}: {choice.message.refusal}")
    if choice.finish_reason == "length":
        raise ImageParsingError(
            f"La transcripción de {file_name} quedó incompleta: alcanzó el límite de {MAX_OUTPUT_TOKENS} tokens"
        )
    if not text:
        raise ImageParsingError(f"Vision devolvió una transcripción vacía para {file_name}")
    if ILLEGIBLE_MARKER in text:
        count = text.count(ILLEGIBLE_MARKER)
        raise IllegibleDocumentError(
            f"{file_name} tiene {count} fragmento(s) marcados como {ILLEGIBLE_MARKER}; "
            "no se compara un documento incompleto"
        )


def _usage_details(usage) -> dict[str, int] | None:
    if usage is None:
        return None
    return {"input": usage.prompt_tokens, "output": usage.completion_tokens, "total": usage.total_tokens}


def _record_error(generation, error: LegalMoveError) -> None:
    if generation:
        generation.update(level="ERROR", status_message=str(error))
