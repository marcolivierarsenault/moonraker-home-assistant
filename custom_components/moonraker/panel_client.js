const API = {
  data: printer => `moonraker/panel_data?printer=${encodeURIComponent(printer || "")}`,
  thumb: printer => `/api/moonraker/panel_thumbnail?printer=${encodeURIComponent(printer || "")}`,
  gcode: (printer, filename) => `/api/moonraker/panel_gcode?printer=${encodeURIComponent(printer || "")}&filename=${encodeURIComponent(filename || "")}`,
  action: "moonraker/panel_action",
  upload: "/api/moonraker/gcode_upload",
};

const SCREEN_TITLES = {
  dashboard: ["DEVICE / LIVE OVERVIEW", "Dashboard"],
  print: ["JOB CONTROL / PROGRESS", "Print Job"],
  movement: ["MOTION SYSTEM / CARTESIAN", "Movement"],
  thermal: ["HEATER CONTROL / TELEMETRY", "Temperatures"],
  extruder: ["MATERIAL FLOW / TOOLING", "Extruder"],
  bedmesh: ["BUILD PLATE / Z COMPENSATION", "Bed Mesh"],
  tuning: ["LIVE OVERRIDES / PROCESS", "Tuning"],
  macros: ["KLIPPER / AUTOMATION", "Macros"],
  files: ["STORAGE / SCHEDULE", "Files & Queue"],
  history: ["PRINT RECORD / TOTALS", "History"],
  camera: ["OPTICAL FEED / MONITORING", "Camera"],
  console: ["G-CODE / LIVE RESPONSE", "Console"],
  hardware: ["POWER / PRINTER HARDWARE", "Hardware"],
  system: ["HOST / FIRMWARE / SOFTWARE", "System"],
  network: ["ENDPOINT / CONNECTION HEALTH", "Network"],
  settings: ["INTEGRATION / DISPLAY", "Settings"],
  components: ["HOME ASSISTANT / MOONRAKER MAP", "Components"],
};

const MAX_TOOLPATH_SEGMENTS = 28000;
const MAX_TOOLPATH_BYTES = 128 * 1024 * 1024;
const AUTO_TOOLPATH_BYTES = 24 * 1024 * 1024;
const byId = id => document.getElementById(id);
const setText = (id, value) => { const element = byId(id); if (element) element.textContent = value; };

let printer = "";
let jogStep = 1;
let lastFiles = [];
let selectedFile = "";
let latestData = null;
let consoleSignature = "";
let lastThumbnailKey = "";
let thumbnailObjectUrl = null;
let toolpathKey = "";
let toolpathAbort = null;
let toolpathRequested = false;
let toolpathSegments = [];
let toolpathBounds = null;
let toolpathReady = false;
let toolpathLoading = false;
let toolpathError = "";
let extHist = [];
let bedHist = [];
let toolpathCamera = { yaw: -0.72, pitch: 0.7, zoom: 1, dragX: 0, dragY: 0, dragging: false };
const CAMERA_VIEWS = {
  iso: { yaw: -0.72, pitch: 0.7 },
  top: { yaw: 0, pitch: 0.035 },
  front: { yaw: 0, pitch: 1.5 },
  side: { yaw: Math.PI / 2, pitch: 1.5 },
};

function hassApi() {
  const api = window.hass;
  if (!api?.callApi || !api?.fetchWithAuth) {
    throw new Error("Open the console from the Home Assistant sidebar panel.");
  }
  return api;
}

function fmt(value, digits = 1) {
  return value == null || Number.isNaN(Number(value)) ? "—" : Number(value).toFixed(digits);
}

function duration(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return "—";
  seconds = Math.max(0, Math.floor(seconds));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return `${days ? `${days}d ` : ""}${hours ? `${hours}h ` : ""}${minutes}m ${remainder}s`;
}

function toast(message, milliseconds = 3200) {
  const element = byId("toast");
  element.textContent = message;
  element.style.display = "block";
  clearTimeout(element._timer);
  element._timer = setTimeout(() => { element.style.display = "none"; }, milliseconds);
}

function showScreen(name) {
  if (!SCREEN_TITLES[name]) return;
  document.querySelectorAll(".screen").forEach(screen => {
    screen.classList.toggle("active", screen.dataset.screen === name);
  });
  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.toggle("active", item.dataset.screenTarget === name);
  });
  setText("pageKicker", SCREEN_TITLES[name][0]);
  setText("screenTitle", SCREEN_TITLES[name][1]);
  if (name === "dashboard") requestAnimationFrame(drawToolpath);
}

async function refresh() {
  try {
    const data = await hassApi().callApi("GET", API.data(printer));
    if (data.error) {
      toast(data.error);
      return;
    }
    render(data);
  } catch (error) {
    if (error.message?.includes("Open the console")) toast(error.message);
  }
}

async function updateThumbnail(data) {
  const filename = (data.status?.print_stats || {}).filename || "";
  const key = `${data.entry_id}:${filename}:${data.meta?.thumbnails_path || ""}`;
  if (key === lastThumbnailKey) return;
  lastThumbnailKey = key;
  if (!filename || !data.meta?.thumbnails_path) return;
  try {
    const response = await hassApi().fetchWithAuth(API.thumb(data.entry_id));
    if (!response.ok) return;
    const blobUrl = URL.createObjectURL(await response.blob());
    if (thumbnailObjectUrl) URL.revokeObjectURL(thumbnailObjectUrl);
    thumbnailObjectUrl = blobUrl;
    const image = byId("thumb");
    if (image) image.src = blobUrl;
  } catch (_error) {
    // A missing thumbnail should not interrupt the rest of the panel.
  }
}

function drawTemperatureGraph(canvasId, extruderTarget, bedTarget) {
  const canvas = byId(canvasId);
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#030b08";
  context.fillRect(0, 0, width, height);
  const maximum = Math.max(60, ...extHist, ...bedHist, Number(extruderTarget) || 0, Number(bedTarget) || 0) * 1.12;
  context.strokeStyle = "rgba(41, 104, 70, .28)";
  context.lineWidth = 1;
  for (let row = 1; row < 4; row++) {
    const y = height * row / 4;
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }
  function line(values, color) {
    if (!values.length) return;
    context.beginPath();
    context.strokeStyle = color;
    context.lineWidth = 2;
    values.forEach((value, index) => {
      const x = index / Math.max(values.length - 1, 1) * width;
      const y = height - Number(value) / maximum * height;
      index ? context.lineTo(x, y) : context.moveTo(x, y);
    });
    context.stroke();
  }
  line(extHist, "#00ef91");
  line(bedHist, "#39e8bd");
  [[extruderTarget, "#00ef91"], [bedTarget, "#39e8bd"]].forEach(([target, color]) => {
    if (target == null) return;
    const y = height - Number(target) / maximum * height;
    context.beginPath();
    context.setLineDash([4, 4]);
    context.strokeStyle = color;
    context.globalAlpha = .45;
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
    context.setLineDash([]);
    context.globalAlpha = 1;
  });
  context.font = "10px monospace";
  context.fillStyle = "#9bffc7";
  context.fillText(`NOZZLE ${fmt(extHist.at(-1), 0)}°`, 8, 13);
  context.fillStyle = "#39e8bd";
  context.fillText(`BED ${fmt(bedHist.at(-1), 0)}°`, 102, 13);
}

function findNamedStatus(status, pattern) {
  return Object.entries(status || {}).find(([name, value]) => pattern.test(name) && value && typeof value === "object")?.[1] || {};
}

