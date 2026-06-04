from __future__ import annotations

import sys
import json
from typing import Optional, Dict, Any, Tuple


NAV_STATUS = {
    0: "Under way using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted manoeuverability",
    4: "Constrained by draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    15: "Undefined",
}


def calculate_nmea_checksum(sentence_body: str) -> int:
    """
    Calcula el checksum NMEA.
    Recibe solo el contenido entre ! y *.
    """
    checksum = 0
    for char in sentence_body:
        checksum ^= ord(char)
    return checksum


def split_nmea_sentence(sentence: str) -> Dict[str, Any]:
    """
    Separa una sentencia NMEA y valida su checksum.

    Ejemplo:
    !AIVDM,1,1,,A,15Muq?002>G?svP00<:O?vN60<0,0*5C
    """

    sentence = sentence.strip()

    if not sentence:
        return {
            "valid": False,
            "error": "Sentencia vacía",
        }

    if not sentence.startswith(("!", "$")):
        return {
            "valid": False,
            "error": "La sentencia no comienza con ! o $",
            "raw": sentence,
        }

    if "*" not in sentence:
        return {
            "valid": False,
            "error": "La sentencia no contiene checksum",
            "raw": sentence,
        }

    body, received_checksum_text = sentence[1:].split("*", 1)
    received_checksum_text = received_checksum_text[:2]

    try:
        received_checksum = int(received_checksum_text, 16)
    except ValueError:
        return {
            "valid": False,
            "error": "Checksum recibido no es hexadecimal válido",
            "raw": sentence,
        }

    calculated_checksum = calculate_nmea_checksum(body)

    checksum_ok = calculated_checksum == received_checksum

    fields = body.split(",")

    return {
        "valid": checksum_ok,
        "checksum_ok": checksum_ok,
        "checksum_calculated": f"{calculated_checksum:02X}",
        "checksum_received": f"{received_checksum:02X}",
        "fields": fields,
        "raw": sentence,
    }


def ais_char_to_sixbit(char: str) -> int:
    """
    Convierte un carácter ASCII del payload AIS a valor de 6 bits.
    """

    value = ord(char) - 48

    if value > 40:
        value -= 8

    if value < 0 or value > 63:
        raise ValueError(f"Carácter AIS inválido: {char}")

    return value


def payload_to_bits(payload: str, fill_bits: int) -> str:
    """
    Convierte el payload AIS en una cadena binaria.
    Cada carácter equivale a 6 bits.
    """

    bits = ""

    for char in payload:
        sixbit_value = ais_char_to_sixbit(char)
        bits += format(sixbit_value, "06b")

    if fill_bits > 0:
        bits = bits[:-fill_bits]

    return bits


def get_unsigned(bits: str, start: int, length: int) -> int:
    """
    Extrae un campo sin signo desde la cadena binaria.
    """
    return int(bits[start:start + length], 2)


def get_signed(bits: str, start: int, length: int) -> int:
    """
    Extrae un campo con signo en complemento a dos.
    """
    value = get_unsigned(bits, start, length)

    sign_bit = 1 << (length - 1)

    if value & sign_bit:
        value -= 1 << length

    return value


def decode_rate_of_turn(rot_raw: int) -> Optional[float]:
    """
    Decodifica ROT, Rate of Turn.
    Devuelve grados por minuto aproximadamente.

    rot_raw = -128 significa no disponible.
    """

    if rot_raw == -128:
        return None

    if rot_raw == 0:
        return 0.0

    rot = (rot_raw / 4.733) ** 2

    if rot_raw < 0:
        rot *= -1

    return rot


def decode_position_report_class_a(bits: str) -> Dict[str, Any]:
    """
    Decodifica mensajes AIS tipo 1, 2 y 3.
    Estos son reportes de posición Clase A.
    """

    if len(bits) < 168:
        return {
            "valid": False,
            "error": f"Mensaje tipo 1/2/3 demasiado corto: {len(bits)} bits. Se esperaban 168 bits.",
        }

    message_type = get_unsigned(bits, 0, 6)
    repeat_indicator = get_unsigned(bits, 6, 2)
    mmsi = get_unsigned(bits, 8, 30)

    nav_status_code = get_unsigned(bits, 38, 4)
    rot_raw = get_signed(bits, 42, 8)

    sog_raw = get_unsigned(bits, 50, 10)
    position_accuracy = get_unsigned(bits, 60, 1)

    lon_raw = get_signed(bits, 61, 28)
    lat_raw = get_signed(bits, 89, 27)

    cog_raw = get_unsigned(bits, 116, 12)
    heading_raw = get_unsigned(bits, 128, 9)

    timestamp = get_unsigned(bits, 137, 6)
    maneuver_indicator = get_unsigned(bits, 143, 2)
    raim_flag = get_unsigned(bits, 148, 1)

    # Conversión de unidades
    sog_kn = None if sog_raw == 1023 else sog_raw / 10.0

    lon_deg = lon_raw / 600000.0
    lat_deg = lat_raw / 600000.0

    # Validación básica de posición
    if abs(lon_deg) > 180:
        lon_deg = None

    if abs(lat_deg) > 90:
        lat_deg = None

    # COG en décimas de grado
    if cog_raw >= 3600:
        cog_deg = None
    else:
        cog_deg = cog_raw / 10.0

    # Heading verdadero
    if heading_raw == 511 or heading_raw > 359:
        heading_deg = None
    else:
        heading_deg = heading_raw

    return {
        "valid": True,
        "message_type": message_type,
        "message_name": "Position Report Class A",
        "repeat_indicator": repeat_indicator,
        "mmsi": mmsi,
        "navigation_status_code": nav_status_code,
        "navigation_status": NAV_STATUS.get(nav_status_code, "Unknown"),
        "rot_raw": rot_raw,
        "rot_deg_per_min": decode_rate_of_turn(rot_raw),
        "sog_kn": sog_kn,
        "position_accuracy": position_accuracy,
        "lon": lon_deg,
        "lat": lat_deg,
        "cog_deg": cog_deg,
        "heading_deg": heading_deg,
        "timestamp": timestamp,
        "maneuver_indicator": maneuver_indicator,
        "raim_flag": raim_flag,
    }


