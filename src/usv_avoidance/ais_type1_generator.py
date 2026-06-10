import math
from pathlib import Path


# Conversión de nudos a metros por segundo.
# AIS normalmente trabaja la velocidad sobre el fondo en nudos,
# pero para mover la posición conviene usar m/s.
KNOT_TO_MPS = 0.514444

# Radio medio de la Tierra en metros.
# Se usa para convertir desplazamientos en metros a cambios de latitud/longitud.
EARTH_RADIUS_M = 6371000.0


def unsigned_to_bits(value: int, length: int) -> str:
    """
    Convierte un número entero sin signo a una cadena binaria de largo fijo.

    Por ejemplo:
    value = 5, length = 6
    resultado = '000101'

    Se usa para construir los campos binarios del mensaje AIS.
    """

    # Verifica que el valor pueda representarse en la cantidad de bits indicada.
    if value < 0 or value >= (1 << length):
        raise ValueError(f"Valor fuera de rango: {value} para {length} bits")

    # Convierte el valor a binario con ceros a la izquierda.
    return format(value, f"0{length}b")


def signed_to_bits(value: int, length: int) -> str:
    """
    Convierte un número entero con signo a binario usando complemento a dos.

    Esto es necesario porque algunos campos AIS pueden ser negativos,
    como la longitud, latitud o razón de giro.

    Por ejemplo:
    - Las longitudes oeste son negativas.
    - Las latitudes sur son negativas.
    """

    # Si el valor es negativo, se convierte a complemento a dos.
    if value < 0:
        value = (1 << length) + value

    # Luego se representa como binario sin signo.
    return unsigned_to_bits(value, length)


def sixbit_to_ais_char(value: int) -> str:
    """
    Convierte un valor de 6 bits, entre 0 y 63, al carácter ASCII usado
    en el payload AIS.

    AIS no transmite directamente los bits como '0' y '1'.
    Agrupa los bits de 6 en 6 y cada grupo se convierte en un carácter.
    """

    # Cada carácter AIS representa un valor de 6 bits.
    if value < 0 or value > 63:
        raise ValueError("Valor AIS 6-bit fuera de rango")

    # Mapeo especial usado por AIS para transformar valores de 6 bits
    # en caracteres ASCII imprimibles.
    if value < 40:
        return chr(value + 48)

    return chr(value + 56)


def calculate_checksum(body: str) -> str:
    """
    Calcula el checksum NMEA de una sentencia.

    El checksum se obtiene aplicando XOR a todos los caracteres entre:
    - el símbolo '!'
    - y el símbolo '*'

    Por ejemplo, para:
    !AIVDM,1,1,,A,payload,0*checksum

    El checksum se calcula sobre:
    AIVDM,1,1,,A,payload,0
    """

    checksum = 0

    # Se aplica XOR carácter por carácter.
    for char in body:
        checksum ^= ord(char)

    # Se retorna como número hexadecimal de dos dígitos.
    return f"{checksum:02X}"


