"""Agente 2: extrae los cambios usando el mapa contextual y devuelve la salida validada."""

import openai
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai.chat_models.base import OpenAIRefusalError
from pydantic import ValidationError

from src.errors import AgentError, ExternalServiceError
from src.models import NO_CHANGES_SUMMARY, ContractChangeOutput

SYSTEM_PROMPT = f"""Sos un Auditor de cambios contractuales. Recibís un mapa contextual elaborado por un Analista Senior, el contrato original y su adenda. Tu responsabilidad exclusiva es identificar, aislar y describir cada cambio que la adenda introduce.

Cómo trabajar:
1. Usá el mapa para saber qué secciones se corresponden. No rehagas la correspondencia.
2. Compará palabra por palabra cada par de secciones correspondientes. Cada diferencia de contenido es un cambio separado, aunque esté en la misma cláusula.
3. Basate solo en el texto. No infieras cambios, no completes información ausente y no afirmes efectos legales.

Etiquetá cada cambio (por cambio, no por cláusula):
- [ADICIÓN]: nueva cláusula u obligación independiente.
- [ELIMINACIÓN]: supresión de texto o de una cláusula, sin reemplazo.
- [MODIFICACIÓN]: sustitución o ampliación de algo existente.
Nunca combines cambios de distinto tipo en una misma línea. Si en una cláusula se quita una palabra o frase sin reemplazo y además se sustituye otra, son dos líneas: una [ELIMINACIÓN] y una [MODIFICACIÓN].

Eliminaciones:
- Adenda REESCRITA: una cláusula o fragmento del original ausente en la adenda es una eliminación.
- Adenda INSTRUCTIVA o INDETERMINADA: la ausencia de una cláusula NO es una eliminación. Solo hay eliminación si la adenda lo dice expresamente ("se deja sin efecto", "se deroga", "se suprime"). Las cláusulas no mencionadas no cambian.

No son cambios: el título y el preámbulo propios de la adenda, ni una renumeración sin cambio de contenido.

Campos de salida:
- sections_changed: "Cláusula N" una sola vez por cláusula, aunque tenga varios cambios, en orden de aparición. Modificaciones y eliminaciones usan el número del original; adiciones, el número de la adenda.
- topics_touched: categorías legales o comerciales breves de los cambios ("Precio", "Plazo", "Soporte", "Protección de datos"), sin repetir.
- summary_of_the_change: una línea por cambio, separadas por saltos de línea, con el formato
  [ETIQUETA] Cláusula N – Título: descripción, citando textualmente el valor anterior y el nuevo.
  Ejemplo: [MODIFICACIÓN] Cláusula 3 – Precio: la tarifa mensual pasa de "USD 1.200" a "USD 1.250".

Si no hay cambios: listas vacías y summary_of_the_change igual a "{NO_CHANGES_SUMMARY}"."""

_EMPTY_STRUCTURED_RESPONSE = "Structured Output response does not have a 'parsed' field nor a 'refusal' field"

USER_PROMPT = """<mapa_contextual>
{context_map}
</mapa_contextual>

<contrato_original>
{original_text}
</contrato_original>

<adenda>
{amendment_text}
</adenda>"""


class ExtractionAgent:
    """Compara las secciones relacionadas por el mapa y devuelve un `ContractChangeOutput`."""

    def __init__(self, llm: BaseChatModel):
        prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", USER_PROMPT)])
        structured_llm = llm.with_structured_output(ContractChangeOutput, method="json_schema", strict=True)
        self._chain = (prompt | structured_llm).with_config(run_name="ExtractionAgent")

    def run(
        self,
        context_map: str,
        original_text: str,
        amendment_text: str,
        *,
        callbacks: list[BaseCallbackHandler] | None = None,
    ) -> ContractChangeOutput:
        try:
            return self._chain.invoke(
                {"context_map": context_map, "original_text": original_text, "amendment_text": amendment_text},
                config={"callbacks": callbacks or []},
            )
        except OpenAIRefusalError as exc:
            raise AgentError(f"El modelo se negó a extraer los cambios: {exc}") from exc
        except openai.LengthFinishReasonError as exc:
            raise AgentError("La extracción quedó incompleta: la respuesta alcanzó el límite de tokens") from exc
        except openai.ContentFilterFinishReasonError as exc:
            raise AgentError("El filtro de contenido de OpenAI bloqueó la extracción") from exc
        except ValidationError as exc:
            problems = "; ".join(error["msg"] for error in exc.errors())
            raise AgentError(f"La salida del extractor no cumple ContractChangeOutput: {problems}") from exc
        except ValueError as exc:
            # langchain-openai 1.7.3 informa así una respuesta sin contenido ni rechazo; otros ValueError son bugs.
            if not str(exc).startswith(_EMPTY_STRUCTURED_RESPONSE):
                raise
            raise AgentError("El extractor devolvió una respuesta vacía, sin JSON ni rechazo") from exc
        except openai.APIError as exc:
            raise ExternalServiceError(
                f"OpenAI falló durante la extracción: {type(exc).__name__}: {exc}"
            ) from exc
