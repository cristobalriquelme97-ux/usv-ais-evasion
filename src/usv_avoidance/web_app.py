from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from usv_avoidance.simulation_runner import list_scenarios, run_scenario

current_visualization = {
    "scenario": None,
    "frame": 0,
    "step": None,
}

def create_app() -> Flask:
    app = Flask(
    __name__,
    template_folder="web_interface_2/templates",
    static_folder="web_interface_2/static",
    )   

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/api/scenarios")
    def scenarios():
        return jsonify(
            {
                "scenarios": list_scenarios(),
            }
        )

    @app.get("/api/run")
    def run_selected_scenario():
        scenario = request.args.get("scenario")
        save_results = request.args.get("save", "false").lower() == "true"

        try:
            result = run_scenario(
                scenario_name=scenario,
                save_results=save_results,
            )
        except FileNotFoundError as error:
            return jsonify({"error": str(error)}), 404

        return jsonify(result)
    
    @app.post("/api/current-step")
    def update_current_step():
        """
        Recibe desde la interfaz de simulación el paso que
        actualmente está siendo visualizado.
        """
        global current_visualization

        payload = request.get_json(silent=True)

        if not isinstance(payload, dict):
            return jsonify(
                {
                    "error": "Se esperaba un objeto JSON.",
                }
            ), 400

        step = payload.get("step")

        if not isinstance(step, dict):
            return jsonify(
                {
                    "error": "El campo 'step' es obligatorio.",
                }
            ), 400

        current_visualization = {
            "scenario": payload.get("scenario"),
            "frame": payload.get("frame", 0),
            "step": step,
        }

        return jsonify(
            {
                "status": "ok",
                "frame": current_visualization["frame"],
            }
        )


    @app.get("/api/current-step")
    def get_current_step():
        """
        Entrega el paso que actualmente está siendo visualizado.
        """
        if current_visualization["step"] is None:
            return jsonify(
                {
                    "error": "Todavía no existe un paso visualizado.",
                    "scenario": None,
                    "frame": 0,
                    "step": None,
                }
            ), 404

        return jsonify(current_visualization)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