function render(data) {
  latestData = data;
  printer = data.entry_id || printer;
  const printerSelect = byId("printerSel");
  if (!printerSelect.options.length && data.entries) {
    data.entries.forEach(entry => {
      const option = document.createElement("option");
      option.value = entry.id;
      option.textContent = entry.name;
      printerSelect.appendChild(option);
    });
    printerSelect.value = printer;
  }
  setText("sidePrinter", data.printer || "—");
  setText("linkStatus", data.available ? "CONNECTED" : "OFFLINE");
  setText("clock", new Date().toLocaleTimeString([], { hour12: false }));

  const status = data.status || {};
  const meta = data.meta || {};
  const printStats = status.print_stats || {};
  const displayStatus = status.display_status || {};
  const virtualSdcard = status.virtual_sdcard || {};
  const extruder = status.extruder || {};
  const bed = status.heater_bed || {};
  const fan = status.fan || {};
  const gcodeMove = status.gcode_move || {};
  const toolhead = status.toolhead || {};
  const printState = (printStats.state || "unknown").toUpperCase();
  const progress = getLiveProgress(data);
  const position = toolhead.position || [];

  const stateChip = byId("stateChip");
  stateChip.innerHTML = "";
  const stateLed = document.createElement("i");
  stateLed.className = "led";
  stateChip.append(stateLed, document.createTextNode(data.available ? printState : "OFFLINE"));
  stateChip.classList.toggle("bad", !data.available);
  setText("klippyChip", `KLIPPY ${(data.printer_info || {}).klippy_state || "—"}`);
  setText("tickerText", `${data.printer} // ${printState} // FILE ${printStats.filename || "NONE"} // ${(progress * 100).toFixed(1)}% // NOZZLE ${fmt(extruder.temperature, 0)}°C // BED ${fmt(bed.temperature, 0)}°C`);

  const ring = byId("ringFg");
  ring.style.strokeDashoffset = 320.44 * (1 - Math.min(progress, 1));
  setText("pct", `${(progress * 100).toFixed(0)}%`);
  setText("fname", printStats.filename || "NO ACTIVE G-CODE");
  const remaining = Math.max(0, (meta.estimated_time || 0) - (printStats.print_duration || 0));
  setText("eta", `ETA ${duration(remaining)}`);
  setText("elapsed", duration(printStats.print_duration));
  setText("remaining", duration(remaining));
  setText("totalEst", duration(printStats.total_duration));
  setText("slicerEst", duration(meta.estimated_time));
  setText("filUsed", `${fmt((printStats.filament_used || 0) / 1000, 2)} m`);
  setText("filEst", `${fmt((meta.filament_total || 0) / 1000, 2)} m`);
  const currentLayer = printStats.info?.current_layer ?? virtualSdcard.current_layer ?? "—";
  const totalLayers = printStats.info?.total_layer ?? virtualSdcard.total_layer ?? meta.layer_count;
  const layerLabel = currentLayer === "—" ? "—" : `${currentLayer}${totalLayers ? ` / ${totalLayers}` : ""}`;
  setText("layer", layerLabel);
  const layerFraction = Number(currentLayer) > 0 && Number(totalLayers) > 0 ? Number(currentLayer) / Number(totalLayers) : progress;
  byId("layerBar").style.width = `${Math.min(layerFraction * 100, 100)}%`;
  setText("zpos", `${fmt(position[2], 2)} mm`);
  setText("dashboardState", printState);
  setText("dashboardAvailability", data.available ? "STREAMING" : "UNAVAILABLE");
  setText("printPageState", printState);
  setText("printPageFile", printStats.filename || "NO ACTIVE G-CODE");
  byId("printProgressBar").style.width = `${Math.min(progress * 100, 100)}%`;
  setText("printProgressText", `${(progress * 100).toFixed(1)}%`);
  setText("printPageEta", `ETA ${duration(remaining)}`);
  setText("printElapsed", duration(printStats.print_duration));
  setText("printRemaining", duration(remaining));
  setText("printLayer", layerLabel);
  setText("printHeight", `${fmt(meta.layer_height, 2)} mm`);
  setText("printFilament", `${fmt((printStats.filament_used || 0) / 1000, 2)} m`);
  setText("printEstimate", duration(meta.estimated_time));
  setText("printMetaEstimate", duration(meta.estimated_time));
  setText("printMetaFilament", `${fmt((meta.filament_total || 0) / 1000, 2)} m`);
  setText("printMetaObjectHeight", `${fmt(meta.object_height, 2)} mm`);
  setText("printMetaLayerCount", meta.layer_count ?? "—");
  setText("printToolpathStatus", toolpathReady ? "INTERACTIVE TOOLPATH READY / DASHBOARD VIEW" : "PREVIEW LOADS FROM ACTIVE G-CODE ON DASHBOARD");
  setText("tuneProgress", `${(progress * 100).toFixed(1)}%`);
  setText("tuneEta", `ETA ${duration(remaining)}`);
  byId("tuneProgressBar").style.width = `${Math.min(progress * 100, 100)}%`;

  setText("dashNozzle", `${fmt(extruder.temperature, 0)}°C`);
  setText("dashNozzleTarget", `${fmt(extruder.target, 0)}°C`);
  byId("extBar").style.width = `${Math.min((extruder.temperature || 0) / 300 * 100, 100)}%`;
  setText("extNow", `${fmt(extruder.temperature, 0)}°C / ${fmt(extruder.target, 0)}°C`);
  setText("extBarT", `${fmt(extruder.temperature, 0)} / ${fmt(extruder.target, 0)}°C`);
  setText("dashBed", `${fmt(bed.temperature, 0)}°C`);
  setText("dashBedTarget", `${fmt(bed.target, 0)}°C`);
  byId("bedBar").style.width = `${Math.min((bed.temperature || 0) / 130 * 100, 100)}%`;
  setText("bedNow", `${fmt(bed.temperature, 0)}°C / ${fmt(bed.target, 0)}°C`);
  setText("bedBarT", `${fmt(bed.temperature, 0)} / ${fmt(bed.target, 0)}°C`);
  if (document.activeElement !== byId("extTarget")) byId("extTarget").value = extruder.target == null ? "" : Math.round(extruder.target);
  if (document.activeElement !== byId("bedTarget")) byId("bedTarget").value = bed.target == null ? "" : Math.round(bed.target);

  const chamber = findNamedStatus(status, /chamber|enclosure/i);
  setText("dashChamber", chamber.temperature == null ? "—" : `${fmt(chamber.temperature, 0)}°C`);
  setText("dashHumidity", chamber.humidity == null ? "SENSOR / NOT REPORTED" : `HUMIDITY ${fmt(chamber.humidity, 0)}%`);
  setText("dashSpeed", `${Math.round((gcodeMove.speed_factor || 0) * 100)}%`);
  setText("dashFlow", `${Math.round((gcodeMove.extrude_factor || 0) * 100)}%`);
  setText("dashFan", `${Math.round((fan.speed || 0) * 100)}%`);
  if (document.activeElement !== byId("speed")) byId("speed").value = Math.round((gcodeMove.speed_factor || 0) * 100);
  if (document.activeElement !== byId("flow")) byId("flow").value = Math.round((gcodeMove.extrude_factor || 0) * 100);
  if (document.activeElement !== byId("fan")) byId("fan").value = Math.round((fan.speed || 0) * 100);
  setText("speedVal", `${Math.round((gcodeMove.speed_factor || 0) * 100)}%`);
  setText("flowVal", `${Math.round((gcodeMove.extrude_factor || 0) * 100)}%`);
  setText("fanVal", `${Math.round((fan.speed || 0) * 100)}%`);
  setText("speedFactor", `${Math.round((gcodeMove.speed_factor || 0) * 100)}%`);
  setText("flowFactor", `${Math.round((gcodeMove.extrude_factor || 0) * 100)}%`);
  setText("fanNow", `${Math.round((fan.speed || 0) * 100)}%`);
  setText("tuneSpeedFactor", `${Math.round((gcodeMove.speed_factor || 0) * 100)}%`);
  setText("tuneFlowFactor", `${Math.round((gcodeMove.extrude_factor || 0) * 100)}%`);
  setText("tuneMoveSpeed", `${fmt(gcodeMove.speed, 0)} mm/s`);
  setText("tuneState", printState);

  setText("posX", fmt(position[0], 2));
  setText("posY", fmt(position[1], 2));
  setText("posZ", fmt(position[2], 2));
  setText("posE", fmt(position[3], 2));
  setText("movePosX", fmt(position[0], 2));
  setText("movePosY", fmt(position[1], 2));
  setText("movePosZ", fmt(position[2], 2));
  setText("movePosE", fmt(position[3], 2));
  setText("moveSpeed", `${fmt(gcodeMove.speed, 0)} mm/s`);
  setText("moveSpeedDetail", `${fmt(gcodeMove.speed, 0)} mm/s`);
  setText("printTime", duration(toolhead.print_time));
  setText("stateMsg", printStats.message || displayStatus.message || "—");
  setText("moveStepValue", `${jogStep}`);
  setText("consoleFile", printStats.filename || "—");
  setText("consoleProgress", `${(progress * 100).toFixed(1)}%`);
  setText("consoleX", fmt(position[0], 2));
  setText("consoleY", fmt(position[1], 2));
  setText("consoleZ", fmt(position[2], 2));
  setText("consoleLayer", layerLabel);

  setText("extrusionFilUsed", `${fmt((printStats.filament_used || 0) / 1000, 2)} m`);
  setText("extrusionFilEst", `${fmt((meta.filament_total || 0) / 1000, 2)} m`);
  setText("extrusionLayer", layerLabel);
  setText("extrusionNozzle", `${fmt(extruder.temperature, 1)}°C`);
  setText("extrusionTarget", `${fmt(extruder.target, 1)}°C`);
  setText("extrusionPosition", `${fmt(position[3], 2)} mm`);
  setText("extrusionSpeed", `${fmt(gcodeMove.speed, 0)} mm/s`);
  setText("extrusionSpeedFactor", `${Math.round((gcodeMove.speed_factor || 0) * 100)}%`);
  setText("extrusionFlowFactor", `${Math.round((gcodeMove.extrude_factor || 0) * 100)}%`);
  setText("extrusionTemp", `${fmt(extruder.temperature, 0)}°C`);
  setText("extrusionFan", `${Math.round((fan.speed || 0) * 100)}%`);
  setText("bedzPosition", `${fmt(position[2], 2)} mm`);
  setText("bedLayer", layerLabel);
  setText("bedLayerHeight", `${fmt(meta.layer_height, 2)} mm`);
  setText("bedTempZ", `${fmt(bed.temperature, 0)}°C`);
  setText("networkState", data.available ? "CONNECTED" : "OFFLINE");
  setText("networkMoonraker", data.available ? "ONLINE" : "UNAVAILABLE");
  setText("networkKlippy", (data.printer_info || {}).klippy_state || "—");
  setText("networkPush", "WEBSOCKET / FALLBACK POLL");
  setText("networkCameras", String((data.webcams || []).length));
  renderSettings(data);
  renderSystem(data, status, printState);
  renderComponents(data);
  renderBedMesh(status);
  renderHardware(status);
  renderVersions(data);

  lastFiles = data.files || [];
  selectedFile = data.selected_file || byId("fileSel").value;
  renderFiles();
  renderQueue(data.queue || {});
  renderPower(data.power_devices || []);
  renderMacros(data.macros || []);
  renderHistory(data);
  renderCamera(data.webcams || []);
  renderConsole(data.gcode_responses || []);
  updateThumbnail(data);
  updateToolpath(data, progress);
  drawTemperatureGraph("tempGraph", extruder.target, bed.target);
  drawTemperatureGraph("tempGraphHistory", extruder.target, bed.target);
}

