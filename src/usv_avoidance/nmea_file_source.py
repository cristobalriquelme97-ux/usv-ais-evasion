import time
from pathlib import Path
from typing import Iterator


class NmeaFileSource:
    """
    Fuente de datos NMEA basada en archivo de texto.
    Simula la recepción secuencial de sentencias AIS.
    """

    def __init__(self, file_path: str, delay_s: float = 0.0):
        self.file_path = Path(file_path)
        self.delay_s = delay_s

    def read_sentences(self) -> Iterator[str]:
        if not self.file_path.exists():
            raise FileNotFoundError(f"No existe el archivo: {self.file_path}")

        with self.file_path.open("r", encoding="utf-8") as file:
            for line in file:
                sentence = line.strip()

                if not sentence:
                    continue

                yield sentence

                if self.delay_s > 0:
                    time.sleep(self.delay_s)