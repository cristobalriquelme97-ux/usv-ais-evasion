# Considera el retorno del USV a su rumbo original después de una maniobra evasiva.

from __future__ import annotations

from dataclasses import dataclass

from usv_avoidance.motion_model import shortest_angle_difference_deg


@dataclass
class RouteManager:
    """
    Gestor simple de retorno a ruta.

    En esta primera versión no usa waypoints.
    Solo guarda el rumbo nominal original del USV y verifica
    si el USV ya volvió suficientemente cerca de ese rumbo.
    """

    original_course_deg: float
    recovery_tolerance_deg: float = 3.0

    def get_return_course(self) -> float:
        """
        Retorna el rumbo al cual debe volver el USV
        después de completar una maniobra evasiva.
        """
        return self.original_course_deg

    def is_route_recovered(self, current_course_deg: float) -> bool:
        """
        Determina si el USV ya recuperó su rumbo original.
        """
        error_deg = shortest_angle_difference_deg(
            target_deg=self.original_course_deg,
            current_deg=current_course_deg,
        )

        return abs(error_deg) <= self.recovery_tolerance_deg