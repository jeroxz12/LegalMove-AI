"""CLI de LegalMove AI: compara un contrato y su adenda a partir de dos imágenes.

Uso: python -m src.main <original> <adenda> [--sin-trazas]
"""

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path

import openai
from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from src.agents.contextualization_agent import ContextualizationAgent
from src.agents.extraction_agent import ExtractionAgent
from src.config import Settings, load_settings
from src.errors import (
    AgentError,
    ConfigError,
    ExternalServiceError,
    IllegibleDocumentError,
    ImageParsingError,
    InputValidationError,
    LegalMoveError,
)
from src.image_parser import parse_contract_image, validate_image_path
from src.models import ContractChangeOutput
from src.tracing import (
    count_tracing_errors,
    current_trace_id,
    observe,
    report_failure,
    safe_flush,
    safe_update,
)

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_INVALID_INPUT = 2
EXIT_EXTERNAL_SERVICE = 3
EXIT_INVALID_ANALYSIS = 4
EXIT_TRACING_FAILURE = 5

_EXIT_CODES = {
    ConfigError: EXIT_INVALID_INPUT,
    InputValidationError: EXIT_INVALID_INPUT,
    IllegibleDocumentError: EXIT_INVALID_INPUT,
    ImageParsingError: EXIT_EXTERNAL_SERVICE,
    ExternalServiceError: EXIT_EXTERNAL_SERVICE,
    AgentError: EXIT_INVALID_ANALYSIS,
}


def run_pipeline(
    original_path: str,
    amendment_path: str,
    *,
    settings: Settings,
    vision_client: openai.OpenAI,
    llm: BaseChatModel,
    langfuse: Langfuse | None = None,
    on_trace_start: Callable[[str], None] | None = None,
) -> ContractChangeOutput:
    """Ejecuta las cuatro etapas dentro del span raíz `contract-analysis`.

    `on_trace_start` recibe el `trace_id` apenas se abre la traza, para poder informarlo aunque el análisis falle.
    """
    callbacks = _langchain_callbacks(langfuse, settings)
    files = {"original": Path(original_path).name, "amendment": Path(amendment_path).name}

    with observe(langfuse, "contract-analysis", input=files) as root:
        if root is not None and on_trace_start:
            trace_id = current_trace_id(langfuse)
            if trace_id:
                on_trace_start(trace_id)
        original_text = _parse(langfuse, "parse_original_contract", original_path, vision_client, settings)
        amendment_text = _parse(langfuse, "parse_amendment_contract", amendment_path, vision_client, settings)

        with observe(langfuse, "contextualization_agent") as span:
            context_map = ContextualizationAgent(llm).run(original_text, amendment_text, callbacks=callbacks)
            safe_update(span, output=context_map)

        with observe(langfuse, "extraction_agent") as span:
            result = ExtractionAgent(llm).run(context_map, original_text, amendment_text, callbacks=callbacks)
            safe_update(span, output=result.model_dump())

        safe_update(root, output=result.model_dump())
    return result


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    load_dotenv()
    tracing = not args.sin_trazas
    try:
        settings = load_settings(os.environ, tracing_enabled=tracing)
    except ConfigError as exc:
        _report(exc)
        return EXIT_INVALID_INPUT
    if not tracing:
        _warn("modo desarrollo --sin-trazas: esta ejecución no queda registrada en Langfuse")

    with count_tracing_errors() as tracing_errors:
        langfuse = _connect_langfuse(settings) if tracing else None
        if tracing and langfuse is None:
            return EXIT_EXTERNAL_SERVICE

        trace_ids: list[str] = []
        result = None
        try:
            validate_image_path(args.original)
            validate_image_path(args.amendment)
            result = run_pipeline(
                args.original,
                args.amendment,
                settings=settings,
                vision_client=build_vision_client(settings),
                llm=build_chat_model(settings),
                langfuse=langfuse,
                on_trace_start=trace_ids.append,
            )
            exit_code = EXIT_OK
        except LegalMoveError as exc:
            _report(exc)
            exit_code = _EXIT_CODES.get(type(exc), EXIT_UNEXPECTED)
        except Exception as exc:
            print(f"Error inesperado: {type(exc).__name__}: {exc}", file=sys.stderr)
            exit_code = EXIT_UNEXPECTED
        finally:
            if langfuse:
                safe_flush(langfuse)
                if trace_ids:
                    _print_trace_reference(langfuse, trace_ids[0])

    if result is not None:
        print(result.model_dump_json(indent=2))
    if tracing_errors.count:
        _warn(f"se detectaron {tracing_errors.count} error(es) al registrar la traza en Langfuse; "
              "la traza puede estar incompleta")
        if exit_code == EXIT_OK:
            exit_code = EXIT_TRACING_FAILURE
    return exit_code


def build_vision_client(settings: Settings, http_client=None) -> openai.OpenAI:
    return openai.OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
        http_client=http_client,
    )


def build_chat_model(settings: Settings, http_client=None) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
        http_client=http_client,
    )


def _connect_langfuse(settings: Settings) -> Langfuse | None:
    try:
        langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_host,
        )
        authenticated = langfuse.auth_check()
    except Exception as exc:
        print(f"Langfuse no respondió o rechazó las credenciales: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None
    if not authenticated:
        print("Langfuse rechazó las credenciales", file=sys.stderr)
        return None
    return langfuse


def _print_trace_reference(langfuse: Langfuse, trace_id: str) -> None:
    try:
        url = langfuse.get_trace_url(trace_id=trace_id)
    except Exception:
        url = None
    print(f"Traza: {url or trace_id}", file=sys.stderr)


def _parse(langfuse, span_name: str, image_path: str, client: openai.OpenAI, settings: Settings) -> str:
    with observe(langfuse, span_name, input={"file_name": Path(image_path).name}) as span:
        text = parse_contract_image(image_path, client=client, model=settings.openai_model, langfuse=langfuse)
        safe_update(span, output={"characters": len(text)})
    return text


def _langchain_callbacks(langfuse: Langfuse | None, settings: Settings) -> list[CallbackHandler] | None:
    if langfuse is None:
        return None
    try:
        return [CallbackHandler(public_key=settings.langfuse_public_key)]
    except Exception as exc:
        report_failure("no se pudo crear el callback de Langfuse", exc)
        return None


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.main",
        description="Compara un contrato original y su adenda (imágenes JPEG o PNG) y devuelve los cambios en JSON.",
    )
    parser.add_argument("original", help="imagen del contrato original")
    parser.add_argument("amendment", metavar="adenda", help="imagen de la adenda")
    parser.add_argument("--sin-trazas", action="store_true",
                        help="modo desarrollo: no registra la ejecución en Langfuse")
    return parser.parse_args(argv)


def _report(exc: LegalMoveError) -> None:
    print(f"{type(exc).__name__}: {exc}", file=sys.stderr)


def _warn(message: str) -> None:
    print(f"AVISO: {message}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
