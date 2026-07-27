from __future__ import annotations

import time
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Iterator


FRAME_PREFIX = "#FRAME,"


@dataclass(frozen=True)
class NmeaFrame:
    """
    Conjunto de sentencias AIS pertenecientes al mismo instante
    de simulación.

    Atributos:
        timestamp_s:
            Tiempo de simulación asociado al frame, en segundos.

        sentences:
            Sentencias AIS recibidas durante ese instante.
    """

    timestamp_s: float
    sentences: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isfinite(self.timestamp_s):
            raise ValueError(
                "El tiempo del frame debe ser un número finito."
            )

        if self.timestamp_s < 0.0:
            raise ValueError(
                "El tiempo del frame no puede ser negativo."
            )

        if not self.sentences:
            raise ValueError(
                "Un frame debe contener al menos una sentencia AIS."
            )

        invalid_sentences = [
            sentence
            for sentence in self.sentences
            if not sentence.startswith(("!AIVDM", "!AIVDO"))
        ]

        if invalid_sentences:
            raise ValueError(
                "El frame contiene sentencias que no son AIS."
            )


class NmeaFileSource:
    """
    Fuente de datos NMEA basada en un archivo de texto.

    Permite dos modalidades de lectura:

    1. read_sentences():
       Mantiene el comportamiento original y entrega las
       sentencias AIS una por una.

    2. read_frames():
       Agrupa las sentencias que pertenecen al mismo instante
       de simulación.
    """

    def __init__(
        self,
        file_path: str,
        delay_s: float = 0.0,
    ) -> None:
        """
        Inicializa la fuente de datos.

        Parámetros:
            file_path:
                Ruta del archivo con sentencias NMEA.

            delay_s:
                Retardo real aplicado después de entregar una
                sentencia o un frame.
        """

        self.file_path = Path(file_path)
        self.delay_s = float(delay_s)

        if self.delay_s < 0.0:
            raise ValueError(
                "El retardo de lectura no puede ser negativo."
            )

    def _validate_file(self) -> None:
        """
        Verifica que el archivo configurado exista.
        """

        if not self.file_path.exists():
            raise FileNotFoundError(
                f"No existe el archivo: {self.file_path}"
            )

        if not self.file_path.is_file():
            raise ValueError(
                f"La ruta no corresponde a un archivo: "
                f"{self.file_path}"
            )

    def _wait_after_delivery(self) -> None:
        """
        Aplica el retardo configurado después de entregar datos.
        """

        if self.delay_s > 0.0:
            time.sleep(self.delay_s)

    @staticmethod
    def _parse_frame_timestamp(
        marker: str,
        *,
        line_number: int,
    ) -> float:
        """
        Extrae el tiempo de un marcador con formato:

            #FRAME,5.0
        """

        _, separator, raw_timestamp = marker.partition(",")

        if not separator or not raw_timestamp.strip():
            raise ValueError(
                "Marcador de frame inválido en la línea "
                f"{line_number}: {marker!r}"
            )

        try:
            timestamp_s = float(raw_timestamp.strip())
        except ValueError as exc:
            raise ValueError(
                "El tiempo del frame no es numérico en la línea "
                f"{line_number}: {marker!r}"
            ) from exc

        if not isfinite(timestamp_s):
            raise ValueError(
                "El tiempo del frame debe ser finito en la línea "
                f"{line_number}: {marker!r}"
            )

        if timestamp_s < 0.0:
            raise ValueError(
                "El tiempo del frame no puede ser negativo en la "
                f"línea {line_number}: {marker!r}"
            )

        return timestamp_s

    def read_sentences(self) -> Iterator[str]:
        """
        Lee el archivo línea por línea y entrega solamente
        sentencias AIS.

        Los marcadores #FRAME son ignorados en esta modalidad,
        manteniendo compatibilidad con el comportamiento anterior.
        """

        self._validate_file()

        with self.file_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            for line in file:
                sentence = line.strip()

                if not sentence:
                    continue

                if not sentence.startswith(
                    ("!AIVDM", "!AIVDO")
                ):
                    continue

                yield sentence
                self._wait_after_delivery()

    def read_frames(
        self,
        *,
        default_step_s: float = 5.0,
    ) -> Iterator[NmeaFrame]:
        """
        Lee el archivo agrupando las sentencias por instante.

        Formato explícito:

            #FRAME,0.0
            !AIVDM,...
            !AIVDM,...

            #FRAME,5.0
            !AIVDM,...
            !AIVDM,...

        Compatibilidad con archivos antiguos:

        Cuando el archivo no contiene marcadores #FRAME, cada
        sentencia AIS se transforma en un frame independiente.
        Sus tiempos se generan usando default_step_s.

        Parámetros:
            default_step_s:
                Intervalo temporal empleado para archivos antiguos
                sin marcadores de frame.
        """

        self._validate_file()

        default_step_s = float(default_step_s)

        if not isfinite(default_step_s):
            raise ValueError(
                "El intervalo temporal debe ser finito."
            )

        if default_step_s <= 0.0:
            raise ValueError(
                "El intervalo temporal debe ser mayor que cero."
            )

        explicit_frame_mode = False

        implicit_timestamp_s = 0.0

        current_timestamp_s: float | None = None
        current_sentences: list[str] = []

        last_explicit_timestamp_s: float | None = None

        with self.file_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            for line_number, line in enumerate(
                file,
                start=1,
            ):
                content = line.strip()

                if not content:
                    continue

                if content.startswith(FRAME_PREFIX):
                    timestamp_s = self._parse_frame_timestamp(
                        content,
                        line_number=line_number,
                    )

                    if (
                        last_explicit_timestamp_s is not None
                        and timestamp_s
                        <= last_explicit_timestamp_s
                    ):
                        raise ValueError(
                            "Los tiempos de los frames deben ser "
                            "estrictamente crecientes. Error en la "
                            f"línea {line_number}: {content!r}"
                        )

                    if (
                        explicit_frame_mode
                        and current_timestamp_s is not None
                        and current_sentences
                    ):
                        yield NmeaFrame(
                            timestamp_s=current_timestamp_s,
                            sentences=tuple(current_sentences),
                        )

                        self._wait_after_delivery()

                    explicit_frame_mode = True
                    current_timestamp_s = timestamp_s
                    current_sentences = []
                    last_explicit_timestamp_s = timestamp_s

                    continue

                if not content.startswith(
                    ("!AIVDM", "!AIVDO")
                ):
                    continue

                if explicit_frame_mode:
                    current_sentences.append(content)
                    continue

                yield NmeaFrame(
                    timestamp_s=implicit_timestamp_s,
                    sentences=(content,),
                )

                self._wait_after_delivery()

                implicit_timestamp_s += default_step_s

        if (
            explicit_frame_mode
            and current_timestamp_s is not None
            and current_sentences
        ):
            yield NmeaFrame(
                timestamp_s=current_timestamp_s,
                sentences=tuple(current_sentences),
            )

            self._wait_after_delivery()