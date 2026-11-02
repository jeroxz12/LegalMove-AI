"""Comprobaciones automáticas de los hechos esperados (data/test_contracts/README.md, sección 8 de la arquitectura).

Verifican secciones, etiquetas por cláusula, valores anteriores y nuevos como números completos y palabras clave.
La redacción del resumen se revisa a mano.
"""

import re
from dataclasses import dataclass, field

from src.models import ContractChangeOutput

_LABEL = re.compile(r"^\[(ADICIÓN|ELIMINACIÓN|MODIFICACIÓN)\]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


@dataclass(frozen=True)
class Fact:
    clause: int
    labels: frozenset[str]
    numbers: frozenset[str] = field(default_factory=frozenset)
    words: tuple[str, ...] = ()


# Cláusula 1: tolerancia documentada (sección 9). Se acepta que la eliminación y la modificación
# queden en una sola línea [MODIFICACIÓN], pero ambos fragmentos deben mencionarse.
PAIR_1 = (
    Fact(1, frozenset({"ELIMINACIÓN", "MODIFICACIÓN"}), words=("intransferible", "operaciones internas")),
    Fact(2, frozenset({"MODIFICACIÓN"}), numbers=frozenset({"12", "24"})),
    Fact(3, frozenset({"MODIFICACIÓN"}), numbers=frozenset({"12000", "15000"})),
    Fact(4, frozenset({"MODIFICACIÓN"}), words=("chat",)),
    Fact(5, frozenset({"MODIFICACIÓN"}), numbers=frozenset({"30", "60"})),
    Fact(7, frozenset({"ADICIÓN"}), words=("protección de datos",)),
)

PAIR_3B = (
    Fact(3, frozenset({"MODIFICACIÓN"}), numbers=frozenset({"1200", "1250"})),
)


def check_facts(output: ContractChangeOutput, facts: tuple[Fact, ...]) -> list[str]:
    """Devuelve la lista de diferencias con los hechos esperados; vacía si coincide."""
    problems = []
    expected_sections = [f"Cláusula {fact.clause}" for fact in facts]
    if sorted(output.sections_changed) != sorted(expected_sections):
        problems.append(f"sections_changed={output.sections_changed}, se esperaba {expected_sections}")

    lines = [line.strip() for line in output.summary_of_the_change.splitlines() if line.strip()]
    expected_clauses = {fact.clause for fact in facts}
    for line in lines:
        clause = _clause_of(line)
        if clause not in expected_clauses:
            problems.append(f"línea sobre una cláusula no esperada: {line[:80]!r}")

    for fact in facts:
        clause_lines = [line for line in lines if _clause_of(line) == fact.clause]
        if not clause_lines:
            problems.append(f"Cláusula {fact.clause}: ninguna línea en el resumen")
            continue
        labels = {_label_of(line) for line in clause_lines}
        if not labels <= fact.labels:
            problems.append(f"Cláusula {fact.clause}: etiquetas {sorted(labels)}, se esperaban {sorted(fact.labels)}")
        text = " ".join(clause_lines)
        missing_numbers = fact.numbers - _numbers_in(text)
        if missing_numbers:
            problems.append(f"Cláusula {fact.clause}: faltan los valores {sorted(missing_numbers)}")
        for word in fact.words:
            if word.lower() not in text.lower():
                problems.append(f"Cláusula {fact.clause}: falta {word!r}")
    return problems


def _clause_of(line: str) -> int | None:
    match = re.search(r"Cláusula (\d+)\b", line)
    return int(match.group(1)) if match else None


def _label_of(line: str) -> str | None:
    match = _LABEL.match(line)
    return match.group(1) if match else None


def _numbers_in(text: str) -> set[str]:
    return {re.sub(r"[.,]", "", number) for number in _NUMBER.findall(text)}