function renderSettings(data) {
  const settings = data.settings || {};
  setText("settingName", data.printer || "—");
  setText("settingHost", settings.host || "—");
  setText("settingPort", settings.port ?? "—");
  setText("settingTls", settings.tls ? "ENABLED" : "DISABLED");
  setText("settingIdlePoll", settings.idle_poll_seconds == null ? "—" : `${settings.idle_poll_seconds}s`);
  setText("settingPrintPoll", settings.print_poll_seconds == null ? "—" : `${settings.print_poll_seconds}s`);
  setText("settingQuiet", settings.quiet_unreachable ? "ENABLED" : "DISABLED");
  setText("settingVersion", data.integration_version || "—");
  setText("networkHost", settings.host || "—");
  setText("networkPort", settings.port ?? "—");
  setText("networkTls", settings.tls ? "ENABLED" : "DISABLED");
  setText("networkApiKey", data.api_key_configured ? "CONFIGURED / VALUE HIDDEN" : "NOT CONFIGURED");
}

function renderSystem(data, status, printState) {
  const printerInfo = data.printer_info || {};
  const systemInfo = data.system_info || {};
  const cpu = systemInfo.cpu_info || {};
  const versions = (data.machine_update || {}).version_info || {};
  const klipper = versions.klipper || {};
  const moonraker = versions.moonraker || {};
  const hostTemp = findNamedStatus(status, /temperature_host|host_temperature|temperature_sensor.*(host|rpi)/i);
  setText("sysPrinterState", printState);
  setText("sysKlippy", printerInfo.klippy_state || "—");
  setText("sysKlipperVersion", klipper.version || klipper.current_version || printerInfo.software_version || "—");
  setText("sysMoonrakerVersion", moonraker.version || moonraker.current_version || data.server_info?.moonraker_version || "—");
  setText("sysCpu", cpu.cpu_desc || cpu.model || cpu.processor || "—");
  setText("sysHostTemp", hostTemp.temperature == null ? "—" : `${fmt(hostTemp.temperature, 1)}°C`);
  const live = byId("systemLive");
  live.textContent = data.available ? "ONLINE" : "OFFLINE";
  live.classList.toggle("bad-text", !data.available);
  setText("dashboardSystemLive", data.available ? "ONLINE" : "OFFLINE");
}

function renderComponents(data) {
  const platforms = data.platforms || [];
  setText("componentCount", String(platforms.length));
  const platformList = byId("platformList");
  platformList.replaceChildren();
  platforms.forEach(platform => appendObjectRow(platformList, platform, "LOADED"));
  if (!platforms.length) appendEmpty(platformList, "NO PLATFORMS REPORTED");

  const objects = data.tracked_objects || [];
  setText("objectCount", `${objects.length} OBJECTS`);
  const objectList = byId("objectList");
  objectList.replaceChildren();
  objects.forEach(object => appendObjectRow(objectList, object.name, object.fields == null ? "ALL FIELDS" : object.fields.join(", ")));
  if (!objects.length) appendEmpty(objectList, "NO SUBSCRIBED OBJECTS");
}

