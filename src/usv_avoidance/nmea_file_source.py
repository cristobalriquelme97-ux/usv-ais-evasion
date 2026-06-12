import time
from pathlib import Path
from typing import Iterator


class NmeaFileSource:

    """
    Fuente de datos NMEA basada en archivo de texto.

    Esta clase permite simular la recepción secuencial de sentencias AIS/NMEA
    desde un archivo previamente generado o registrado.

    Puede utilizarse con:
    - archivos simulados generados por ais_type1_generator.py
    - archivos reales capturados desde un receptor AIS
    """
    
    def __init__(self, file_path: str, delay_s: float = 0.0):

        """
        Inicializa la fuente de datos.

        Parámetros:
        file_path : ruta del archivo .txt con sentencias NMEA.
        delay_s   : retardo entre sentencias, en segundos.
                    Sirve para simular recepción en tiempo real.
        """

        self.file_path = Path(file_path)
        self.delay_s = delay_s

    def read_sentences(self) -> Iterator[str]:

        """
        Lee el archivo línea por línea y entrega sentencias AIS válidas.

        Cada sentencia se entrega usando yield, por lo que no se carga
        todo el archivo de una sola vez.

        Retorna:
        Iterator[str] con sentencias tipo !AIVDM o !AIVDO.
        """

        if not self.file_path.exists():
            raise FileNotFoundError(f"No existe el archivo: {self.file_path}")

        with self.file_path.open("r", encoding="utf-8") as file:
            for line in file:
                sentence = line.strip()

                if not sentence:
                    continue

                # Filtra solo sentencias AIS.
                if not sentence.startswith(("!AIVDM", "!AIVDO")):
                    continue

                yield sentence

                # Simula espera entre reportes AIS.
                if self.delay_s > 0:
                    time.sleep(self.delay_s)