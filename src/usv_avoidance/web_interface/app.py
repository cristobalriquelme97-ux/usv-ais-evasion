import json
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from flask import Flask, jsonify, render_template


app = Flask(__name__)


SIMULATOR_CURRENT_STEP_URL = "http://127.0.0.1:5000/api/current-step"


def fetch_current_visualization() -> dict:
    """
    Consulta el paso que actualmente está siendo visualizado
    en la interfaz principal de simulación.
    """

    try:
        with urlopen(
            SIMULATOR_CURRENT_STEP_URL,
            timeout=2.0,
        ) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    except HTTPError as error:
        raise RuntimeError(
            f"El simulador respondió con HTTP {error.code}."
        ) from error

    except URLError as error:
        raise RuntimeError(
            "No fue posible conectarse con web_app.py."
        ) from error
    
def map_recommended_action(
    decision: dict,
    state: dict,
) -> str:
    action = str(
        decision.get("action", "")
    ).strip().lower()

    action_map = {
        "turn_starboard": "TURN_STARBOARD",
        "starboard": "TURN_STARBOARD",
        "turn_port": "TURN_PORT",
        "port": "TURN_PORT",
        "maintain_course": "MAINTAIN_COURSE",
        "reduce_speed": "REDUCE_SPEED",
        "stop": "STOP",
        "return_to_route": "RETURN_TO_ROUTE",
    }

    if action in action_map:
        return action_map[action]

    current_state = state.get("current_state")

    if current_state == "RETURNING_TO_TRACK":
        return "RETURN_TO_ROUTE"

    return "MAINTAIN_COURSE"

def transform_step_to_dashboard(
    visualization: dict,
) -> dict:
    """
    Convierte la salida de simulation_runner al formato
    utilizado por la interfaz de recomendación.
    """

    step = visualization.get("step") or {}
    ownship = step.get("ownship") or {}
    targets = step.get("targets") or []
    state = step.get("state") or {}
    decision = step.get("avoidance_decision") or {}

    critical_mmsi = step.get("critical_target_mmsi")

    priority_target = next(
        (
            target
            for target in targets
            if target.get("mmsi") == critical_mmsi
        ),
        targets[0] if targets else None,
    )

    if priority_target is None:
        priority_target = {
            "mmsi": None,
            "cpa_m": 0.0,
            "tcpa_s": 0.0,
            "distance_m": 0.0,
            "encounter_type": "UNKNOWN",
        }

    recommended_action = map_recommended_action(
        decision=decision,
        state=state,
    )

    return {
        "scenario": visualization.get("scenario"),
        "frame": visualization.get("frame", 0),
        "time_s": step.get("time_s", 0.0),

        "own_ship": {
            "latitude": ownship.get("lat", 0.0),
            "longitude": ownship.get("lon", 0.0),
            "speed_knots": ownship.get("sog_kn", 0.0),
            "heading_deg": ownship.get(
                "cog_deg",
                ownship.get("heading_deg", 0.0),
            ),
        },

        "targets": [
            {
                "mmsi": target.get("mmsi"),
                "priority": target.get("priority"),
            }
            for target in targets
        ],

        "priority_target": {
            "mmsi": priority_target.get("mmsi"),
            "cpa_m": priority_target.get("cpa_m") or 0.0,
            "tcpa_s": priority_target.get("tcpa_s") or 0.0,
            "distance_m": (
                priority_target.get("distance_m") or 0.0
            ),
        },

        "navigation": {
            "previous_state": state.get(
                "previous_state",
                "TRACKING_ROUTE",
            ),
            "current_state": state.get(
                "current_state",
                "TRACKING_ROUTE",
            ),
            "encounter_type": priority_target.get(
                "encounter_type",
                "UNKNOWN",
            ),
            "recommended_action": recommended_action,
            "recommended_heading_deg": step.get(
                "commanded_course_deg",
                ownship.get("cog_deg", 0.0),
            ),
        },
    }

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/status")
def status():
    try:
        visualization = fetch_current_visualization()

        return jsonify(
            transform_step_to_dashboard(
                visualization
            )
        )

    except RuntimeError as error:
        return jsonify(
            {
                "error": str(error),
            }
        ), 503


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=4500,
        debug=True,
    )