function appendObjectRow(parent, name, detail) {
  const row = document.createElement("div");
  row.className = "object-row";
  const key = document.createElement("span");
  key.textContent = String(name);
  const value = document.createElement("span");
  value.textContent = String(detail);
  row.append(key, value);
  parent.appendChild(row);
}

function appendEmpty(parent, text) {
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.textContent = text;
  parent.appendChild(empty);
}

function renderBedMesh(status) {
  const mesh = status.bed_mesh || {};
  const matrix = mesh.mesh_matrix || mesh.probed_matrix || [];
  const profile = mesh.profile_name || mesh.profile || "NO PROFILE";
  setText("meshProfile", String(profile).toUpperCase());
  const container = byId("bedMeshMap");
  container.replaceChildren();
  if (Array.isArray(matrix) && matrix.length && Array.isArray(matrix[0])) {
    const values = matrix.flat().map(Number).filter(Number.isFinite);
    const min = Math.min(...values);
    const max = Math.max(...values);
    container.style.gridTemplateColumns = `repeat(${matrix[0].length}, minmax(0, 1fr))`;
    matrix.forEach(row => row.forEach(value => {
      const cell = document.createElement("div");
      const numeric = Number(value);
      const ratio = max === min ? .15 : (numeric - min) / (max - min);
      cell.className = "mesh-cell";
      cell.style.background = `rgba(0,239,145,${.04 + ratio * .22})`;
      cell.textContent = Number.isFinite(numeric) ? numeric.toFixed(3) : "—";
      container.appendChild(cell);
    }));
    const minPoint = (mesh.mesh_min || []).join(", ");
    const maxPoint = (mesh.mesh_max || []).join(", ");
    setText("meshBounds", `PROBED ${matrix.length} × ${matrix[0].length} / MIN ${minPoint || "—"} / MAX ${maxPoint || "—"}`);
  } else {
    container.style.gridTemplateColumns = "1fr";
    appendEmpty(container, "BED MESH MATRIX NOT REPORTED BY PRINTER");
    setText("meshBounds", "Klipper bed_mesh must be configured and probed to show a height map.");
  }
}

function renderHardware(status) {
  const hardwareRows = Object.entries(status).filter(([name, value]) =>
    /mcu|stepper|heater|fan|probe|temperature|bed_mesh/i.test(name) && value && typeof value === "object",
  );
  const container = byId("hardwareTable");
  container.replaceChildren();
  hardwareRows.forEach(([name, values]) => {
    const summary = Object.entries(values)
      .filter(([key]) => /temperature|target|speed|value|position|status|state|offset|current/i.test(key))
      .slice(0, 7)
      .map(([key, value]) => `${key}:${Array.isArray(value) ? value.join(",") : value}`)
      .join(" / ") || "STATUS AVAILABLE";
    appendObjectRow(container, name, summary);
  });
  if (!hardwareRows.length) appendEmpty(container, "NO OPTIONAL HARDWARE SENSORS REPORTED");
}

function renderVersions(data) {
  const versions = (data.machine_update || {}).version_info || {};
  const container = byId("versionList");
  container.replaceChildren();
  Object.entries(versions).forEach(([name, version]) => {
    const current = version.version || version.current_version || "—";
    const detail = version.remote_version
      ? `${current} → ${version.remote_version}`
      : current;
    appendObjectRow(container, name, detail);
  });
  if (!Object.keys(versions).length) appendEmpty(container, "UPDATE STATUS NOT AVAILABLE");
}

function renderHistory(data) {
  const totals = (data.history || {}).job_totals || {};
  setText("totJobs", totals.total_jobs ?? "—");
  setText("totPrint", duration(totals.total_print_time ?? totals.total_time));
  setText("totFil", `${fmt((totals.total_filament_used || 0) / 1000, 1)} m`);
  setText("longJob", duration(totals.longest_print));
  const spool = data.spoolman || {};
  const spoolLabel = spool.spool_id != null ? `SPOOL #${spool.spool_id}` : "—";
  setText("spool", spoolLabel);
  setText("extrusionSpool", spoolLabel);
  const versions = (data.machine_update || {}).version_info || {};
  const pending = Object.values(versions).filter(version => {
    const current = version?.version || version?.current_version;
    return current && version?.remote_version && current !== version.remote_version;
  }).length;
  setText("updates", Object.keys(versions).length ? `${pending} PENDING` : "—");
}

function renderQueue(queue) {
  setText("queueState", `QUEUE ${queue.queue_state || "—"}`);
  const container = byId("queueList");
  container.replaceChildren();
  const jobs = queue.queued_jobs || [];
  jobs.forEach((job, index) => appendObjectRow(container, `${String(index + 1).padStart(2, "0")} / ${job.filename || job}`, job.job_id || job.status || "QUEUED"));
  if (!jobs.length) appendEmpty(container, "QUEUE EMPTY");
}

function renderFiles() {
  const select = byId("fileSel");
  const filter = (byId("fileSearch").value || "").toLowerCase();
  const visibleFiles = lastFiles.filter(file => !filter || file.path.toLowerCase().includes(filter));
  select.replaceChildren();
  const list = byId("fileList");
  list.replaceChildren();
  if (!visibleFiles.length) {
    appendEmpty(list, filter ? "NO MATCHING FILES" : "NO G-CODE FILES FOUND");
    return;
  }
  visibleFiles.forEach(file => {
    const option = document.createElement("option");
    option.value = file.path;
    option.textContent = file.path;
    select.appendChild(option);
    const item = document.createElement("button");
    item.type = "button";
    item.className = `file-option${file.path === selectedFile ? " selected" : ""}`;
    item.dataset.fileOption = file.path;
    const name = document.createElement("span");
    name.textContent = file.path;
    const size = document.createElement("span");
    size.textContent = file.size ? `${(Number(file.size) / 1048576).toFixed(1)} MB` : "GCODE";
    item.append(name, size);
    list.appendChild(item);
  });
  select.value = selectedFile;
}

function renderPower(devices) {
  const containers = [byId("powerRow")];
  containers.forEach(container => {
    container.replaceChildren();
    if (!devices.length) {
      appendEmpty(container, "NO POWER DEVICES REPORTED");
      return;
    }
    devices.forEach(device => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `power-toggle${device.status === "on" ? " is-active" : ""}`;
      button.dataset.action = "power";
      button.dataset.device = device.device;
      button.dataset.powerAction = device.status === "on" ? "off" : "on";
      button.textContent = `${device.status === "on" ? "POWER ON" : "POWER OFF"} / ${device.device}`;
      container.appendChild(button);
    });
  });
}

function renderMacros(macros) {
  const buttons = macros.map((macro, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.action = "run_macro";
    button.dataset.script = macro;
    button.dataset.confirm = `Run macro ${macro}?`;
    button.textContent = macro.replace(/_/g, " ").toUpperCase();
    const caption = document.createElement("span");
    caption.textContent = `KLIPPER MACRO / ${String(index + 1).padStart(2, "0")}`;
    button.appendChild(caption);
    return button;
  });
  const full = byId("macroRow");
  full.replaceChildren(...(buttons.length ? buttons : [emptyElement("NO MACROS DISCOVERED")]));
  setText("macroCount", `${macros.length} MACROS`);
  const dashboard = byId("dashboardMacros");
  dashboard.replaceChildren(...(buttons.length ? buttons.slice(0, 6).map(button => button.cloneNode(true)) : [emptyElement("NO MACROS REPORTED") ]));
}

