import pytest
from pydantic import ValidationError

from src.models import ContractChangeOutput


def test_valid_output_is_accepted():
    output = ContractChangeOutput.model_validate({
        "sections_changed": ["Cláusula 3", "Cláusula 4"],
        "topics_touched": ["Precio", "Disponibilidad"],
        "summary_of_the_change": "[MODIFICACIÓN] Cláusula 3 – Precio: de USD 1.200 a USD 1.250.",
    })

    assert output.sections_changed == ["Cláusula 3", "Cláusula 4"]


def test_duplicate_sections_are_rejected_naming_the_identifier():
    with pytest.raises(ValidationError, match="repetidos en sections_changed: Cláusula 1"):
        ContractChangeOutput(
            sections_changed=["Cláusula 1", "Cláusula 2", "Cláusula 1"],
            topics_touched=["Licencia"],
            summary_of_the_change="...",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"sections_changed": [], "topics_touched": []},
        {"sections_changed": [], "topics_touched": [], "summary_of_the_change": "x", "risk": "alto"},
        {"sections_changed": "Cláusula 1", "topics_touched": [], "summary_of_the_change": "x"},
    ],
    ids=["missing-field", "extra-field", "wrong-type"],
)
def test_schema_violations_are_rejected(payload):
    with pytest.raises(ValidationError):
        ContractChangeOutput.model_validate(payload)


def test_no_changes_output_is_valid():
    output = ContractChangeOutput(sections_changed=[], topics_touched=[], summary_of_the_change="No se detectaron cambios")

    assert output.sections_changed == []


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"sections_changed": ["Cláusula 3"], "topics_touched": ["Precio"],
          "summary_of_the_change": "No se detectaron cambios"}, "dice"),
        ({"sections_changed": [], "topics_touched": [],
          "summary_of_the_change": "[MODIFICACIÓN] Cláusula 3 – Precio: de USD 1.200 a USD 1.250."}, "sin secciones"),
        ({"sections_changed": [], "topics_touched": ["Precio"],
          "summary_of_the_change": "No se detectaron cambios"}, "sin secciones"),
        ({"sections_changed": ["Cláusula 3"], "topics_touched": ["Precio"], "summary_of_the_change": "   "}, "vacío"),
        ({"sections_changed": ["Cláusula 3"], "topics_touched": [],
          "summary_of_the_change": "[MODIFICACIÓN] Cláusula 3 – Precio."}, "topics_touched está vacío"),
        ({"sections_changed": ["Cláusula 3"], "topics_touched": ["Precio"],
          "summary_of_the_change": "[MODIFICACIÓN] Cláusula 3 – Precio.\nNota: revisar."}, "sin etiqueta"),
    ],
    ids=["changes-but-no-changes-summary", "no-sections-but-change", "no-sections-but-topics",
         "blank-summary", "no-topics", "unlabeled-line"],
)
def test_contradictory_outputs_are_rejected(payload, expected):
    with pytest.raises(ValidationError, match=expected):
        ContractChangeOutput.model_validate(payload)


def test_json_schema_has_exactly_the_three_documented_fields():
    schema = ContractChangeOutput.model_json_schema()

    assert set(schema["properties"]) == {"sections_changed", "topics_touched", "summary_of_the_change"}
    assert all(field.get("description") for field in schema["properties"].values())
    assert schema["additionalProperties"] is False
