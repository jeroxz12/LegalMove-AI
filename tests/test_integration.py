"""Pruebas de integración reales (pagas). Se ejecutan solo con: pytest -m integration

Las comprobaciones de hechos están en tests/contract_checks.py y se prueban sin costo en test_contract_checks.py.
"""

import subprocess
import sys

import pytest

from src.models import ContractChangeOutput
from tests.contract_checks import PAIR_1, PAIR_3B, check_facts

pytestmark = pytest.mark.integration


def run_cli(pair: str, environ: dict[str, str]) -> ContractChangeOutput:
    result = subprocess.run(
        [sys.executable, "-m", "src.main",
         f"data/test_contracts/{pair}__original.jpg", f"data/test_contracts/{pair}__enmienda.jpg"],
        capture_output=True, text=True, timeout=300, env=environ,
    )
    assert result.returncode == 0, result.stderr
    assert "Traza: " in result.stderr
    return ContractChangeOutput.model_validate_json(result.stdout)


def test_pair_3b_simple_price_change(original_environ):
    assert check_facts(run_cli("documento_3b", original_environ), PAIR_3B) == []


def test_pair_1_complex_changes(original_environ):
    assert check_facts(run_cli("documento_1", original_environ), PAIR_1) == []