function emptyElement(text) {
  const element = document.createElement("span");
  element.className = "empty-state";
  element.textContent = text;
  return element;
}

function renderCamera(webcams) {
  const camera = webcams[0];
  const images = [byId("webcam"), byId("webcamLarge")];
  const available = Boolean(camera?.stream_url);
  byId("cameraEmpty").style.display = available ? "none" : "grid";
  images.forEach(image => {
    image.style.display = available ? "block" : "none";
    if (available && (!image.src || !image.src.startsWith(camera.stream_url))) image.src = camera.stream_url;
  });
  setText("cameraName", camera?.name ? `SOURCE / ${camera.name}` : "CAMERA SOURCE NOT CONFIGURED");
  setText("networkCameras", String(webcams.length));
}

function renderConsole(lines) {
  const signature = lines.join("\n");
  if (signature === consoleSignature) return;
  const output = byId("console");
  output.textContent = signature;
  output.scrollTop = output.scrollHeight;
  consoleSignature = signature;
}

async function act(action, value, preset, extra) {
  const body = { entry_id: printer, action };
  if (["set_speed", "set_flow", "set_fan", "set_extruder", "set_bed", "z_adjust", "z_set"].includes(action)) {
    if (value === "" || value == null || Number.isNaN(Number(value))) {
      toast("Enter a valid numeric value.");
      return;
    }
    body.value = Number(value);
  }
  if (preset) body.preset = preset;
  if (["print_file", "select_file", "enqueue_file", "delete_file"].includes(action)) body.filename = value;
  if (extra) Object.assign(body, extra);
  try {
    const result = await hassApi().callApi("POST", API.action, body);
    toast(result.ok ? `COMMAND OK / ${action.toUpperCase()}` : `COMMAND ERROR / ${result.error || action}`);
    refresh();
  } catch (error) {
    toast(`COMMAND ERROR / ${error.message || "request failed"}`);
  }
}

function dispatchAction(button) {
  const action = button.dataset.action;
  if (!action) return;
  if (button.dataset.confirm && !confirm(button.dataset.confirm)) return;
  let value = button.dataset.value;
  const preset = button.dataset.preset;
  const extra = {};
  if (button.dataset.valueFrom) {
    value = byId(button.dataset.valueFrom)?.value;
    if (value == null || value === "") {
      toast("ENTER A VALUE FIRST");
      return;
    }
  }
  if (button.hasAttribute("data-file-select")) value = byId("fileSel").value;
  if (button.dataset.script) extra.script = button.dataset.script;
  if (button.dataset.device) extra.device = button.dataset.device;
  if (button.dataset.powerAction) extra.power_action = button.dataset.powerAction;
  if (action === "jog") {
    extra.axis = button.dataset.axis;
    extra.dist = Number(button.dataset.dir) * jogStep;
  }
  if (action === "set_fan" && button.dataset.scale === "fan-percent") value = Math.round(Number(value) * 2.55);
  if (["print_file", "enqueue_file", "delete_file"].includes(action) && !value) {
    toast("SELECT A G-CODE FILE FIRST");
    return;
  }
  act(action, value, preset, extra);
}

async function uploadFile(event) {
  event.preventDefault();
  const file = byId("upFile").files[0];
  if (!file) return false;
  const form = new FormData();
  form.append("printer", printer);
  form.append("file", file);
  if (byId("upPrint").checked) form.append("start_print", "1");
  try {
    const response = await hassApi().fetchWithAuth(API.upload, { method: "POST", body: form });
    const result = await response.json().catch(() => ({}));
    toast(response.ok ? `UPLOAD OK / ${result.filename || file.name}` : `UPLOAD ERROR / ${result.error || response.status}`);
    if (response.ok) byId("upFile").value = "";
    setTimeout(refresh, 800);
  } catch (error) {
    toast(`UPLOAD ERROR / ${error.message || "request failed"}`);
  }
  return false;
}

function sendGcode(event) {
  if (event) event.preventDefault();
  const input = byId("gcodeIn");
  const script = input.value.trim();
  if (!script) return;
  input.value = "";
  act("run_gcode", null, null, { script });
}

function switchPrinter() {
  printer = byId("printerSel").value;
  latestData = null;
  selectedFile = "";
  lastThumbnailKey = "";
  toolpathKey = "";
  toolpathReady = false;
  toolpathLoading = false;
  toolpathRequested = false;
  toolpathSegments = [];
  if (toolpathAbort) toolpathAbort.abort();
  extHist = [];
  bedHist = [];
  renderToolpathStatus("WAITING FOR PRINTER DATA");
  refresh();
}

function setScreen(name) {
  if (!SCREEN_TITLES[name]) return;
  document.querySelectorAll(".screen").forEach(screen => screen.classList.toggle("active", screen.dataset.screen === name));
  document.querySelectorAll(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.screenTarget === name));
  setText("pageKicker", SCREEN_TITLES[name][0]);
  setText("screenTitle", SCREEN_TITLES[name][1]);
  if (name === "dashboard") requestAnimationFrame(drawToolpath);
}

function setJogStep(button) {
  jogStep = Number(button.dataset.jogStep) || 1;
  document.querySelectorAll("[data-jog-step]").forEach(item => item.classList.toggle("is-active", item.dataset.jogStep === button.dataset.jogStep));
  setText("moveStepValue", String(jogStep));
}

function setToolpathView(view) {
  const preset = CAMERA_VIEWS[view];
  if (!preset) return;
  toolpathCamera.yaw = preset.yaw;
  toolpathCamera.pitch = preset.pitch;
  document.querySelectorAll("[data-toolpath-view]").forEach(button => button.classList.toggle("is-active", button.dataset.toolpathView === view));
  drawToolpath();
}

function bindInteractions() {
  document.addEventListener("click", event => {
    const nav = event.target.closest("[data-screen-target]");
    if (nav) {
      setScreen(nav.dataset.screenTarget);
      return;
    }
    const view = event.target.closest("[data-toolpath-view]");
    if (view) {
      setToolpathView(view.dataset.toolpathView);
      return;
    }
    if (event.target.closest("[data-toolpath-reset]")) {
      setToolpathView("iso");
      toolpathCamera.zoom = 1;
      drawToolpath();
      return;
    }
    if (event.target.closest("[data-toolpath-load]")) {
      requestToolpath();
      return;
    }
    const step = event.target.closest("[data-jog-step]");
    if (step) {
      setJogStep(step);
      return;
    }
    if (event.target.closest("[data-camera-fullscreen]")) {
      const image = byId("webcamLarge").style.display !== "none" ? byId("webcamLarge") : byId("webcam");
      if (image.requestFullscreen) image.requestFullscreen();
      return;
    }
    const fileOption = event.target.closest("[data-file-option]");
    if (fileOption) {
      selectedFile = fileOption.dataset.fileOption;
      byId("fileSel").value = selectedFile;
      renderFiles();
      act("select_file", selectedFile);
      return;
    }
    const action = event.target.closest("[data-action]");
    if (action) dispatchAction(action);
  });

  document.addEventListener("change", event => {
    const target = event.target;
    if (target.id === "printerSel") switchPrinter();
    if (target.id === "fileSel") {
      selectedFile = target.value;
      act("select_file", selectedFile);
    }
    if (target.id === "speed") act("set_speed", target.value);
    if (target.id === "flow") act("set_flow", target.value);
    if (target.id === "fan") act("set_fan", Math.round(Number(target.value) * 2.55));
    if (target.id === "showFuturePath") drawToolpath();
  });

  document.addEventListener("input", event => {
    const target = event.target;
    if (target.id === "fileSearch") renderFiles();
    if (["speed", "flow", "fan"].includes(target.id)) {
      const label = byId(`${target.id}Val`);
      if (label) label.textContent = `${Math.round(Number(target.value))}%`;
    }
  });

  document.addEventListener("submit", event => {
    if (event.target.id === "upForm") uploadFile(event);
    if (event.target.id === "gcodeForm") sendGcode(event);
  });
}

