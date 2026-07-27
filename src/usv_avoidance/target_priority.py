from __future__ import annotations

from math import inf
from typing import Any, Mapping, Sequence


Assessment = Mapping[str, Any]


def assessment_priority_key(
    assessment: Assessment,
) -> tuple[float, float, float, float]:
    """
    Construye la clave utilizada para ordenar un contacto.

    Un valor menor representa una prioridad mayor.

    Orden actual:

    1. Contactos con riesgo.
    2. Contactos respecto de los cuales el USV debe maniobrar.
    3. Menor TCPA futuro.
    4. Menor CPA.
    """

    cpa_result = assessment["cpa_result"]
    classification = assessment["classification"]

    risk = bool(
        classification.get(
            "risk",
            cpa_result.get("risk", False),
        )
    )

    should_maneuver = bool(
        classification.get("should_maneuver", False)
    )

    cpa_m = float(cpa_result.get("cpa_m", inf))
    tcpa_s = float(cpa_result.get("tcpa_s", inf))

    # Un TCPA negativo significa que el punto de máxima
    # aproximación ya ocurrió.
    tcpa_priority = tcpa_s if tcpa_s >= 0.0 else inf

    risk_priority = 0.0 if risk else 1.0
    maneuver_priority = 0.0 if should_maneuver else 1.0

    return (
        risk_priority,
        maneuver_priority,
        tcpa_priority,
        cpa_m,
    )


def rank_assessments(
    assessments: Sequence[Assessment],
) -> list[Assessment]:
    """
    Retorna todos los contactos ordenados desde el más crítico
    hasta el menos crítico.
    """

    return sorted(
        assessments,
        key=assessment_priority_key,
    )


def select_most_critical_assessment(
    assessments: Sequence[Assessment],
) -> Assessment | None:
    """
    Selecciona el primer contacto de la lista priorizada.
    """

    ranked_assessments = rank_assessments(assessments)

    if not ranked_assessments:
        return None

    return ranked_assessments[0]