def encode_type1_position_report(
    mmsi: int,
    lat: float,
    lon: float,
    sog_kn: float,
    cog_deg: float,
    heading_deg: int | None = None,
    timestamp: int = 0,
    nav_status: int = 0,
) -> str:
    """
    Genera una sentencia AIS AIVDM tipo 1.

    El mensaje AIS tipo 1 corresponde a:
    Position Report Class A.

    Este mensaje informa principalmente:
    - MMSI del buque
    - estado de navegación
    - velocidad sobre el fondo, SOG
    - posición geográfica
    - curso sobre el fondo, COG
    - rumbo verdadero, Heading
    - timestamp
    """

    # Tipo de mensaje AIS.
    # El tipo 1 es reporte de posición de buque Clase A.
    message_type = 1

    # Indicador de repetición.
    # 0 significa que el mensaje no ha sido repetido.
    repeat_indicator = 0

    # Razón de giro, ROT.
    # Aquí se deja en cero, es decir, sin giro simulado.
    rot_raw = 0

    # Precisión de posición.
    # 0 generalmente indica baja precisión o precisión no especificada.
    position_accuracy = 0

    # Indicador de maniobra.
    # 0 significa no disponible o sin maniobra especial.
    maneuver_indicator = 0

    # Bits de reserva.
    spare = 0

    # Bandera RAIM.
    # 0 indica que RAIM no está siendo usado.
    raim_flag = 0

    # Estado de radio AIS.
    # Aquí se deja en cero para simplificar la simulación.
    radio_status = 0

    # AIS codifica la velocidad SOG en décimas de nudo.
    # Por ejemplo: 8.5 kn se codifica como 85.
    sog_raw = int(round(sog_kn * 10))

    # Se limita el valor al rango permitido.
    # 1023 suele representar valor no disponible,
    # por eso aquí se limita hasta 1022.
    sog_raw = max(0, min(sog_raw, 1022))

    # AIS codifica el COG en décimas de grado.
    # Por ejemplo: 45.0° se codifica como 450.
    # El módulo 360 asegura que el curso quede entre 0 y 359.9 grados.
    cog_raw = int(round((cog_deg % 360) * 10))

    # El heading AIS usa 511 cuando el dato no está disponible.
    if heading_deg is None:
        heading_raw = 511
    else:
        # Si hay rumbo, se redondea y se mantiene entre 0 y 359 grados.
        heading_raw = int(round(heading_deg)) % 360

    # AIS codifica longitud y latitud en grados multiplicados por 600000.
    # Esto equivale a usar una resolución de 1/10000 de minuto.
    #
    # Longitud oeste y latitud sur son negativas.
    lon_raw = int(round(lon * 600000))
    lat_raw = int(round(lat * 600000))

    # Construcción del mensaje AIS completo en bits.
    #
    # Cada campo tiene una cantidad fija de bits según la estructura
    # del mensaje AIS tipo 1.
    bits = (
        unsigned_to_bits(message_type, 6)          # Tipo de mensaje: 6 bits
        + unsigned_to_bits(repeat_indicator, 2)   # Indicador de repetición: 2 bits
        + unsigned_to_bits(mmsi, 30)              # MMSI: 30 bits
        + unsigned_to_bits(nav_status, 4)         # Estado de navegación: 4 bits
        + signed_to_bits(rot_raw, 8)              # Razón de giro ROT: 8 bits
        + unsigned_to_bits(sog_raw, 10)           # Velocidad SOG: 10 bits
        + unsigned_to_bits(position_accuracy, 1)  # Precisión de posición: 1 bit
        + signed_to_bits(lon_raw, 28)             # Longitud: 28 bits
        + signed_to_bits(lat_raw, 27)             # Latitud: 27 bits
        + unsigned_to_bits(cog_raw, 12)           # Curso COG: 12 bits
        + unsigned_to_bits(heading_raw, 9)        # Rumbo verdadero: 9 bits
        + unsigned_to_bits(timestamp % 60, 6)     # Segundo UTC: 6 bits
        + unsigned_to_bits(maneuver_indicator, 2) # Indicador de maniobra: 2 bits
        + unsigned_to_bits(spare, 3)              # Bits de reserva: 3 bits
        + unsigned_to_bits(raim_flag, 1)          # Bandera RAIM: 1 bit
        + unsigned_to_bits(radio_status, 19)      # Estado de radio: 19 bits
    )

    # Un mensaje AIS tipo 1 debe tener exactamente 168 bits.
    if len(bits) != 168:
        raise ValueError(f"El mensaje AIS tipo 1 debe tener 168 bits, tiene {len(bits)}")

    # Se construye el payload AIS.
    # Para ello se toman los 168 bits en grupos de 6 bits.
    payload = ""

    for i in range(0, len(bits), 6):
        # Extrae un bloque de 6 bits.
        sixbit_value = int(bits[i:i + 6], 2)

        # Convierte ese bloque al carácter AIS correspondiente.
        payload += sixbit_to_ais_char(sixbit_value)

    # Como 168 es divisible por 6, no se necesitan bits de relleno.
    fill_bits = 0

    # Cuerpo de la sentencia NMEA.
    #
    # Formato:
    # AIVDM,total_fragmentos,numero_fragmento,id_secuencial,canal,payload,fill_bits
    #
    # En este caso:
    # AIVDM -> mensaje AIS recibido
    # 1     -> solo hay un fragmento
    # 1     -> este es el fragmento número 1
    # vacío -> sin ID secuencial
    # A     -> canal AIS A
    body = f"AIVDM,1,1,,A,{payload},{fill_bits}"

    # Calcula el checksum NMEA del cuerpo de la sentencia.
    checksum = calculate_checksum(body)

    # Retorna la sentencia completa.
    return f"!{body}*{checksum}"


