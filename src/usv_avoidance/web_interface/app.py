from flask import Flask, jsonify, render_template


app = Flask(__name__)


def get_dashboard_data() -> dict:
    """
    Devuelve los datos que serán visualizados en la interfaz.

    En esta primera versión se utilizan datos simulados.
    Más adelante esta función obtendrá la información desde
    el algoritmo de evasión.
    """

    return {
        "own_ship": {
            "latitude": -41.9483,
            "longitude": -73.7016,
            "speed_knots": 12.0,
            "heading_deg": 43.0,
        },
        "targets": [
            {
                "mmsi": "725000003",
                "priority": 1,
            },
            {
                "mmsi": "725000001",
                "priority": 2,
            },
            {
                "mmsi": "725000002",
                "priority": 3,
            },
        ],
        "priority_target": {
            "mmsi": "725000003",
            "cpa_m": 57.2,
            "tcpa_s": 1960,
            "distance_m": 140.0,
        },
        "navigation": {
            "previous_state": "TRACKING_ROUTE",
            "current_state": "AVOIDING",
            "encounter_type": "HEAD_ON",
            "recommended_action": "TURN_STARBOARD",
            "recommended_heading_deg": 78.0,
        },
    }


@app.get("/")
def index():
    """
    Muestra la página principal de la interfaz.
    """
    return render_template("index.html")


@app.get("/api/status")
def status():
    """
    Entrega el estado actual del algoritmo en formato JSON.
    """
    return jsonify(get_dashboard_data())


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=4500,
        debug=True,
    )