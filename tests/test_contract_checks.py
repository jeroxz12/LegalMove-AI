"""Las comprobaciones de integración deben rechazar resultados incorrectos (sin llamadas reales)."""

import pytest

from src.models import ContractChangeOutput
from tests.contract_checks import PAIR_1, PAIR_3B, check_facts

PAIR_1_LINES = [
    '[MODIFICACIÓN] Cláusula 1 – Otorgamiento de Licencia: se elimina "intransferible" y se cambia '
    '"fines internos de la empresa" por "operaciones internas de negocio".',
    '[MODIFICACIÓN] Cláusula 2 – Plazo: la duración pasa de "12 meses" a "24 meses".',
    '[MODIFICACIÓN] Cláusula 3 – Pago: la tarifa anual pasa de "USD 12.000" a "USD 15.000".',
    '[MODIFICACIÓN] Cláusula 4 – Soporte: se añade "y chat" al soporte.',
    '[MODIFICACIÓN] Cláusula 5 – Terminación: el aviso pasa de "30 días" a "60 días".',
    "[ADICIÓN] Cláusula 7 – Protección de Datos: se añade el cumplimiento de normativas de protección de datos.",
]
PAIR_1_SECTIONS = ["Cláusula 1", "Cláusula 2", "Cláusula 3", "Cláusula 4", "Cláusula 5", "Cláusula 7"]


def output(lines, sections=PAIR_1_SECTIONS):
    return ContractChangeOutput(sections_changed=sections, topics_touched=["Licencia"],
                                summary_of_the_change="\n".join(lines))


def replace_line(index, new_line):
    lines = list(PAIR_1_LINES)
    lines[index] = new_line
    return lines


def test_real_pair_1_output_passes_with_the_documented_clause_1_tolerance():
    assert check_facts(output(PAIR_1_LINES), PAIR_1) == []


def test_clause_1_split_into_deletion_and_modification_also_passes():
    lines = ['[ELIMINACIÓN] Cláusula 1 – Licencia: se elimina "e intransferible".',
             '[MODIFICACIÓN] Cláusula 1 – Licencia: "fines internos" pasa a "operaciones internas de negocio".',
             *PAIR_1_LINES[1:]]
    assert check_facts(output(lines), PAIR_1) == []


@pytest.mark.parametrize(
    ("lines", "sections", "expected"),
    [
        (replace_line(2, '[MODIFICACIÓN] Cláusula 3 – Pago: de "USD 120.000" a "USD 150.000".'),
         PAIR_1_SECTIONS, "faltan los valores ['12000', '15000']"),
        (replace_line(1, '[MODIFICACIÓN] Cláusula 2 – Plazo: pasa a "24 meses".'),
         PAIR_1_SECTIONS, "faltan los valores ['12']"),
        (PAIR_1_LINES[:3] + PAIR_1_LINES[4:], PAIR_1_SECTIONS, "Cláusula 4: ninguna línea"),
        (replace_line(5, "[MODIFICACIÓN] Cláusula 7 – Protección de Datos: protección de datos."),
         PAIR_1_SECTIONS, "Cláusula 7: etiquetas ['MODIFICACIÓN']"),
        ([*PAIR_1_LINES, "[ADICIÓN] Cláusula 8 – Inventada: nueva cláusula."],
         [*PAIR_1_SECTIONS, "Cláusula 8"], "no esperada"),
        (replace_line(0, '[MODIFICACIÓN] Cláusula 1 – Licencia: pasa a "operaciones internas de negocio".'),
         PAIR_1_SECTIONS, "falta 'intransferible'"),
    ],
    ids=["amounts-x10", "missing-old-value", "omitted-support", "wrong-label", "invented-clause", "missing-deletion"],
)
def test_incorrect_pair_1_outputs_are_rejected(lines, sections, expected):
    problems = check_facts(output(lines, sections), PAIR_1)
    assert any(expected in problem for problem in problems), problems


def test_pair_3b_rejects_extra_clause_and_wrong_value():
    good = ContractChangeOutput(sections_changed=["Cláusula 3"], topics_touched=["Precio"],
                                summary_of_the_change='[MODIFICACIÓN] Cláusula 3 – Precio: de "USD 1.200" a "USD 1.250".')
    wrong = good.model_copy(update={"summary_of_the_change": "[MODIFICACIÓN] Cláusula 3 – Precio: de USD 1.200 a USD 12.500."})

    assert check_facts(good, PAIR_3B) == []
    assert check_facts(wrong, PAIR_3B) == ["Cláusula 3: faltan los valores ['1250']"]