function parseGcodeLine(line, state, fraction, stride) {
  let clean = line.replace(/\([^)]*\)/g, "").split(";")[0].trim().toUpperCase();
  clean = clean.replace(/^N\d+\s*/, "");
  if (!clean) return null;
  if (/\bG90\b/.test(clean)) state.xyzAbsolute = true;
  if (/\bG91\b/.test(clean)) state.xyzAbsolute = false;
  if (/\bM82\b/.test(clean)) state.eAbsolute = true;
  if (/\bM83\b/.test(clean)) state.eAbsolute = false;
  if (/\bG20\b/.test(clean)) state.unit = 25.4;
  if (/\bG21\b/.test(clean)) state.unit = 1;

  const words = {};
  for (const match of clean.matchAll(/([XYZEF])\s*(-?(?:\d+\.?\d*|\.\d+))/g)) words[match[1]] = Number(match[2]);
  if (/\bG92\b/.test(clean)) {
    for (const axis of ["X", "Y", "Z"]) if (words[axis] != null) state.position[axis.toLowerCase()] = words[axis] * state.unit;
    if (words.E != null) state.position.e = words.E * state.unit;
    return null;
  }
  const command = clean.match(/(?:^|\s)(G0?0|G0?1|G0?2|G0?3)\b/);
  if (!command) return null;

  const previous = { ...state.position };
  const next = { ...state.position };
  for (const axis of ["X", "Y", "Z"]) {
    const key = axis.toLowerCase();
    if (words[axis] != null) next[key] = state.xyzAbsolute ? words[axis] * state.unit : previous[key] + words[axis] * state.unit;
  }
  let extrusionDelta = 0;
  if (words.E != null) {
    const extrusion = words.E * state.unit;
    next.e = state.eAbsolute ? extrusion : previous.e + extrusion;
    extrusionDelta = state.eAbsolute ? next.e - previous.e : extrusion;
  }
  state.position = next;
  const distance = Math.hypot(next.x - previous.x, next.y - previous.y, next.z - previous.z);
  if (extrusionDelta <= 0.0005 || distance <= 0.0001) return null;
  state.extrusions += 1;
  if (state.extrusions % stride !== 0) return null;
  return { a: [previous.x, previous.y, previous.z], b: [next.x, next.y, next.z], fraction };
}

function beginToolpathLoad(data, filename, key) {
  if (toolpathLoading || toolpathReady) return;
  toolpathLoading = true;
  const button = byId("toolpathLoadButton");
  button.disabled = true;
  button.textContent = "PARSING G-CODE";
  toolpathAbort = new AbortController();
  loadToolpath(data, filename, key, toolpathAbort.signal).finally(() => {
    if (key !== toolpathKey) return;
    toolpathLoading = false;
    button.disabled = toolpathReady;
    button.textContent = toolpathReady ? "PATH READY" : "LOAD TOOLPATH";
  });
}

function requestToolpath() {
  const data = latestData;
  const status = data?.status || {};
  const filename = status.print_stats?.filename || status.virtual_sdcard?.file_path || "";
  if (!data || !filename) {
    toast("NO ACTIVE G-CODE FILE");
    return;
  }
  const fileSize = Number(status.virtual_sdcard?.file_size) || 0;
  if (fileSize > MAX_TOOLPATH_BYTES) {
    toast("G-CODE FILE EXCEEDS THE 128 MB PREVIEW LIMIT");
    return;
  }
  toolpathRequested = true;
  toolpathError = "";
  beginToolpathLoad(data, filename, `${data.entry_id}:${filename}`);
}

async function updateToolpath(data) {
  const status = data.status || {};
  const printStats = status.print_stats || {};
  const virtualSdcard = status.virtual_sdcard || {};
  const filename = printStats.filename || virtualSdcard.file_path || "";
  const key = `${data.entry_id}:${filename}`;
  if (!filename) {
    if (toolpathAbort) toolpathAbort.abort();
    toolpathKey = "";
    toolpathReady = false;
    toolpathLoading = false;
    toolpathRequested = false;
    toolpathSegments = [];
    toolpathBounds = null;
    const button = byId("toolpathLoadButton");
    button.disabled = true;
    button.textContent = "LOAD TOOLPATH";
    renderToolpathStatus("WAITING FOR ACTIVE G-CODE");
    drawToolpath();
    return;
  }
  if (key !== toolpathKey) {
    if (toolpathAbort) toolpathAbort.abort();
    toolpathKey = key;
    toolpathReady = false;
    toolpathLoading = false;
    toolpathError = "";
    toolpathSegments = [];
    toolpathBounds = null;
    const fileSize = Number(virtualSdcard.file_size) || 0;
    toolpathRequested = fileSize > 0 && fileSize <= AUTO_TOOLPATH_BYTES;
    const button = byId("toolpathLoadButton");
    button.disabled = fileSize > MAX_TOOLPATH_BYTES;
    button.textContent = fileSize > MAX_TOOLPATH_BYTES
      ? "FILE TOO LARGE"
      : toolpathRequested ? "LOAD TOOLPATH" : "LOAD 3D PREVIEW";
    if (!toolpathRequested) {
      renderToolpathStatus(fileSize > MAX_TOOLPATH_BYTES
        ? "FILE EXCEEDS 128 MB PREVIEW LIMIT"
        : "G-CODE READY / PRESS LOAD 3D PREVIEW");
    }
  }
  if (toolpathRequested && !toolpathReady && !toolpathLoading && !toolpathError) {
    beginToolpathLoad(data, filename, key);
  }
  drawToolpath();
}

