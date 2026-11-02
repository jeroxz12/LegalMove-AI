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


def test_json_schema_has_exactly_the_three_documented_fields():
    schema = ContractChangeOutput.model_json_schema()

    assert set(schema["properties"]) == {"sections_changed", "topics_touched", "summary_of_the_change"}
    assert all(field.get("description") for field in schema["properties"].values())
    assert schema["additionalProperties"] is False
