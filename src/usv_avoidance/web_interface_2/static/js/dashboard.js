const state = {
    scenarios: [],
    result: null,
    frame: 0,
    timer: null,
};

const els = {
    scenarioSelect: document.querySelector("#scenarioSelect"),
    runButton: document.querySelector("#runButton"),
    playButton: document.querySelector("#playButton"),
    resetButton: document.querySelector("#resetButton"),
    timeSlider: document.querySelector("#timeSlider"),
    canvas: document.querySelector("#plotCanvas"),
    scenarioDescription: document.querySelector("#scenarioDescription"),
    currentState: document.querySelector("#currentState"),
    previousState: document.querySelector("#previousState"),
    commandedCourse: document.querySelector("#commandedCourse"),
    criticalTarget: document.querySelector("#criticalTarget"),
    timeValue: document.querySelector("#timeValue"),
    cpaValue: document.querySelector("#cpaValue"),
    tcpaValue: document.querySelector("#tcpaValue"),
    distanceValue: document.querySelector("#distanceValue"),
    cogValue: document.querySelector("#cogValue"),
    targetsTable: document.querySelector("#targetsTable"),
    encounterValue: document.querySelector("#encounterValue"),
    roleValue: document.querySelector("#roleValue"),
    actionValue: document.querySelector("#actionValue"),
    reasonValue: document.querySelector("#reasonValue"),
};

const ctx = els.canvas.getContext("2d");

async function init() {
    const response = await fetch("/api/scenarios");
    const data = await response.json();
    state.scenarios = data.scenarios || [];

    els.scenarioSelect.innerHTML = state.scenarios
        .map((scenario) => {
            const value = scenario.output_file || `${scenario.name}.txt`;
            return `<option value="${value}">${scenario.name}</option>`;
        })
        .join("");

    await runScenario();
}

async function runScenario() {
    stopPlayback();
    setBusy(true);

    const selected = els.scenarioSelect.value;
    const response = await fetch(`/api/run?scenario=${encodeURIComponent(selected)}`);
    state.result = await response.json();
    state.frame = 0;

    if (state.result.error) {
        els.scenarioDescription.textContent = state.result.error;
        setBusy(false);
        return;
    }

    const scenarioMeta = state.scenarios.find((item) => item.output_file === selected);
    els.scenarioDescription.textContent = scenarioMeta?.description || state.result.scenario.name;

    els.timeSlider.max = Math.max(0, state.result.steps.length - 1);
    els.timeSlider.value = 0;
    render();
    setBusy(false);
}

async function publishCurrentStep(step) {
    try {
        await fetch("/api/current-step", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                scenario: state.result?.scenario?.name ?? null,
                frame: state.frame,
                step: step,
            }),
        });
    } catch (error) {
        console.error(
            "No fue posible publicar el paso actual:",
            error
        );
    }
}


function render() {
    if (!state.result || !state.result.steps.length) {
        clearCanvas();
        return;
    }

    const step = state.result.steps[state.frame];

    publishCurrentStep(step);

    const critical = getCriticalTarget(step);
    const decision = step.avoidance_decision;
    const currentState = step.state.current_state || "--";

    els.currentState.textContent = currentState;
    els.currentState.className = `state-${currentState}`;
    els.previousState.textContent = step.state.previous_state || "--";
    els.commandedCourse.textContent = formatDeg(step.commanded_course_deg);
    els.criticalTarget.textContent = step.critical_target_mmsi || "--";
    els.timeValue.textContent = `${formatNumber(step.time_s, 0)} s`;

    els.cpaValue.textContent = critical ? formatMeters(critical.cpa_m) : "--";
    els.tcpaValue.textContent = critical ? formatSeconds(critical.tcpa_s) : "--";
    els.distanceValue.textContent = critical ? formatMeters(critical.distance_m) : "--";
    els.cogValue.textContent = formatDeg(step.ownship.cog_deg);

    els.encounterValue.textContent = critical?.encounter_name || "--";
    els.roleValue.textContent = critical?.ownship_role || "--";
    els.actionValue.textContent = decision?.action || "maintain_course";
    els.reasonValue.textContent = decision?.reason || critical?.reason || step.state.reason || "--";

    renderTargets(step);
    drawPlot(step);
}