async function loadToolpath(data, filename, key, signal) {
  const entryId = data.entry_id;
  const metadata = data.meta || {};
  const reportedSize = Number(data.status?.virtual_sdcard?.file_size) || 0;
  renderToolpathStatus("LOADING ACTIVE G-CODE / BUILDING 3D PATH…");
  try {
    const response = await hassApi().fetchWithAuth(API.gcode(entryId, filename), { signal });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || `file request ${response.status}`);
    }
    const totalBytes = Number(response.headers.get("Content-Length")) || reportedSize;
    if (totalBytes > MAX_TOOLPATH_BYTES) throw new Error("G-code file exceeds the 128 MB interactive preview limit");
    const startCandidate = Number(metadata.gcode_start_byte);
    const endCandidate = Number(metadata.gcode_end_byte);
    const rangeStart = Number.isFinite(startCandidate) ? startCandidate : 0;
    const hasMetadataRange = Number.isFinite(endCandidate) && endCandidate > rangeStart;
    const rangeEnd = hasMetadataRange ? endCandidate : (totalBytes || Number.POSITIVE_INFINITY);
    const rangeBytes = Number.isFinite(rangeEnd) ? Math.max(1, rangeEnd - rangeStart) : 1;
    const fractionAt = offset => Number.isFinite(rangeEnd)
      ? Math.max(0, Math.min((offset - rangeStart) / rangeBytes, 1))
      : 0;
    const stride = Math.max(1, Math.ceil(totalBytes / (MAX_TOOLPATH_SEGMENTS * 70)));
    const state = { xyzAbsolute: true, eAbsolute: true, unit: 1, position: { x: 0, y: 0, z: 0, e: 0 }, extrusions: 0 };
    const bounds = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity, minZ: Infinity, maxZ: -Infinity };
    const segments = [];
    const decoder = new TextDecoder();
    const reader = response.body?.getReader();
    if (!reader) {
      const text = await response.text();
      let offset = 0;
      const lines = text.split(/\r?\n/);
      for (let index = 0; index < lines.length; index++) {
        offset += lines[index].length + 1;
        const segment = parseGcodeLine(lines[index], state, fractionAt(offset), stride);
        if (segment && offset >= rangeStart && offset <= rangeEnd) addToolpathSegment(segments, bounds, segment);
        if (index > 0 && index % 6000 === 0) await new Promise(requestAnimationFrame);
      }
    } else {
      let buffer = "";
      let parsedChars = 0;
      let lineCount = 0;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const rawLine of lines) {
          const line = rawLine.replace(/\r$/, "");
          parsedChars += line.length + 1;
          const segment = parseGcodeLine(line, state, fractionAt(parsedChars), stride);
          if (segment && parsedChars >= rangeStart && parsedChars <= rangeEnd) addToolpathSegment(segments, bounds, segment);
          lineCount += 1;
        }
        if (lineCount && lineCount % 7000 < lines.length) {
          renderToolpathStatus(`PARSING G-CODE / ${segments.length.toLocaleString()} PATH SEGMENTS`);
          await new Promise(requestAnimationFrame);
        }
      }
      buffer += decoder.decode();
      if (buffer) {
        parsedChars += buffer.length;
        const segment = parseGcodeLine(buffer, state, fractionAt(parsedChars), stride);
        if (segment && parsedChars >= rangeStart && parsedChars <= rangeEnd) addToolpathSegment(segments, bounds, segment);
      }
    }
    if (key !== toolpathKey) return;
    if (!Number.isFinite(rangeEnd) && segments.length > 1) {
      segments.forEach((segment, index) => { segment.fraction = index / (segments.length - 1); });
    }
    toolpathSegments = segments;
    toolpathBounds = normalizeBounds(bounds);
    toolpathReady = segments.length > 0;
    toolpathError = segments.length ? "" : "NO EXTRUSION MOVES COULD BE PARSED FROM THIS FILE";
    renderToolpathStatus(toolpathReady ? `SIMULATED PATH / ${segments.length.toLocaleString()} SAMPLED MOVES` : toolpathError);
    drawToolpath();
  } catch (error) {
    if (error.name === "AbortError" || key !== toolpathKey) return;
    toolpathReady = false;
    toolpathError = error.message || "TOOLPATH PREVIEW UNAVAILABLE";
    renderToolpathStatus(toolpathError.toUpperCase());
    drawToolpath();
  }
}

function addToolpathSegment(segments, bounds, segment) {
  if (segments.length >= MAX_TOOLPATH_SEGMENTS) return;
  segments.push(segment);
  for (const point of [segment.a, segment.b]) {
    bounds.minX = Math.min(bounds.minX, point[0]);
    bounds.maxX = Math.max(bounds.maxX, point[0]);
    bounds.minY = Math.min(bounds.minY, point[1]);
    bounds.maxY = Math.max(bounds.maxY, point[1]);
    bounds.minZ = Math.min(bounds.minZ, point[2]);
    bounds.maxZ = Math.max(bounds.maxZ, point[2]);
  }
}

function normalizeBounds(bounds) {
  if (!Number.isFinite(bounds.minX)) return null;
  if (bounds.maxX - bounds.minX < 1) { bounds.minX -= .5; bounds.maxX += .5; }
  if (bounds.maxY - bounds.minY < 1) { bounds.minY -= .5; bounds.maxY += .5; }
  if (bounds.maxZ - bounds.minZ < 1) { bounds.minZ = Math.min(0, bounds.minZ); bounds.maxZ += .5; }
  return bounds;
}

function renderToolpathStatus(text) {
  const element = byId("toolpathStatus");
  if (element) element.textContent = text;
}

function projectPoint(point, camera, scale, centerU, centerV, width, height) {
  const cosYaw = Math.cos(camera.yaw), sinYaw = Math.sin(camera.yaw);
  const cosPitch = Math.cos(camera.pitch), sinPitch = Math.sin(camera.pitch);
  const u = point[0] * cosYaw - point[1] * sinYaw;
  const horizontal = point[0] * sinYaw + point[1] * cosYaw;
  const v = horizontal * cosPitch - point[2] * sinPitch;
  const depth = horizontal * sinPitch + point[2] * cosPitch;
  return { x: width / 2 + (u - centerU) * scale, y: height * .53 - (v - centerV) * scale, depth };
}

