"""Pruebas de integración reales (pagas). Se ejecutan solo con: pytest -m integration

Comprueban los hechos esperados de data/test_contracts/README.md con criterios sencillos
(sección 8 de docs/architecture.md); la redacción del resumen se revisa a mano.
"""

import re
import subprocess
import sys

import pytest

from src.models import ContractChangeOutput

pytestmark = pytest.mark.integration

LABELS = ("ADICIÓN", "ELIMINACIÓN", "MODIFICACIÓN")


def run_cli(pair: str) -> ContractChangeOutput:
    result = subprocess.run(
        [sys.executable, "-m", "src.main",
         f"data/test_contracts/{pair}__original.jpg", f"data/test_contracts/{pair}__enmienda.jpg"],
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert "Traza: " in result.stderr
    return ContractChangeOutput.model_validate_json(result.stdout)


def digits(text: str) -> str:
    return re.sub(r"[.,\s]", "", text)


def labels_in(summary: str) -> set[str]:
    return {label for label in LABELS if f"[{label}]" in summary}


def test_pair_3b_simple_price_change():
    output = run_cli("documento_3b")

    assert output.sections_changed == ["Cláusula 3"]
    assert labels_in(output.summary_of_the_change) == {"MODIFICACIÓN"}
    assert "1200" in digits(output.summary_of_the_change) and "1250" in digits(output.summary_of_the_change)


def test_pair_1_complex_changes():
    output = run_cli("documento_1")

    assert set(output.sections_changed) == {"Cláusula 1", "Cláusula 2", "Cláusula 3", "Cláusula 4",
                                             "Cláusula 5", "Cláusula 7"}
    summary = digits(output.summary_of_the_change)
    for value in ("12000", "15000", "24meses", "60días"):
        assert value in summary
    assert "ADICIÓN" in labels_in(output.summary_of_the_change)
