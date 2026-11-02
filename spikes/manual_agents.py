"""Prueba manual real de las etapas 3 y 4: parsing, ambos agentes y salida validada, en una traza.

Requiere `.env` con claves reales y hace llamadas pagas: Vision por cada imagen y una llamada por agente.
Los archivos `.md` se usan como texto ya transcrito, sin pasar por Vision (caso instructivo).

Uso (desde la raíz del repo):
  .venv/bin/python -m spikes.manual_agents data/test_contracts/documento_1__original.jpg data/test_contracts/documento_1__enmienda.jpg
  .venv/bin/python -m spikes.manual_agents data/test_contracts/instructivo__original.md data/test_contracts/instructivo__enmienda.md
"""

import os
import sys
from pathlib import Path

import openai
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from src.agents.contextualization_agent import ContextualizationAgent
from src.agents.extraction_agent import ExtractionAgent
from src.config import load_settings
from src.errors import LegalMoveError
from src.image_parser import parse_contract_image


def main(original_path: str, amendment_path: str) -> int:
    load_dotenv(".env")
    settings = load_settings(os.environ)
    langfuse = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_host,
    )
    if not langfuse.auth_check():
        return 3

    vision_client = openai.OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    callback = CallbackHandler(public_key=settings.langfuse_public_key)

    def read_document(span_name: str, path: str) -> str:
        with langfuse.start_as_current_observation(name=span_name, input={"file_name": Path(path).name}) as span:
            if path.endswith(".md"):
                text = Path(path).read_text(encoding="utf-8")
            else:
                text = parse_contract_image(path, client=vision_client, model=settings.openai_model,
                                            langfuse=langfuse)
            span.update(output={"characters": len(text)})
            return text

    trace_id = None
    try:
        with langfuse.start_as_current_observation(
            name="contract-analysis",
            input={"original": Path(original_path).name, "amendment": Path(amendment_path).name},
        ) as root:
            trace_id = langfuse.get_current_trace_id()
            original_text = read_document("parse_original_contract", original_path)
            amendment_text = read_document("parse_amendment_contract", amendment_path)

            with langfuse.start_as_current_observation(name="contextualization_agent") as span:
                context_map = ContextualizationAgent(llm).run(original_text, amendment_text, callbacks=[callback])
                span.update(output=context_map)
            print(context_map, file=sys.stderr)

            with langfuse.start_as_current_observation(name="extraction_agent") as span:
                result = ExtractionAgent(llm).run(context_map, original_text, amendment_text, callbacks=[callback])
                span.update(output=result.model_dump())
            root.update(output=result.model_dump())

        print(result.model_dump_json(indent=2))
        return 0
    except LegalMoveError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 4
    finally:
        langfuse.flush()
        if trace_id:
            print(f"URL: {langfuse.get_trace_url(trace_id=trace_id)}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