function drawToolpath() {
  const canvas = byId("toolpathCanvas");
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  if (rect.width < 8 || rect.height < 8) return;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const pixelWidth = Math.round(rect.width * ratio);
  const pixelHeight = Math.round(rect.height * ratio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  const width = rect.width, height = rect.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#030d0a";
  ctx.fillRect(0, 0, width, height);

  const bounds = toolpathBounds;
  if (!bounds) {
    drawEmptyBuildPlate(ctx, width, height);
    return;
  }
  const corners = [
    [bounds.minX - 5, bounds.minY - 5, 0], [bounds.maxX + 5, bounds.minY - 5, 0],
    [bounds.maxX + 5, bounds.maxY + 5, 0], [bounds.minX - 5, bounds.maxY + 5, 0],
    [bounds.minX - 5, bounds.minY - 5, bounds.maxZ], [bounds.maxX + 5, bounds.minY - 5, bounds.maxZ],
    [bounds.maxX + 5, bounds.maxY + 5, bounds.maxZ], [bounds.minX - 5, bounds.maxY + 5, bounds.maxZ],
  ];
  const cosYaw = Math.cos(toolpathCamera.yaw), sinYaw = Math.sin(toolpathCamera.yaw);
  const cosPitch = Math.cos(toolpathCamera.pitch), sinPitch = Math.sin(toolpathCamera.pitch);
  const transformed = corners.map(point => {
    const u = point[0] * cosYaw - point[1] * sinYaw;
    const horizontal = point[0] * sinYaw + point[1] * cosYaw;
    return { u, v: horizontal * cosPitch - point[2] * sinPitch };
  });
  const minU = Math.min(...transformed.map(point => point.u));
  const maxU = Math.max(...transformed.map(point => point.u));
  const minV = Math.min(...transformed.map(point => point.v));
  const maxV = Math.max(...transformed.map(point => point.v));
  const centerU = (minU + maxU) / 2, centerV = (minV + maxV) / 2;
  const scale = Math.max(.01, Math.min((width - 54) / Math.max(1, maxU - minU), (height - 42) / Math.max(1, maxV - minV)) * toolpathCamera.zoom);
  const project = point => projectPoint(point, toolpathCamera, scale, centerU, centerV, width, height);

  drawBuildPlate(ctx, project, bounds);
  const progress = getLiveProgress(latestData);
  const showFuture = byId("showFuturePath")?.checked !== false;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.lineWidth = 1.2;
  if (showFuture) {
    ctx.beginPath();
    for (const segment of toolpathSegments) {
      if ((segment.fraction ?? 0) <= progress) continue;
      const a = project(segment.a), b = project(segment.b);
      ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
    }
    ctx.strokeStyle = "rgba(15, 108, 66, .48)";
    ctx.stroke();
  }
  ctx.beginPath();
  for (const segment of toolpathSegments) {
    if ((segment.fraction ?? 0) > progress) continue;
    const a = project(segment.a), b = project(segment.b);
    ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
  }
  ctx.strokeStyle = "#00ef91";
  ctx.shadowColor = "rgba(0,239,145,.3)";
  ctx.shadowBlur = 3;
  ctx.stroke();
  ctx.shadowBlur = 0;

  const position = latestData?.status?.toolhead?.position || [];
  if (position.length >= 3 && position.slice(0,3).every(value => Number.isFinite(Number(value)))) {
    const head = project([Number(position[0]), Number(position[1]), Number(position[2])]);
    ctx.beginPath(); ctx.arc(head.x, head.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = "#f7cb64"; ctx.shadowColor = "#f7cb64"; ctx.shadowBlur = 10; ctx.fill(); ctx.shadowBlur = 0;
    ctx.beginPath(); ctx.moveTo(head.x - 8, head.y); ctx.lineTo(head.x + 8, head.y); ctx.moveTo(head.x, head.y - 8); ctx.lineTo(head.x, head.y + 8);
    ctx.strokeStyle = "#f7cb64"; ctx.lineWidth = 1; ctx.stroke();
  }
  renderToolpathStatus(toolpathReady ? `SIMULATED EXTRUSION PATH / ${toolpathSegments.length.toLocaleString()} SAMPLES / ${(progress * 100).toFixed(1)}%` : (toolpathError || "LOADING ACTIVE G-CODE"));
}

function drawBuildPlate(ctx, project, bounds) {
  const minX = Math.min(0, bounds.minX - 5), maxX = Math.max(220, bounds.maxX + 5);
  const minY = Math.min(0, bounds.minY - 5), maxY = Math.max(220, bounds.maxY + 5);
  const step = Math.max(10, Math.ceil(Math.max(maxX - minX, maxY - minY) / 22 / 10) * 10);
  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(28,104,68,.42)";
  ctx.beginPath();
  for (let x = Math.ceil(minX / step) * step; x <= maxX; x += step) {
    const a = project([x, minY, 0]), b = project([x, maxY, 0]);
    ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
  }
  for (let y = Math.ceil(minY / step) * step; y <= maxY; y += step) {
    const a = project([minX, y, 0]), b = project([maxX, y, 0]);
    ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
  }
  ctx.stroke();
  const floor = [[minX,minY,0],[maxX,minY,0],[maxX,maxY,0],[minX,maxY,0]];
  ctx.beginPath();
  floor.forEach((point, index) => { const p = project(point); index ? ctx.lineTo(p.x,p.y) : ctx.moveTo(p.x,p.y); });
  ctx.closePath();
  ctx.strokeStyle = "rgba(0,239,145,.7)";
  ctx.stroke();
  const top = [[minX,minY,bounds.maxZ],[maxX,minY,bounds.maxZ],[maxX,maxY,bounds.maxZ],[minX,maxY,bounds.maxZ]];
  ctx.beginPath();
  floor.forEach((point,index) => { const p=project(point); index ? ctx.lineTo(p.x,p.y) : ctx.moveTo(p.x,p.y); });
  ctx.closePath();
  top.forEach((point,index) => { const a=project(floor[index]), b=project(point); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); });
  ctx.strokeStyle = "rgba(0,239,145,.17)";
  ctx.stroke();
  const origin = project([0,0,0]);
  const xAxis = project([Math.min(maxX, 25),0,0]);
  const yAxis = project([0,Math.min(maxY,25),0]);
  const zAxis = project([0,0,Math.max(bounds.maxZ,25)]);
  ctx.lineWidth = 1.5;
  [[origin,xAxis,"#ff536b","X"],[origin,yAxis,"#35e8bd","Y"],[origin,zAxis,"#00ef91","Z"]].forEach(([a,b,color,label]) => {
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.strokeStyle=color; ctx.stroke();
    ctx.fillStyle=color; ctx.font="7px monospace"; ctx.fillText(label,b.x+3,b.y-2);
  });
}

function drawEmptyBuildPlate(ctx, width, height) {
  ctx.strokeStyle = "rgba(0,130,76,.35)";
  ctx.lineWidth = 1;
  const pad = 26;
  for (let x = pad; x < width - pad; x += 20) { ctx.beginPath(); ctx.moveTo(x,pad); ctx.lineTo(x,height-pad); ctx.stroke(); }
  for (let y = pad; y < height - pad; y += 20) { ctx.beginPath(); ctx.moveTo(pad,y); ctx.lineTo(width-pad,y); ctx.stroke(); }
  ctx.strokeStyle = "rgba(0,239,145,.65)";
  ctx.strokeRect(pad,pad,width-pad*2,height-pad*2);
}

function getLiveProgress(data) {
  const status = data?.status || {};
  const card = status.virtual_sdcard || {};
  const position = Number(card.file_position);
  const start = Number(data?.meta?.gcode_start_byte);
  const end = Number(data?.meta?.gcode_end_byte);
  if (Number.isFinite(position) && Number.isFinite(start) && Number.isFinite(end) && end > start) {
    return Math.max(0, Math.min((position - start) / (end - start), 1));
  }
  const size = Number(card.file_size);
  if (Number.isFinite(position) && Number.isFinite(size) && size > 0) {
    return Math.max(0, Math.min(position / size, 1));
  }
  const fallback = Number(status.display_status?.progress ?? card.progress ?? 0);
  return Number.isFinite(fallback) ? Math.max(0, Math.min(fallback, 1)) : 0;
}

function bindToolpathCanvas() {
  const canvas = byId("toolpathCanvas");
  let startX = 0, startY = 0;
  canvas.addEventListener("pointerdown", event => {
    toolpathCamera.dragging = true; startX = event.clientX; startY = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", event => {
    if (!toolpathCamera.dragging) return;
    const deltaX = event.clientX - startX, deltaY = event.clientY - startY;
    startX = event.clientX; startY = event.clientY;
    toolpathCamera.yaw += deltaX * .009;
    toolpathCamera.pitch = Math.max(.025, Math.min(1.55, toolpathCamera.pitch + deltaY * .008));
    drawToolpath();
  });
  const stopDrag = () => { toolpathCamera.dragging = false; };
  canvas.addEventListener("pointerup", stopDrag);
  canvas.addEventListener("pointercancel", stopDrag);
  canvas.addEventListener("wheel", event => {
    event.preventDefault();
    toolpathCamera.zoom = Math.max(.45, Math.min(3.5, toolpathCamera.zoom * (event.deltaY < 0 ? 1.1 : .91)));
    drawToolpath();
  }, { passive: false });
  window.addEventListener("resize", drawToolpath);
}

function initializePanel() {
  bindInteractions();
  bindToolpathCanvas();
  setScreen("dashboard");
  refresh();
  if (!window.moonrakerRefreshTimer) window.moonrakerRefreshTimer = setInterval(refresh, 2000);
}

function startPanel() {
  if (window.moonrakerPanelStarted) return;
  window.moonrakerPanelStarted = true;
  initializePanel();
}

window.addEventListener("moonraker-hass-ready", startPanel);
if (window.hass?.callApi) startPanel();