function renderTargets(step) {
    const orderedTargets = [...step.targets].sort(
        (first, second) => (
            Number(first.priority ?? Infinity)
            - Number(second.priority ?? Infinity)
        )
    );

    if (!orderedTargets.length) {
        els.targetsTable.innerHTML = `
            <tr>
                <td colspan="5">
                    Sin contactos AIS activos
                </td>
            </tr>
        `;
        return;
    }

    els.targetsTable.innerHTML = orderedTargets
        .map((target) => {
            const isPriority = (
                target.mmsi === step.critical_target_mmsi
            );

            return `
                <tr class="${
                    isPriority
                        ? "priority-target-row"
                        : ""
                }">
                    <td>${target.mmsi}</td>

                    <td class="risk-${Boolean(target.risk)}">
                        ${target.risk ? "Sí" : "No"}
                    </td>

                    <td>${formatMeters(target.cpa_m)}</td>

                    <td>${formatSeconds(target.tcpa_s)}</td>

                    <td>
                        <span class="priority-badge">
                            ${target.priority}
                        </span>

                        ${
                            isPriority
                                ? `<span class="priority-label">
                                       Prioritario
                                   </span>`
                                : ""
                        }
                    </td>
                </tr>
            `;
        })
        .join("");
}

function drawPlot(step) {
    clearCanvas();

    const steps = state.result.steps.slice(0, state.frame + 1);

    const nominalPath = buildNominalPath(
        state.result.steps
    );

    const bounds = computeBounds(
        state.result.steps,
        nominalPath
    );

    const project = makeProjector(bounds);

    drawGrid(project, bounds);

    // Trayectoria nominal
    drawDashedPath(
        nominalPath.slice(0, state.frame + 1),
        "#6b7280",
        project
    );

    // Trayectoria ejecutada o evasiva
    drawPath(
        steps.map((item) => item.ownship),
        "#1f6feb",
        project
    );

    const targetSeries = new Map();
    for (const item of steps) {
        for (const target of item.targets) {
            if (!targetSeries.has(target.mmsi)) {
                targetSeries.set(target.mmsi, []);
            }
            targetSeries.get(target.mmsi).push(target);
        }
    }

    for (const series of targetSeries.values()) {
        drawPath(series, "#c83737", project);
    }

    const own = project(step.ownship.x_m, step.ownship.y_m);
    drawSafetyCircle(
        own,
        project.scale,
        state.result.config.safety_radius_m
    );
    drawVessel(own.x, own.y, step.ownship.cog_deg, "#1f6feb", "USV");

    for (const target of step.targets) {
        const point = project(target.x_m, target.y_m);
        drawVessel(point.x, point.y, target.cog_deg, target.risk ? "#c83737" : "#208a57", String(target.mmsi));
    }

    const maneuverStartStep = findManeuverStartStep();

    if (
        maneuverStartStep
        && maneuverStartStep.time_s <= step.time_s
    ) {
        const maneuverPoint = project(
            maneuverStartStep.ownship.x_m,
            maneuverStartStep.ownship.y_m
        );

        drawManeuverStart(
            maneuverPoint,
            maneuverStartStep.time_s
        );
    }
}

