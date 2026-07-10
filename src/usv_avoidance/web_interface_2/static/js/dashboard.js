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

function render() {
    if (!state.result || !state.result.steps.length) {
        clearCanvas();
        return;
    }

    const step = state.result.steps[state.frame];
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
    if (!step.targets.length) {
        els.targetsTable.innerHTML = `<tr><td colspan="5">Sin blancos activos</td></tr>`;
        return;
    }

    els.targetsTable.innerHTML = step.targets
        .map((target) => `
            <tr>
                <td>${target.mmsi}</td>
                <td class="risk-${Boolean(target.risk)}">${target.risk ? "Si" : "No"}</td>
                <td>${formatMeters(target.cpa_m)}</td>
                <td>${formatSeconds(target.tcpa_s)}</td>
                <td>${target.priority}</td>
            </tr>
        `)
        .join("");
}

function drawPlot(step) {
    clearCanvas();

    const steps = state.result.steps.slice(0, state.frame + 1);
    const bounds = computeBounds(state.result.steps);
    const project = makeProjector(bounds);

    drawGrid(project, bounds);
    drawPath(steps.map((item) => item.ownship), "#1f6feb", project);

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
    drawSafetyCircle(own, bounds);
    drawVessel(own.x, own.y, step.ownship.cog_deg, "#1f6feb", "USV");

    for (const target of step.targets) {
        const point = project(target.x_m, target.y_m);
        drawVessel(point.x, point.y, target.cog_deg, target.risk ? "#c83737" : "#208a57", String(target.mmsi));
    }
}

function computeBounds(steps) {
    const points = [];

    for (const step of steps) {
        points.push(step.ownship);
        for (const target of step.targets) {
            points.push(target);
        }
    }

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

function drawSafetyCircle(center, bounds) {
    const radius = state.result.config.safety_radius_m * makeProjector(bounds).scale;
    ctx.save();
    ctx.strokeStyle = "rgba(200, 55, 55, .35)";
    ctx.fillStyle = "rgba(200, 55, 55, .06)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(center.x, center.y, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
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