def decode_ais_payload(payload: str, fill_bits: int) -> Dict[str, Any]:
    """
    Decodifica el payload AIS.
    """

    try:
        bits = payload_to_bits(payload, fill_bits)
    except ValueError as error:
        return {
            "valid": False,
            "error": str(error),
        }

    if len(bits) < 6:
        return {
            "valid": False,
            "error": "Payload demasiado corto",
        }

    message_type = get_unsigned(bits, 0, 6)

    if message_type in (1, 2, 3):
        decoded = decode_position_report_class_a(bits)
        decoded["payload_bits_length"] = len(bits)
        return decoded

    return {
        "valid": True,
        "message_type": message_type,
        "message_name": "Mensaje AIS no implementado en este adaptador",
        "payload_bits_length": len(bits),
        "note": "Por ahora el script solo decodifica mensajes tipo 1, 2 y 3.",
    }


class AisNmeaReceiver:
    """
    Receptor lógico de sentencias AIS/NMEA.

    Recibe líneas NMEA, valida checksum, reensambla fragmentos
    y entrega diccionarios listos para el algoritmo.
    """

    def __init__(self, strict_checksum: bool = True):
        self.strict_checksum = strict_checksum
        self.fragment_buffer: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    def ingest(self, sentence: str) -> Optional[Dict[str, Any]]:
        parsed = split_nmea_sentence(sentence)

        if not parsed["valid"]:
            if self.strict_checksum:
                return {
                    "valid": False,
                    "stage": "checksum",
                    "error": "Checksum inválido",
                    "checksum_calculated": parsed.get("checksum_calculated"),
                    "checksum_received": parsed.get("checksum_received"),
                    "raw": parsed.get("raw"),
                }

        fields = parsed.get("fields", [])

        if len(fields) < 7:
            return {
                "valid": False,
                "stage": "nmea",
                "error": "Cantidad insuficiente de campos NMEA",
                "raw": sentence.strip(),
            }

        sentence_type = fields[0]

        if sentence_type not in ("AIVDM", "AIVDO"):
            return {
                "valid": False,
                "stage": "nmea",
                "error": f"Tipo de sentencia no soportado: {sentence_type}",
                "raw": sentence.strip(),
            }

        try:
            total_fragments = int(fields[1])
            fragment_number = int(fields[2])
            sequential_id = fields[3]
            radio_channel = fields[4]
            payload = fields[5]
            fill_bits = int(fields[6])
        except Exception as error:
            return {
                "valid": False,
                "stage": "nmea",
                "error": f"Error al leer campos NMEA: {error}",
                "raw": sentence.strip(),
            }

        # Caso simple: un solo fragmento
        if total_fragments == 1:
            decoded = decode_ais_payload(payload, fill_bits)

            decoded.update({
                "nmea_type": sentence_type,
                "radio_channel": radio_channel,
                "checksum_ok": parsed.get("checksum_ok"),
                "raw": sentence.strip(),
            })

            return decoded

        # Caso multifragmento
        key = (sentence_type, sequential_id, radio_channel)

        if key not in self.fragment_buffer:
            self.fragment_buffer[key] = {
                "total_fragments": total_fragments,
                "fragments": [None] * total_fragments,
                "fill_bits": 0,
                "raw_sentences": [],
            }

        buffer = self.fragment_buffer[key]

        buffer["fragments"][fragment_number - 1] = payload
        buffer["raw_sentences"].append(sentence.strip())

        # Los fill bits relevantes son los del último fragmento
        if fragment_number == total_fragments:
            buffer["fill_bits"] = fill_bits

        # Si todavía faltan fragmentos, no se decodifica
        if any(fragment is None for fragment in buffer["fragments"]):
            return None

        complete_payload = "".join(buffer["fragments"])
        final_fill_bits = buffer["fill_bits"]
        raw_sentences = buffer["raw_sentences"]

        del self.fragment_buffer[key]

        decoded = decode_ais_payload(complete_payload, final_fill_bits)

        decoded.update({
            "nmea_type": sentence_type,
            "radio_channel": radio_channel,
            "checksum_ok": parsed.get("checksum_ok"),
            "raw": raw_sentences,
        })

        return decoded


def main():
    """
    Modo de prueba:
    Permite leer sentencias AIS desde la entrada estándar.

    Uso:
    python ais_adapter.py < sample_nmea.txt
    """

    receiver = AisNmeaReceiver(strict_checksum=True)

    for line in sys.stdin:
        result = receiver.ingest(line)

        if result is not None:
            print(json.dumps(result, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    main()