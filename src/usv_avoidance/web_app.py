from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from usv_avoidance.simulation_runner import list_scenarios, run_scenario


def create_app() -> Flask:
    app = Flask(__name__)

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

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
