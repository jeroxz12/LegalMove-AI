"""Modelo de salida validado del pipeline."""

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NO_CHANGES_SUMMARY = "No se detectaron cambios"
LABELS = ("[ADICIÓN]", "[ELIMINACIÓN]", "[MODIFICACIÓN]")


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

    @model_validator(mode="after")
    def _fields_are_consistent(self) -> "ContractChangeOutput":
        summary = self.summary_of_the_change.strip()
        if not summary:
            raise ValueError("summary_of_the_change está vacío")

        if not self.sections_changed:
            if self.topics_touched or summary != NO_CHANGES_SUMMARY:
                raise ValueError(
                    f'sin secciones modificadas, topics_touched debe estar vacío y el resumen ser "{NO_CHANGES_SUMMARY}"'
                )
            return self

        if summary == NO_CHANGES_SUMMARY:
            raise ValueError(f'hay secciones modificadas pero el resumen dice "{NO_CHANGES_SUMMARY}"')
        if not self.topics_touched:
            raise ValueError("hay secciones modificadas pero topics_touched está vacío")
        unlabeled = [line for line in summary.splitlines() if line.strip() and not line.lstrip().startswith(LABELS)]
        if unlabeled:
            raise ValueError(f"línea del resumen sin etiqueta [ADICIÓN|ELIMINACIÓN|MODIFICACIÓN]: {unlabeled[0][:80]!r}")
        return self
