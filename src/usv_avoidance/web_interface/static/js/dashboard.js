const UPDATE_INTERVAL_MS = 1000;


const stateNames = {
    NORMAL_NAVIGATION: "Navegación normal",
    TRACKING_ROUTE: "Seguimiento de ruta",
    TRACKING_TARGET: "Seguimiento de blanco",
    ASSESSING_TARGET: "Evaluando blanco",
    RISK_DETECTED: "Riesgo detectado",
    EVALUATING_MANEUVER: "Evaluando maniobra",
    AVOIDING_TARGET: "Maniobra de evasión",
    MONITORING_CPA: "Verificando separación",
    MONITORING_PMA: "Verificando separación",
    RETURNING_ROUTE: "Retorno a la ruta",
    RETURNING_TO_TRACK: "Retorno a la trayectoria",
};


const encounterNames = {
    HEAD_ON: "Vuelta encontrada",
    CROSSING_STARBOARD: "Cruce por estribor",
    CROSSING_PORT: "Cruce por babor",
    OVERTAKING: "Alcance",
    BEING_OVERTAKEN: "Siendo alcanzado",
    SAFE: "Sin riesgo de colisión",
    UNKNOWN: "Encuentro no determinado",
};


const actionNames = {
    TURN_STARBOARD: "Caer a estribor",
    TURN_PORT: "Caer a babor",
    MAINTAIN_COURSE: "Mantener rumbo",
    REDUCE_SPEED: "Reducir velocidad",
    STOP: "Detener avance",
    RETURN_TO_ROUTE: "Retornar a la ruta",
    NONE: "Sin maniobra requerida",
};


function formatCoordinate(value, positive, negative) {
    const direction = value >= 0 ? positive : negative;
    return `${Math.abs(value).toFixed(5)}° ${direction}`;
}


function formatHeading(value) {
    return String(Math.round(value)).padStart(3, "0");
}


function formatTcpa(totalSeconds) {
    if (!Number.isFinite(totalSeconds) || totalSeconds < 0) {
        return "--:--";
    }

    const minutes = Math.floor(totalSeconds / 60);
    const seconds = Math.floor(totalSeconds % 60);

    return (
        `${String(minutes).padStart(2, "0")}:` +
        `${String(seconds).padStart(2, "0")}`
    );
}


function calculateHeadingDifference(currentHeading, recommendedHeading) {
    let difference = (
        recommendedHeading - currentHeading + 540
    ) % 360 - 180;

    if (Math.abs(difference) < 0.5) {
        return "Mantener rumbo actual";
    }

    const direction = difference > 0
        ? "a estribor"
        : "a babor";

    return `${Math.abs(difference).toFixed(0)}° ${direction}`;
}


function renderTargets(targets) {
    const tableBody = document.getElementById("targetsTableBody");
    const targetCount = document.getElementById("targetCount");

    tableBody.innerHTML = "";
    targetCount.textContent = targets.length;

    if (targets.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="2">
                    No se detectan blancos AIS
                </td>
            </tr>
        `;
        return;
    }

    targets.forEach((target) => {
        const row = document.createElement("tr");

        row.innerHTML = `
            <td>${target.mmsi}</td>
            <td>
                <span class="priority-badge">
                    ${target.priority}
                </span>
            </td>
        `;

        tableBody.appendChild(row);
    });
}


function updateDashboard(data) {
    const ownShip = data.own_ship;
    const target = data.priority_target;
    const navigation = data.navigation;

    document.getElementById("latitude").textContent =
        formatCoordinate(ownShip.latitude, "N", "S");

    document.getElementById("longitude").textContent =
        formatCoordinate(ownShip.longitude, "E", "O");

    document.getElementById("speed").textContent =
        ownShip.speed_knots.toFixed(1);

    document.getElementById("currentHeading").textContent =
        formatHeading(ownShip.heading_deg);

    document.getElementById("recommendedHeading").textContent =
        formatHeading(navigation.recommended_heading_deg);

    document.getElementById("cpa").textContent =
        target.cpa_m.toFixed(1);

    document.getElementById("tcpa").textContent =
        formatTcpa(target.tcpa_s);

    document.getElementById("distance").textContent =
        target.distance_m.toFixed(0);

    document.getElementById("priorityMmsi").textContent =
        target.mmsi;

    const currentStateKey = String(
        navigation.current_state ?? "UNKNOWN"
    ).trim().toUpperCase();

    document.getElementById("currentState").textContent =
        stateNames[currentStateKey]
        ?? "Estado no determinado";

    const previousStateKey = String(
        navigation.previous_state ?? "UNKNOWN"
    ).trim().toUpperCase();

    document.getElementById("previousState").textContent =
        stateNames[previousStateKey]
        ?? "Estado no determinado";

    const encounterKey = String(
        navigation.encounter_type ?? "UNKNOWN"
    ).trim().toUpperCase();

    document.getElementById("encounterType").textContent =
        encounterNames[encounterKey]
        ?? "Encuentro no determinado";

    document.getElementById("recommendedAction").textContent =
        actionNames[navigation.recommended_action]
        ?? navigation.recommended_action;

    const headingDifference = calculateHeadingDifference(
        ownShip.heading_deg,
        navigation.recommended_heading_deg
    );

    document.getElementById("headingVariation").textContent =
        headingDifference;

    document.getElementById("recommendationDescription").textContent =
        `Cambiar desde ${formatHeading(ownShip.heading_deg)}° ` +
        `hasta ${formatHeading(navigation.recommended_heading_deg)}°.`;

    document.getElementById("vesselIcon").style.transform =
        `rotate(${ownShip.heading_deg}deg)`;

    renderTargets(data.targets);

    document.getElementById("lastUpdate").textContent =
        `Última actualización: ${new Date().toLocaleTimeString("es-CL")}`;
}


function setConnectionStatus(connected) {
    const connectionText = document.getElementById("connectionText");
    const statusDot = document.querySelector(".status-dot");

    if (connected) {
        connectionText.textContent = "Sistema conectado";
        statusDot.style.background = "var(--green)";
        statusDot.style.boxShadow = "0 0 12px var(--green)";
    } else {
        connectionText.textContent = "Sin conexión con el servidor";
        statusDot.style.background = "var(--red)";
        statusDot.style.boxShadow = "0 0 12px var(--red)";
    }
}


async function fetchDashboardData() {
    try {
        const response = await fetch("/api/status", {
            cache: "no-store",
        });

        if (!response.ok) {
            throw new Error(
                `Respuesta HTTP inválida: ${response.status}`
            );
        }

        const data = await response.json();

        updateDashboard(data);
        setConnectionStatus(true);

    } catch (error) {
        console.error(
            "No fue posible actualizar la interfaz:",
            error
        );

        setConnectionStatus(false);
    }
}


fetchDashboardData();

setInterval(
    fetchDashboardData,
    UPDATE_INTERVAL_MS
);