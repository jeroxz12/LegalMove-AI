"""Errores propios de LegalMove AI."""


class LegalMoveError(Exception):
    """Base de todos los errores que el pipeline reporta con un mensaje claro."""


class ConfigError(LegalMoveError):
    """La configuración del entorno falta o es inválida."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        details = "\n".join(f"- {problem}" for problem in problems)
        super().__init__(f"Configuración inválida:\n{details}")


class InputValidationError(LegalMoveError):
    """La imagen de entrada no existe, no se puede leer o no tiene un formato admitido."""


class ImageParsingError(LegalMoveError):
    """Vision no devolvió una transcripción utilizable (vacía, rechazada o truncada)."""


class IllegibleDocumentError(LegalMoveError):
    """La transcripción contiene fragmentos marcados como [ILEGIBLE]."""


class AgentError(LegalMoveError):
    """Un agente no produjo un resultado válido: mapa ambiguo o mal formado, rechazo, truncado o schema inválido."""


class ExternalServiceError(LegalMoveError):
    """Un servicio externo (OpenAI o Langfuse) falló o rechazó la petición."""
