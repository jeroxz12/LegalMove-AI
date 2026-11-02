"""Modelo de salida validado del pipeline."""

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

NO_CHANGES_SUMMARY = "No se detectaron cambios"


class ContractChangeOutput(BaseModel):
    """Cambios que la adenda introduce sobre el contrato original."""

    model_config = ConfigDict(extra="forbid")

    sections_changed: List[str] = Field(
        description=(
            'Identificadores únicos con el formato "Cláusula N", en orden de aparición. '
            "Modificaciones y eliminaciones usan el número del contrato original; "
            "adiciones, el número de la adenda. Lista vacía si no hay cambios."
        )
    )
    topics_touched: List[str] = Field(
        description=(
            'Categorías legales o comerciales afectadas, por ejemplo "Precio", "Plazo", '
            '"Protección de datos". Lista vacía si no hay cambios.'
        )
    )
    summary_of_the_change: str = Field(
        description=(
            "Una línea por cambio con el formato "
            '"[ADICIÓN|ELIMINACIÓN|MODIFICACIÓN] Cláusula N – Título: descripción", '
            "citando los valores anteriores y nuevos. "
            f'Si no hay cambios: "{NO_CHANGES_SUMMARY}".'
        )
    )

    @field_validator("sections_changed")
    @classmethod
    def _sections_are_unique(cls, sections: List[str]) -> List[str]:
        repeated = sorted({section for section in sections if sections.count(section) > 1})
        if repeated:
            raise ValueError(f"identificadores repetidos en sections_changed: {', '.join(repeated)}")
        return sections