def move_position(
    lat: float,
    lon: float,
    sog_kn: float,
    cog_deg: float,
    delta_t_s: float,
) -> tuple[float, float]:
    """
    Actualiza la latitud y longitud de forma aproximada usando:
    - velocidad sobre el fondo, SOG
    - curso sobre el fondo, COG
    - intervalo de tiempo

    Esta aproximación es válida para simulaciones locales o distancias pequeñas.
    """

    # Convierte la velocidad de nudos a metros por segundo.
    speed_mps = sog_kn * KNOT_TO_MPS

    # Convierte el curso de grados a radianes.
    course_rad = math.radians(cog_deg)

    # Descomposición de la velocidad en componentes Este y Norte.
    #
    # En navegación:
    # COG = 0°   -> movimiento hacia el norte
    # COG = 90°  -> movimiento hacia el este
    # COG = 180° -> movimiento hacia el sur
    # COG = 270° -> movimiento hacia el oeste
    east_m = speed_mps * math.sin(course_rad) * delta_t_s
    north_m = speed_mps * math.cos(course_rad) * delta_t_s

    # Convierte el desplazamiento hacia el norte en cambio de latitud.
    delta_lat = (north_m / EARTH_RADIUS_M) * (180.0 / math.pi)

    # Convierte el desplazamiento hacia el este en cambio de longitud.
    # Se divide por cos(latitud) porque la distancia equivalente a un grado
    # de longitud cambia según la latitud.
    delta_lon = (east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat)))) * (180.0 / math.pi)

    # Retorna la nueva posición.
    return lat + delta_lat, lon + delta_lon


def generate_moving_target_scenario(
    output_file: str,
    mmsi: int,
    lat0: float,
    lon0: float,
    sog_kn: float,
    cog_deg: float,
    heading_deg: int,
    duration_s: int,
    step_s: int,
) -> None:
    """
    Genera un archivo de sentencias AIS/NMEA para un blanco móvil.

    El blanco mantiene:
    - mismo MMSI
    - misma velocidad SOG
    - mismo curso COG
    - mismo heading

    Lo que cambia en cada sentencia es principalmente:
    - latitud
    - longitud
    - timestamp
    """

    # Define la ruta del archivo de salida.
    output_path = Path(output_file)

    # Crea la carpeta de salida si no existe.
    # Por ejemplo, crea data/scenarios/
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Posición inicial del blanco.
    lat = lat0
    lon = lon0

    # Abre el archivo de salida en modo escritura.
    with output_path.open("w", encoding="utf-8") as file:

        # Genera una sentencia cada step_s segundos.
        # Por ejemplo, si duration_s = 120 y step_s = 5,
        # genera sentencias desde t = 0 hasta t = 120.
        for t in range(0, duration_s + 1, step_s):

            # Genera una sentencia AIS tipo 1 para la posición actual.
            sentence = encode_type1_position_report(
                mmsi=mmsi,
                lat=lat,
                lon=lon,
                sog_kn=sog_kn,
                cog_deg=cog_deg,
                heading_deg=heading_deg,
                timestamp=t,
            )

            # Escribe la sentencia en el archivo.
            file.write(sentence + "\n")

            # Actualiza la posición del blanco para el siguiente instante.
            lat, lon = move_position(
                lat=lat,
                lon=lon,
                sog_kn=sog_kn,
                cog_deg=cog_deg,
                delta_t_s=step_s,
            )


if __name__ == "__main__":
    from scenario_config import (
        OUTPUT_FILE,
        TARGET_MMSI,
        TARGET_LAT0,
        TARGET_LON0,
        TARGET_SOG_KN,
        TARGET_COG_DEG,
        TARGET_HEADING_DEG,
        DURATION_S,
        STEP_S,
    )

    generate_moving_target_scenario(
        output_file=OUTPUT_FILE,
        mmsi=TARGET_MMSI,
        lat0=TARGET_LAT0,
        lon0=TARGET_LON0,
        sog_kn=TARGET_SOG_KN,
        cog_deg=TARGET_COG_DEG,
        heading_deg=TARGET_HEADING_DEG,
        duration_s=DURATION_S,
        step_s=STEP_S,
    )

    print(f"Escenario AIS generado correctamente en: {OUTPUT_FILE}")