function buildNominalPath(steps) {
    if (!steps.length) {
        return [];
    }

    const initialStep = steps[0];
    const initialOwnship = initialStep.ownship;

    const initialX = Number(initialOwnship.x_m);
    const initialY = Number(initialOwnship.y_m);

    const speedMps = (
        Number(initialOwnship.sog_kn) * 0.514444
    );

    const courseRad = (
        Number(initialOwnship.cog_deg)
        * Math.PI
        / 180
    );

    const initialTime = Number(initialStep.time_s);

    return steps.map((step) => {
        const elapsedTime = (
            Number(step.time_s) - initialTime
        );

        return {
            x_m: (
                initialX
                + speedMps
                * Math.sin(courseRad)
                * elapsedTime
            ),
            y_m: (
                initialY
                + speedMps
                * Math.cos(courseRad)
                * elapsedTime
            ),
        };
    });
}

function computeBounds(steps, extraPoints = []) {
    const points = [];

    for (const step of steps) {
        points.push(step.ownship);
        for (const target of step.targets) {
            points.push(target);
        }
    }

    points.push(...extraPoints);

    const xs = points.map((point) => point.x_m);
    const ys = points.map((point) => point.y_m);
    let minX = Math.min(...xs);
    let maxX = Math.max(...xs);
    let minY = Math.min(...ys);
    let maxY = Math.max(...ys);

    const margin = 80;
    minX -= margin;
    maxX += margin;
    minY -= margin;
    maxY += margin;

    if (maxX - minX < 100) {
        minX -= 50;
        maxX += 50;
    }

    if (maxY - minY < 100) {
        minY -= 50;
        maxY += 50;
    }

    return { minX, maxX, minY, maxY };
}

function makeProjector(bounds) {
    const padding = 44;
    const width = els.canvas.width - padding * 2;
    const height = els.canvas.height - padding * 2;
    const spanX = bounds.maxX - bounds.minX;
    const spanY = bounds.maxY - bounds.minY;
    const scale = Math.min(width / spanX, height / spanY);
    const offsetX = (els.canvas.width - spanX * scale) / 2;
    const offsetY = (els.canvas.height - spanY * scale) / 2;

    const project = (x, y) => ({
        x: offsetX + (x - bounds.minX) * scale,
        y: els.canvas.height - (offsetY + (y - bounds.minY) * scale),
    });

    project.scale = scale;
    return project;
}

function drawGrid(project, bounds) {
    ctx.save();
    ctx.strokeStyle = "#e6edf3";
    ctx.lineWidth = 1;
    ctx.font = "12px Segoe UI";
    ctx.fillStyle = "#667789";

    const step = 100;
    const startX = Math.ceil(bounds.minX / step) * step;
    const startY = Math.ceil(bounds.minY / step) * step;

    for (let x = startX; x <= bounds.maxX; x += step) {
        const a = project(x, bounds.minY);
        const b = project(x, bounds.maxY);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
    }

    for (let y = startY; y <= bounds.maxY; y += step) {
        const a = project(bounds.minX, y);
        const b = project(bounds.maxX, y);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
    }

    ctx.fillText("N", 18, 24);
    ctx.restore();
}

function drawPath(points, color, project) {
    if (!points.length) {
        return;
    }

    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();

    points.forEach((point, index) => {
        const p = project(point.x_m, point.y_m);
        if (index === 0) {
            ctx.moveTo(p.x, p.y);
        } else {
            ctx.lineTo(p.x, p.y);
        }
    });

    ctx.stroke();
    ctx.restore();
}

function drawDashedPath(points, color, project) {
    if (!points.length) {
        return;
    }

    ctx.save();

    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.setLineDash([10, 7]);

    ctx.beginPath();

    points.forEach((point, index) => {
        const projected = project(
            point.x_m,
            point.y_m
        );

        if (index === 0) {
            ctx.moveTo(projected.x, projected.y);
        } else {
            ctx.lineTo(projected.x, projected.y);
        }
    });

    ctx.stroke();
    ctx.restore();
}

