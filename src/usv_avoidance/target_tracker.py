from __future__ import annotations

from typing import Any, Mapping


class TargetTracker:
    """
    Traqueador simple de blancos AIS.

    Su función es mantener actualizado el último estado conocido
    de cada blanco AIS usando su MMSI como identificador único.

    Este módulo no calcula CPA/TCPA.
    Este módulo no clasifica encuentros.
    Este módulo solo guarda y actualiza blancos.
    """

    def __init__(self, max_age_s: float = 60.0):
        """
        Parámetros:
        - max_age_s: tiempo máximo permitido sin actualización para
          considerar que un blanco sigue activo.
        """

        self.max_age_s = max_age_s
        self._targets: dict[int, dict[str, Any]] = {}

    def update_from_ais(
        self,
        ais_data: Mapping[str, Any],
        received_at_s: float,
    ) -> dict[str, Any] | None:
        """
        Actualiza el estado de un blanco usando un mensaje AIS decodificado.

        Parámetros:
        - ais_data: diccionario generado por ais_adapter.py.
        - received_at_s: tiempo de simulación en que se recibió el mensaje.

        Retorna:
        - estado actualizado del blanco, si el AIS es válido.
        - None si el mensaje no contiene datos útiles.
        """

        if not ais_data.get("valid", False):
            return None

        mmsi = ais_data.get("mmsi")
        lat = ais_data.get("lat")
        lon = ais_data.get("lon")
        sog_kn = ais_data.get("sog_kn")
        cog_deg = ais_data.get("cog_deg")

        # Para seguimiento cinemático necesitamos al menos:
        # MMSI, posición, velocidad y curso.
        if mmsi is None or lat is None or lon is None:
            return None

        if sog_kn is None or cog_deg is None:
            return None

        target_state = {
            "mmsi": int(mmsi),
            "lat": float(lat),
            "lon": float(lon),
            "sog_kn": float(sog_kn),
            "cog_deg": float(cog_deg),
            "heading_deg": ais_data.get("heading_deg"),
            "last_update_s": float(received_at_s),
            "message_type": ais_data.get("message_type"),
            "navigation_status": ais_data.get("navigation_status"),
            "raw": ais_data.get("raw"),
        }

        self._targets[int(mmsi)] = target_state

        return target_state

    def get_target(self, mmsi: int) -> dict[str, Any] | None:
        """
        Retorna el último estado conocido de un blanco específico.
        """

        return self._targets.get(int(mmsi))

    def get_all_targets(self) -> list[dict[str, Any]]:
        """
        Retorna todos los blancos conocidos, incluyendo los que podrían
        estar vencidos por antigüedad.
        """

        return list(self._targets.values())

    def get_active_targets(self, current_time_s: float) -> list[dict[str, Any]]:
        """
        Retorna solo los blancos activos.

        Un blanco se considera activo si su última actualización ocurrió
        dentro de la ventana max_age_s.
        """

        active_targets = []

        for target in self._targets.values():
            age_s = float(current_time_s) - float(target["last_update_s"])

            if age_s <= self.max_age_s:
                active_targets.append(target)

        return active_targets

    def remove_stale_targets(self, current_time_s: float) -> None:
        """
        Elimina blancos antiguos que no han sido actualizados dentro
        del tiempo máximo permitido.
        """

        stale_mmsi = []

        for mmsi, target in self._targets.items():
            age_s = float(current_time_s) - float(target["last_update_s"])

            if age_s > self.max_age_s:
                stale_mmsi.append(mmsi)

        for mmsi in stale_mmsi:
            del self._targets[mmsi]


if __name__ == "__main__":
    tracker = TargetTracker(max_age_s=30.0)

    ais_message_1 = {
        "valid": True,
        "mmsi": 725000001,
        "lat": -33.0233,
        "lon": -71.6239,
        "sog_kn": 8.5,
        "cog_deg": 225.0,
        "heading_deg": 225.0,
        "message_type": 1,
        "navigation_status": "Under way using engine",
        "raw": "!AIVDM,...",
    }

    ais_message_2 = {
        "valid": True,
        "mmsi": 725000002,
        "lat": -33.0240,
        "lon": -71.6225,
        "sog_kn": 6.0,
        "cog_deg": 180.0,
        "heading_deg": 180.0,
        "message_type": 1,
        "navigation_status": "Under way using engine",
        "raw": "!AIVDM,...",
    }

    tracker.update_from_ais(ais_message_1, received_at_s=0.0)
    tracker.update_from_ais(ais_message_2, received_at_s=5.0)

    print("Todos los blancos:")
    print(tracker.get_all_targets())

    print("\nBlancos activos en t=10 s:")
    print(tracker.get_active_targets(current_time_s=10.0))

    print("\nBlancos activos en t=40 s:")
    print(tracker.get_active_targets(current_time_s=40.0))