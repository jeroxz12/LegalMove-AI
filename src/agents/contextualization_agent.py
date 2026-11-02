"""Agente 1: construye el mapa contextual que relaciona las secciones de ambos documentos."""

import re

import openai
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from src.errors import AgentError, ExternalServiceError

AMENDMENT_TYPES = ("INSTRUCTIVA", "REESCRITA", "INDETERMINADA")
AMBIGUOUS_MARKER = "AMBIGUA"

SYSTEM_PROMPT = """Sos un Analista Senior de contratos. Recibís la transcripción de un contrato original y la de su adenda. Tu única tarea es construir un mapa estructural comparado que otro analista usará para encontrar los cambios.

No describas cambios, no compares valores, no opines sobre efectos legales. Respondés "dónde mirar", no "qué cambió".

1. Clasificá la adenda:
   - REESCRITA: reproduce el contrato completo, con su texto actualizado.
   - INSTRUCTIVA: solo enumera modificaciones sobre cláusulas del original ("Se modifica la Cláusula 2...", "Se deja sin efecto la Cláusula 3...").
   - INDETERMINADA: no se puede decidir con seguridad.

2. Relacioná cada cláusula numerada del original con la de la adenda por contenido y título, no solo por número: una cláusula renumerada es la misma sección. Usá identificadores con el formato "Cláusula N".

3. Asigná una correspondencia a cada fila:
   - AMBOS: la sección aparece en los dos documentos, aunque su texto o su número difieran.
   - SOLO_ORIGINAL: aparece en el original y la adenda no la reproduce ni la menciona.
   - SOLO_ADENDA: sección nueva que solo aparece en la adenda.
   - REFERENCIADA: la adenda no la reproduce completa, pero la menciona expresamente (para modificarla, sustituirla o dejarla sin efecto).
   - AMBIGUA: no podés relacionarla con seguridad. Nunca inventes una correspondencia.

4. En "Propósito" describí en pocas palabras qué regula la sección (por ejemplo, "Precio del servicio"), sin mencionar valores ni diferencias.

5. El título y el preámbulo propios de la adenda ("La presente enmienda modifica...") no son secciones: no los incluyas en la tabla.

Respondé exactamente con este formato, sin texto antes ni después:

## Tipo de adenda: <INSTRUCTIVA, REESCRITA o INDETERMINADA>

## Mapa de secciones
| ID original | ID en adenda | Propósito | Correspondencia |
|---|---|---|---|
| Cláusula 1 | Cláusula 1 | ... | AMBOS |

## Observaciones
<renumeraciones, referencias expresas de la adenda o motivos de una correspondencia AMBIGUA; "Ninguna" si no hay>

Usá "—" en la columna del documento donde la sección no existe."""

USER_PROMPT = """<contrato_original>
{original_text}
</contrato_original>

<adenda>
{amendment_text}
</adenda>"""

_AMENDMENT_TYPE_LINE = re.compile(r"^## Tipo de adenda:\s*(\w+)\s*$", re.MULTILINE)


class ContextualizationAgent:
    """Relaciona las secciones del original y la adenda; no extrae cambios."""

    def __init__(self, llm: BaseChatModel):
        prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", USER_PROMPT)])
        self._chain = (prompt | llm).with_config(run_name="ContextualizationAgent")

    def run(
        self,
        original_text: str,
        amendment_text: str,
        *,
        callbacks: list[BaseCallbackHandler] | None = None,
    ) -> str:
        try:
            message = self._chain.invoke(
                {"original_text": original_text, "amendment_text": amendment_text},
                config={"callbacks": callbacks or []},
            )
        except openai.APIError as exc:
            raise ExternalServiceError(
                f"OpenAI falló durante la contextualización: {type(exc).__name__}: {exc}"
            ) from exc

        if message.response_metadata.get("finish_reason") == "length":
            raise AgentError("El mapa contextual quedó incompleto: la respuesta alcanzó el límite de tokens")
        context_map = message.text.strip()
        check_context_map(context_map)
        return context_map


def check_context_map(context_map: str) -> None:
    if not context_map:
        raise AgentError("El agente de contextualización devolvió un mapa vacío")

    match = _AMENDMENT_TYPE_LINE.search(context_map)
    if not match or match.group(1) not in AMENDMENT_TYPES or "## Mapa de secciones" not in context_map:
        raise AgentError("El mapa contextual no respeta el formato esperado (tipo de adenda y mapa de secciones)")

    ambiguous_rows = [
        line.strip()
        for line in context_map.splitlines()
        if line.lstrip().startswith("|") and AMBIGUOUS_MARKER in _cells(line)
    ]
    if ambiguous_rows:
        rows = "\n".join(f"  {row}" for row in ambiguous_rows)
        raise AgentError(f"Correspondencia ambigua entre secciones; no se extraen cambios:\n{rows}")


def _cells(table_row: str) -> list[str]:
    return [cell.strip() for cell in table_row.strip().strip("|").split("|")]