function drawSafetyCircle(center, scale, safetyRadiusM) {
    const radiusPixels = safetyRadiusM * scale;

    ctx.save();

    ctx.setLineDash([8, 6]);
    ctx.strokeStyle = "rgba(200, 55, 55, 0.8)";
    ctx.fillStyle = "rgba(200, 55, 55, 0.06)";
    ctx.lineWidth = 2;

    ctx.beginPath();
    ctx.arc(
        center.x,
        center.y,
        radiusPixels,
        0,
        Math.PI * 2
    );
    ctx.fill();
    ctx.stroke();

    ctx.setLineDash([]);
    ctx.fillStyle = "#7a2020";
    ctx.font = "12px Segoe UI";
    ctx.fillText(
        `Ds = ${safetyRadiusM.toFixed(0)} m`,
        center.x + radiusPixels + 6,
        center.y
    );

    ctx.restore();
}

function drawVessel(x, y, courseDeg, color, label) {
    const angle = (courseDeg || 0) * Math.PI / 180;
    const size = 16;

    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(0, -size);
    ctx.lineTo(size * .62, size);
    ctx.lineTo(0, size * .55);
    ctx.lineTo(-size * .62, size);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    ctx.save();
    ctx.fillStyle = "#17212b";
    ctx.font = "12px Segoe UI";
    ctx.fillText(label, x + 12, y - 12);
    ctx.restore();
}

function findManeuverStartStep() {
    if (!state.result?.steps?.length) {
        return null;
    }

    return state.result.steps.find((step, index, steps) => {
        const currentState = step.state?.current_state;
        const previousState = (
            index > 0
                ? steps[index - 1].state?.current_state
                : null
        );

        return (
            step.replanning?.trigger === "initial_plan"
            || (
                currentState === "AVOIDING_TARGET"
                && previousState !== "AVOIDING_TARGET"
            )
        );
    }) || null;
}

function drawManeuverStart(point, timeS) {
    ctx.save();

    ctx.fillStyle = "#d97706";
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;

    ctx.beginPath();
    ctx.arc(point.x, point.y, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#7c2d12";
    ctx.font = "12px Segoe UI";
    ctx.fillText(
        `Inicio maniobra: t = ${timeS.toFixed(0)} s`,
        point.x + 12,
        point.y - 10
    );

    ctx.restore();
}

function clearCanvas() {
    ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
}

function getCriticalTarget(step) {
    return step.targets.find((target) => target.mmsi === step.critical_target_mmsi)
        || step.targets[0]
        || null;
}

function togglePlayback() {
    if (state.timer) {
        stopPlayback();
        return;
    }

    els.playButton.textContent = "Pause";
    state.timer = window.setInterval(() => {
        if (!state.result) {
            stopPlayback();
            return;
        }

        state.frame += 1;

        if (state.frame >= state.result.steps.length) {
            state.frame = state.result.steps.length - 1;
            stopPlayback();
        }

        els.timeSlider.value = state.frame;
        render();
    }, 450);
}

function stopPlayback() {
    if (state.timer) {
        window.clearInterval(state.timer);
        state.timer = null;
    }
    els.playButton.textContent = "Play";
}

function reset() {
    stopPlayback();
    state.frame = 0;
    els.timeSlider.value = 0;
    render();
}

function setBusy(isBusy) {
    els.runButton.disabled = isBusy;
    els.runButton.textContent = isBusy ? "Ejecutando" : "Ejecutar";
}

function formatNumber(value, decimals = 1) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return "--";
    }
    return Number(value).toFixed(decimals);
}

function formatMeters(value) {
    return `${formatNumber(value, 1)} m`;
}

function formatSeconds(value) {
    return `${formatNumber(value, 1)} s`;
}

function formatDeg(value) {
    return `${formatNumber(value, 1)} deg`;
}

els.runButton.addEventListener("click", runScenario);
els.playButton.addEventListener("click", togglePlayback);
els.resetButton.addEventListener("click", reset);
els.timeSlider.addEventListener("input", (event) => {
    stopPlayback();
    state.frame = Number(event.target.value);
    render();
});

init();
