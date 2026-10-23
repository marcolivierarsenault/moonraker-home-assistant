const API = {
  data: (printer) =>
    `moonraker/panel_data?printer=${encodeURIComponent(printer || "")}`,
  thumb: (printer, filename) =>
    `/api/moonraker/panel_thumbnail?printer=${encodeURIComponent(
      printer || "",
    )}${filename ? `&filename=${encodeURIComponent(filename)}` : ""}`,
  snapshot: (printer, camera) =>
    `/api/moonraker/panel_webcam_snapshot?printer=${encodeURIComponent(
      printer || "",
    )}&camera=${encodeURIComponent(camera || "")}`,
  gcode: (printer, filename) =>
    `/api/moonraker/panel_gcode?printer=${encodeURIComponent(
      printer || "",
    )}&filename=${encodeURIComponent(filename || "")}`,
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

const PANEL_FALLBACK_POLL_MS = 2667;
const PANEL_STALENESS_CHECK_MS = 1333;
const byId = (id) => document.getElementById(id);
const setText = (id, value) => {
  const element = byId(id);
  if (element) element.textContent = t(value);
};

// ---- panel translations ----

const I18N_STATIC_SELECTOR =
  ".nav-label, .panel-title, .panel-kicker, .stat-label, .stat-foot, .micro, .empty-state, .notice, .skip-link, button, option, label, p, strong, span, b, h2";
let panelLang = "en";

function t(value) {
  if (typeof value !== "string" || panelLang === "en") return value;
  return window.NEXUS_I18N?.[panelLang]?.[value] ?? value;
}

function resolvePanelLanguage(choice) {
  const requested =
    choice && choice !== "auto"
      ? choice
      : String(
          window.hass?.locale?.language ||
            window.hass?.language ||
            window.navigator?.language ||
            "en",
        );
  const code = requested.toLowerCase().slice(0, 2);
  return window.NEXUS_I18N?.[code] ? code : "en";
}

function translateNodeText(holder, getText, setTextValue) {
  const raw = getText();
  const parts = /^(\s*)([\s\S]*?)(\s*)$/.exec(raw);
  const source = holder.i18nSrc ?? parts[2].replace(/\s+/g, " ");
  if (!source) return;
  holder.i18nSrc = source;
  setTextValue(`${parts[1]}${t(source)}${parts[3]}`);
}

function translateStatic(root = document) {
  for (const element of root.querySelectorAll?.(I18N_STATIC_SELECTOR) || []) {
    if (element.id) continue;
    if (!element.children?.length) {
      translateNodeText(
        element.dataset,
        () => element.textContent,
        (text) => {
          element.textContent = text;
        },
      );
      continue;
    }
    for (const node of element.childNodes || []) {
      if (node.nodeType !== 3) continue;
      translateNodeText(
        node,
        () => node.textContent,
        (text) => {
          node.textContent = text;
        },
      );
    }
  }
  for (const element of root.querySelectorAll?.("[placeholder]") || []) {
    const source =
      element.dataset.i18nPlaceholder ?? element.getAttribute("placeholder");
    element.dataset.i18nPlaceholder = source;
    element.setAttribute("placeholder", t(source));
  }
}

function applyPanelLanguage(choice) {
  const lang = resolvePanelLanguage(choice);
  if (lang === panelLang) return false;
  panelLang = lang;
  if (document.documentElement) document.documentElement.lang = lang;
  translateStatic(document);
  if (SCREEN_TITLES[activeScreen]) {
    setText("pageKicker", SCREEN_TITLES[activeScreen][0]);
    setText("screenTitle", SCREEN_TITLES[activeScreen][1]);
  }
  return true;
}

let printer = "";
let jogStep = 1;
let lastFiles = [];
let selectedFile = "";
let latestData = null;
let consoleSignature = "";
let sentCommandHistory = [];
let activeScreen = "dashboard";
let detailsOpen = false;
let lastThumbnailKey = "";
let thumbnailObjectUrl = null;
let cameraLayout = "1x1";
let cameraAssignments = [];
let cameraGridSignature = "";
let dashboardCameraLayout = "1";
let dashboardCameraAssignments = [];
let dashboardCameraSignature = "";
let dashboardCameraPrefsKey = "";
let cameraConfigOpen = false;
let availableWebcams = [];
let toolpathKey = "";
let toolpathAbort = null;
let toolpathRequested = false;
let toolpathSegments = [];
let toolpathBounds = null;
let toolpathReady = false;
let toolpathLoading = false;
let toolpathError = "";
let toolpathLayerStats = [];
let toolpathSimSeconds = 0;
let extHist = [];
let bedHist = [];
let toolpathCamera = {
  yaw: -0.72,
  pitch: 0.7,
  zoom: 1,
  panX: 0,
  panY: 0,
  dragX: 0,
  dragY: 0,
  dragging: false,
};
let cameraAnim = null;
let cameraAnimFrame = null;
let orbitVelocityX = 0;
let orbitVelocityY = 0;
let orbitInertiaFrame = null;
const CAMERA_VIEWS = {
  iso: { yaw: -0.72, pitch: 0.7 },
  iso2: { yaw: 2.42, pitch: 0.7 },
  top: { yaw: 0, pitch: 0.035 },
  front: { yaw: 0, pitch: 1.5 },
  back: { yaw: Math.PI, pitch: 1.5 },
  left: { yaw: -Math.PI / 2, pitch: 1.5 },
  right: { yaw: Math.PI / 2, pitch: 1.5 },
};
let liveEntityIds = {};
let liveSubscription = false;
let liveSubscriptionUnsub = null;
let liveSubscriptionGeneration = 0;
let panelStopped = false;
let liveHeadTarget = null;
let liveHeadDrawn = null;
let liveProgress = null;
let liveLayer = null;
let headAnimFrame = null;
let scrubZ = null;
let timelapseFrames = [];
let timelapseBytes = 0;
let timelapseAbort = null;
let timelapseGeneration = 0;
let timelapseViewCamera = "";
const MAX_TIMELAPSE_FRAMES = 400;
const MAX_TIMELAPSE_BYTES = 64 * 1024 * 1024;
let analysisFile = "";
let displayPrefsKey = "";
let retransmitHistory = [];

function hassApi() {
  const api = window.hass;
  if (!api?.callApi || !api?.fetchWithAuth) {
    throw new Error("Open the console from the Home Assistant sidebar panel.");
  }
  return api;
}

function fmt(value, digits = 1) {
  return value == null || Number.isNaN(Number(value))
    ? "—"
    : Number(value).toFixed(digits);
}

function duration(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return "—";
  seconds = Math.max(0, Math.floor(seconds));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return `${days ? `${days}d ` : ""}${
    hours ? `${hours}h ` : ""
  }${minutes}m ${remainder}s`;
}

function toast(message, milliseconds = 3200) {
  const element = byId("toast");
  element.textContent = t(message);
  element.style.display = "block";
  clearTimeout(element._timer);
  element._timer = setTimeout(() => {
    element.style.display = "none";
  }, milliseconds);
}

function handlePanelPayload(data) {
  if (data?.error) {
    toast(data.error);
    return;
  }
  lastDataAt = Date.now();
  updateStaleness();
  render(data);
  if (!Object.keys(liveEntityIds).length) resolveLiveEntities();
  ensureLiveSubscription();
}

async function refresh() {
  // Websocket push is the primary feed; polling only refills when push stalls.
  if (
    panelStopped ||
    (panelPushLive && lastDataAt && Date.now() - lastDataAt < 12000)
  )
    return;
  if (panelRefreshInFlight) return;
  panelRefreshInFlight = true;
  const requestPrinter = printer;
  try {
    const data = await hassApi().callApi("GET", API.data(requestPrinter));
    if (requestPrinter === printer) handlePanelPayload(data);
  } catch (error) {
    if (error.message?.includes("Open the console")) toast(error.message);
  } finally {
    panelRefreshInFlight = false;
    if (requestPrinter !== printer) refresh();
  }
}

async function subscribePanelPush() {
  const connection = window.hass?.connection;
  if (
    !connection?.subscribeMessage ||
    panelPushUnsub ||
    panelPushRequest ||
    panelStopped
  )
    return;
  const request = connection.subscribeMessage(
    { type: "moonraker/panel_subscribe", entry_id: printer || undefined },
    (data) => {
      panelPushLive = true;
      handlePanelPayload(data);
    },
  );
  panelPushRequest = request;
  try {
    panelPushUnsub = await request;
  } catch {
    panelPushLive = false;
  } finally {
    panelPushRequest = null;
  }
}

async function resetPanelPush() {
  panelPushLive = false;
  if (panelPushRequest) {
    const request = panelPushRequest;
    panelPushRequest = null;
    try {
      const unsub = await request;
      unsub();
    } catch {
      /* subscription never established */
    }
    return;
  }
  if (panelPushUnsub) {
    const unsub = panelPushUnsub;
    panelPushUnsub = null;
    try {
      unsub();
    } catch {
      /* already closed */
    }
  }
  panelPushLive = false;
}

function clearAuthedImage(image) {
  if (!image) return;
  const objectUrl =
    image === byId("thumb") ? thumbnailObjectUrl : image._objectUrl;
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  if (image === byId("thumb")) thumbnailObjectUrl = null;
  image._objectUrl = null;
  image.removeAttribute("src");
  image.hidden = true;
  image.style.display = "none";
}

async function loadAuthedImage(image, url) {
  if (!image) return false;
  clearAuthedImage(image);
  const generation = (image._loadGen = (image._loadGen || 0) + 1);
  try {
    const response = await hassApi().fetchWithAuth(url);
    if (!response.ok || generation !== image._loadGen) return false;
    const blob = await response.blob();
    if (!blob.size || generation !== image._loadGen) return false;
    const objectUrl = URL.createObjectURL(blob);
    if (image === byId("thumb")) thumbnailObjectUrl = objectUrl;
    else image._objectUrl = objectUrl;
    let loadPromise;
    if (typeof image.decode !== "function") {
      loadPromise = new Promise((resolve, reject) => {
        image.onload = () => {
          image.onload = null;
          image.onerror = null;
          resolve();
        };
        image.onerror = () => {
          image.onload = null;
          image.onerror = null;
          reject(new Error("Image decode failed"));
        };
      });
    }
    image.src = objectUrl;
    if (typeof image.decode === "function") await image.decode();
    else await loadPromise;
    if (generation !== image._loadGen) return false;
    image.hidden = false;
    image.style.display = "";
    return true;
  } catch {
    if (generation !== image._loadGen) return false;
    clearAuthedImage(image);
    return false;
  }
}

async function updateThumbnail(data) {
  const filename = (data.status?.print_stats || {}).filename || "";
  const key = `${data.entry_id}:${filename}:${
    data.meta?.thumbnails_path || ""
  }`;
  if (key === lastThumbnailKey) return;
  lastThumbnailKey = key;
  const image = byId("thumb");
  if (!filename || !data.meta?.thumbnails_path) {
    clearAuthedImage(image);
    return;
  }
  await loadAuthedImage(image, API.thumb(data.entry_id));
}

function drawTemperatureGraph(canvasId, extruderTarget, bedTarget) {
  const canvas = byId(canvasId);
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);
  context.fillStyle = cssVar("--bg", "#030b08");
  context.fillRect(0, 0, width, height);
  const maximum =
    Math.max(
      60,
      ...extHist,
      ...bedHist,
      Number(extruderTarget) || 0,
      Number(bedTarget) || 0,
    ) * 1.12;
  context.strokeStyle = cssRgba("--line-hi", 0.28, "rgba(41,104,70,.28)");
  context.lineWidth = 1;
  for (let row = 1; row < 4; row++) {
    const y = (height * row) / 4;
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
      const x = (index / Math.max(values.length - 1, 1)) * width;
      const y = height - (Number(value) / maximum) * height;
      index ? context.lineTo(x, y) : context.moveTo(x, y);
    });
    context.stroke();
  }
  line(extHist, cssVar("--green", "#00ef91"));
  line(bedHist, cssVar("--cyan", "#39e8bd"));
  [
    [extruderTarget, cssVar("--green", "#00ef91")],
    [bedTarget, cssVar("--cyan", "#39e8bd")],
  ].forEach(([target, color]) => {
    if (target == null) return;
    const y = height - (Number(target) / maximum) * height;
    context.beginPath();
    context.setLineDash([4, 4]);
    context.strokeStyle = color;
    context.globalAlpha = 0.45;
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
    context.setLineDash([]);
    context.globalAlpha = 1;
  });
  context.font = "10px monospace";
  context.fillStyle = cssVar("--green-soft", "#9bffc7");
  context.fillText(`NOZZLE ${fmt(extHist.at(-1), 0)}°`, 8, 13);
  context.fillStyle = cssVar("--cyan", "#39e8bd");
  context.fillText(`BED ${fmt(bedHist.at(-1), 0)}°`, 102, 13);
}

function findNamedStatus(status, pattern) {
  return (
    Object.entries(status || {}).find(
      ([name, value]) =>
        pattern.test(name) && value && typeof value === "object",
    )?.[1] || {}
  );
}

function render(data) {
  latestData = data;
  printer = data.entry_id || printer;
  subscribePanelPush();
  const printerSelect = byId("printerSel");
  if (!printerSelect.options.length && data.entries) {
    data.entries.forEach((entry) => {
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
  stateChip.append(
    stateLed,
    document.createTextNode(data.available ? printState : "OFFLINE"),
  );
  stateChip.classList.toggle("bad", !data.available);
  setText("klippyChip", `KLIPPY ${(data.printer_info || {}).state || "—"}`);
  setText(
    "tickerText",
    `${data.printer} // ${printState} // FILE ${
      printStats.filename || "NONE"
    } // ${(progress * 100).toFixed(1)}% // NOZZLE ${fmt(
      extruder.temperature,
      0,
    )}°C // BED ${fmt(bed.temperature, 0)}°C`,
  );

  const ring = byId("ringFg");
  ring.style.strokeDashoffset = 320.44 * (1 - Math.min(progress, 1));
  setText("pct", `${(progress * 100).toFixed(0)}%`);
  setText("fname", printStats.filename || "NO ACTIVE G-CODE");
  const remaining = Math.max(
    0,
    (meta.estimated_time || 0) - (printStats.print_duration || 0),
  );
  setText("eta", `ETA ${duration(remaining)}`);
  setText("elapsed", duration(printStats.print_duration));
  setText("remaining", duration(remaining));
  setText("totalEst", duration(printStats.total_duration));
  setText("slicerEst", duration(meta.estimated_time));
  setText("filUsed", `${fmt((printStats.filament_used || 0) / 1000, 2)} m`);
  setText("filEst", `${fmt((meta.filament_total || 0) / 1000, 2)} m`);
  const currentLayer =
    printStats.info?.current_layer ??
    virtualSdcard.current_layer ??
    (data.layers?.current || "—");
  const totalLayers =
    printStats.info?.total_layer ??
    virtualSdcard.total_layer ??
    data.layers?.total ??
    meta.layer_count;
  const layerLabel =
    currentLayer === "—"
      ? "—"
      : `${currentLayer}${totalLayers ? ` / ${totalLayers}` : ""}`;
  setText("layer", layerLabel);
  const layerFraction =
    Number(currentLayer) > 0 && Number(totalLayers) > 0
      ? Number(currentLayer) / Number(totalLayers)
      : progress;
  byId("layerBar").style.width = `${Math.min(layerFraction * 100, 100)}%`;
  setText("zpos", `${fmt(position[2], 2)} mm`);
  setText("dashboardState", printState);
  setText(
    "dashboardAvailability",
    data.available ? "STREAMING" : "UNAVAILABLE",
  );
  setText("printPageState", printState);
  setText("printPageFile", printStats.filename || "NO ACTIVE G-CODE");
  byId("printProgressBar").style.width = `${Math.min(progress * 100, 100)}%`;
  setText("printProgressText", `${(progress * 100).toFixed(1)}%`);
  setText("printPageEta", `ETA ${duration(remaining)}`);
  setText("printElapsed", duration(printStats.print_duration));
  setText("printRemaining", duration(remaining));
  setText("printLayer", layerLabel);
  setText("printHeight", `${fmt(meta.layer_height, 2)} mm`);
  setText(
    "printFilament",
    `${fmt((printStats.filament_used || 0) / 1000, 2)} m`,
  );
  setText("printEstimate", duration(meta.estimated_time));
  setText("printMetaEstimate", duration(meta.estimated_time));
  setText(
    "printMetaFilament",
    `${fmt((meta.filament_total || 0) / 1000, 2)} m`,
  );
  setText("printMetaObjectHeight", `${fmt(meta.object_height, 2)} mm`);
  setText("printMetaLayerCount", meta.layer_count ?? "—");
  setText(
    "printToolpathStatus",
    toolpathReady
      ? "INTERACTIVE TOOLPATH READY / DASHBOARD VIEW"
      : "PREVIEW LOADS FROM ACTIVE G-CODE ON DASHBOARD",
  );
  setText("tuneProgress", `${(progress * 100).toFixed(1)}%`);
  setText("tuneEta", `ETA ${duration(remaining)}`);
  byId("tuneProgressBar").style.width = `${Math.min(progress * 100, 100)}%`;

  setText("dashNozzle", `${fmt(extruder.temperature, 0)}°C`);
  setText("dashNozzleTarget", `${fmt(extruder.target, 0)}°C`);
  byId("extBar").style.width = `${Math.min(
    ((extruder.temperature || 0) / 300) * 100,
    100,
  )}%`;
  setText(
    "extNow",
    `${fmt(extruder.temperature, 0)}°C / ${fmt(extruder.target, 0)}°C`,
  );
  setText(
    "extBarT",
    `${fmt(extruder.temperature, 0)} / ${fmt(extruder.target, 0)}°C`,
  );
  setText("dashBed", `${fmt(bed.temperature, 0)}°C`);
  setText("dashBedTarget", `${fmt(bed.target, 0)}°C`);
  byId("bedBar").style.width = `${Math.min(
    ((bed.temperature || 0) / 130) * 100,
    100,
  )}%`;
  setText("bedNow", `${fmt(bed.temperature, 0)}°C / ${fmt(bed.target, 0)}°C`);
  setText("bedBarT", `${fmt(bed.temperature, 0)} / ${fmt(bed.target, 0)}°C`);
  if (document.activeElement !== byId("extTarget"))
    byId("extTarget").value =
      extruder.target == null ? "" : Math.round(extruder.target);
  if (document.activeElement !== byId("bedTarget"))
    byId("bedTarget").value = bed.target == null ? "" : Math.round(bed.target);

  const chamber = findNamedStatus(status, /chamber|enclosure/i);
  setText(
    "dashChamber",
    chamber.temperature == null ? "—" : `${fmt(chamber.temperature, 0)}°C`,
  );
  setText(
    "dashHumidity",
    chamber.humidity == null
      ? "SENSOR / NOT REPORTED"
      : `HUMIDITY ${fmt(chamber.humidity, 0)}%`,
  );
  setText("dashSpeed", `${Math.round((gcodeMove.speed_factor || 0) * 100)}%`);
  setText("dashFlow", `${Math.round((gcodeMove.extrude_factor || 0) * 100)}%`);
  setText("dashFan", `${Math.round((fan.speed || 0) * 100)}%`);
  if (document.activeElement !== byId("speed"))
    byId("speed").value = Math.round((gcodeMove.speed_factor || 0) * 100);
  if (document.activeElement !== byId("flow"))
    byId("flow").value = Math.round((gcodeMove.extrude_factor || 0) * 100);
  if (document.activeElement !== byId("fan"))
    byId("fan").value = Math.round((fan.speed || 0) * 100);
  setText("speedVal", `${Math.round((gcodeMove.speed_factor || 0) * 100)}%`);
  setText("flowVal", `${Math.round((gcodeMove.extrude_factor || 0) * 100)}%`);
  setText("fanVal", `${Math.round((fan.speed || 0) * 100)}%`);
  setText("speedFactor", `${Math.round((gcodeMove.speed_factor || 0) * 100)}%`);
  setText(
    "flowFactor",
    `${Math.round((gcodeMove.extrude_factor || 0) * 100)}%`,
  );
  setText("fanNow", `${Math.round((fan.speed || 0) * 100)}%`);
  setText(
    "tuneSpeedFactor",
    `${Math.round((gcodeMove.speed_factor || 0) * 100)}%`,
  );
  setText(
    "tuneFlowFactor",
    `${Math.round((gcodeMove.extrude_factor || 0) * 100)}%`,
  );
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
  setText("consoleXY", `${fmt(position[0], 2)} / ${fmt(position[1], 2)}`);
  setText("consoleZ", fmt(position[2], 2));
  setText("consoleLayer", layerLabel);
  setText("consoleConnection", data.available ? "LIVE" : "UNAVAILABLE");

  setText(
    "extrusionFilUsed",
    `${fmt((printStats.filament_used || 0) / 1000, 2)} m`,
  );
  setText("extrusionFilEst", `${fmt((meta.filament_total || 0) / 1000, 2)} m`);
  setText("extrusionLayer", layerLabel);
  setText("extrusionNozzle", `${fmt(extruder.temperature, 1)}°C`);
  setText("extrusionTarget", `${fmt(extruder.target, 1)}°C`);
  setText("extrusionPosition", `${fmt(position[3], 2)} mm`);
  setText("extrusionSpeed", `${fmt(gcodeMove.speed, 0)} mm/s`);
  setText(
    "extrusionSpeedFactor",
    `${Math.round((gcodeMove.speed_factor || 0) * 100)}%`,
  );
  setText(
    "extrusionFlowFactor",
    `${Math.round((gcodeMove.extrude_factor || 0) * 100)}%`,
  );
  setText("extrusionTemp", `${fmt(extruder.temperature, 0)}°C`);
  setText("extrusionFan", `${Math.round((fan.speed || 0) * 100)}%`);
  setText("bedzPosition", `${fmt(position[2], 2)} mm`);
  setText("bedLayer", layerLabel);
  setText("bedLayerHeight", `${fmt(meta.layer_height, 2)} mm`);
  setText("bedTempZ", `${fmt(bed.temperature, 0)}°C`);
  setText("networkState", data.available ? "CONNECTED" : "OFFLINE");
  setText("networkMoonraker", data.available ? "ONLINE" : "UNAVAILABLE");
  setText("networkKlippy", (data.printer_info || {}).state || "—");
  setText("networkPush", "WEBSOCKET / FALLBACK POLL");
  setText("networkCameras", String((data.webcams || []).length));
  renderSettings(data);
  renderSystem(data, status, printState);
  renderFleet(data);
  lastFlowFinding = renderFlowHeadroom(status);
  renderHealth(data);
  renderMaintenance(data);
  renderComponents(data);
  renderBedMesh(status);
  renderMeshDecay(status);
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
  const extTemp = Number(extruder.temperature);
  const bedTemp = Number(bed.temperature);
  if (Number.isFinite(extTemp)) extHist.push(extTemp);
  if (Number.isFinite(bedTemp)) bedHist.push(bedTemp);
  if (extHist.length > 240) extHist.splice(0, extHist.length - 240);
  if (bedHist.length > 240) bedHist.splice(0, bedHist.length - 240);
  drawTemperatureGraph("tempGraph", extruder.target, bed.target);
  drawTemperatureGraph("tempGraphHistory", extruder.target, bed.target);
  maybeTimelapse(data, currentLayer);
  if (detailsOpen) renderPageDetails(data);
  populateAlertEntities();
  loadFlowPrefs();
  loadEnergyPrefs();
  populateEnergyEntities();
  updateEnergy(data);
  loadDisplayPrefs();
  checkAlerts(data);
}

function renderSettings(data) {
  const settings = data.settings || {};
  setText("settingName", data.printer || "—");
  setText("settingHost", settings.host || "—");
  setText("settingPort", settings.port ?? "—");
  setText("settingTls", settings.tls ? "ENABLED" : "DISABLED");
  setText(
    "settingIdlePoll",
    settings.idle_poll_seconds == null ? "—" : `${settings.idle_poll_seconds}s`,
  );
  setText(
    "settingPrintPoll",
    settings.print_poll_seconds == null
      ? "—"
      : `${settings.print_poll_seconds}s`,
  );
  setText("settingQuiet", settings.quiet_unreachable ? "ENABLED" : "DISABLED");
  setText("settingVersion", data.integration_version || "—");
  setText("networkHost", settings.host || "—");
  setText("networkPort", settings.port ?? "—");
  setText("networkTls", settings.tls ? "ENABLED" : "DISABLED");
  setText(
    "networkApiKey",
    data.api_key_configured ? "CONFIGURED / VALUE HIDDEN" : "NOT CONFIGURED",
  );
}

function renderSystem(data, status, printState) {
  const printerInfo = data.printer_info || {};
  const systemInfo = data.system_info || {};
  const cpu = systemInfo.cpu_info || {};
  const versions = (data.machine_update || {}).version_info || {};
  const klipper = versions.klipper || {};
  const moonraker = versions.moonraker || {};
  const hostTemp = findNamedStatus(
    status,
    /temperature_host|host_temperature|temperature_sensor.*(host|rpi)/i,
  );
  const printerState = printerInfo.state || printState || "—";
  const klippyState = printerInfo.state || "—";
  const klipperVersion =
    klipper.version ||
    klipper.current_version ||
    printerInfo.software_version ||
    "—";
  const moonrakerVersion =
    moonraker.version ||
    moonraker.current_version ||
    data.server_info?.moonraker_version ||
    "—";
  const cpuModel = cpu.cpu_desc || cpu.model || cpu.processor || "—";
  const hostTemperature =
    hostTemp.temperature ??
    status.system_stats?.cpu_temp ??
    status.system_stats?.cpu_temperature;
  const hostTemperatureText =
    hostTemperature == null ? "NOT REPORTED" : `${fmt(hostTemperature, 1)}°C`;

  setText("sysPrinterState", printerState);
  setText("sysKlippy", klippyState);
  setText("sysKlipperVersion", klipperVersion);
  setText("sysMoonrakerVersion", moonrakerVersion);
  setText("sysCpu", cpuModel);
  setText("sysHostTemp", hostTemperatureText);
  setText("systemPrinterState", printerState);
  setText("systemKlippy", klippyState);
  setText("systemKlipperVersion", klipperVersion);
  setText("systemMoonrakerVersion", moonrakerVersion);
  setText("systemCpu", cpuModel);
  setText("systemHostTemp", hostTemperatureText);
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
  platforms.forEach((platform) =>
    appendObjectRow(platformList, platform, "LOADED"),
  );
  if (!platforms.length) appendEmpty(platformList, "NO PLATFORMS REPORTED");

  const objects = data.tracked_objects || [];
  setText("objectCount", `${objects.length} OBJECTS`);
  const objectList = byId("objectList");
  objectList.replaceChildren();
  objects.forEach((object) =>
    appendObjectRow(
      objectList,
      object.name,
      object.fields == null ? "ALL FIELDS" : object.fields.join(", "),
    ),
  );
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
  const probe = byId("probeMeshBtn");
  if (probe) {
    const state = String(status.print_stats?.state || "");
    probe.hidden = state === "printing" || state === "paused";
  }
  const container = byId("bedMeshMap");
  container.replaceChildren();
  if (Array.isArray(matrix) && matrix.length && Array.isArray(matrix[0])) {
    const values = matrix.flat().map(Number).filter(Number.isFinite);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const spread = Math.max(1e-6, max - min);
    container.style.gridTemplateColumns = `repeat(${matrix[0].length}, minmax(0, 1fr))`;
    matrix.forEach((row) =>
      row.forEach((value) => {
        const cell = document.createElement("div");
        const numeric = Number(value);
        const ratio = Number.isFinite(numeric) ? (numeric - min) / spread : 0;
        // Blue (low) → green (mid) → red (high) deviation scale.
        const hue = displayPrefs.colorSafe
          ? ratio < 0.5
            ? 210
            : 24
          : Math.round(215 - 215 * ratio);
        const saturation = displayPrefs.colorSafe
          ? Math.round(Math.abs(ratio - 0.5) * 160)
          : 72;
        cell.className = "mesh-cell";
        cell.style.background = `hsl(${hue} ${saturation}% ${Math.round(
          26 + 20 * (1 - Math.abs(ratio - 0.5) * 2),
        )}%)`;
        cell.textContent = Number.isFinite(numeric) ? numeric.toFixed(3) : "—";
        container.appendChild(cell);
      }),
    );
    const minPoint = (mesh.mesh_min || []).join(", ");
    const maxPoint = (mesh.mesh_max || []).join(", ");
    setText(
      "meshBounds",
      `PROBED ${matrix.length} × ${matrix[0].length} / MIN ${fmt(
        min,
        3,
      )} / MAX ${fmt(max, 3)} / Δ ${fmt(spread, 3)} MM / AREA ${
        minPoint || "—"
      } → ${maxPoint || "—"}`,
    );
  } else {
    container.style.gridTemplateColumns = "1fr";
    appendEmpty(container, "BED MESH MATRIX NOT REPORTED BY PRINTER");
    setText(
      "meshBounds",
      "Klipper bed_mesh must be configured and probed to show a height map.",
    );
  }
}

function renderHardware(status) {
  const hardwareRows = Object.entries(status).filter(
    ([name, value]) =>
      /mcu|stepper|heater|fan|probe|temperature|bed_mesh/i.test(name) &&
      value &&
      typeof value === "object",
  );
  const container = byId("hardwareTable");
  container.replaceChildren();
  hardwareRows.forEach(([name, values]) => {
    const summary =
      Object.entries(values)
        .filter(([key]) =>
          /temperature|target|speed|value|position|status|state|offset|current/i.test(
            key,
          ),
        )
        .slice(0, 7)
        .map(
          ([key, value]) =>
            `${key}:${Array.isArray(value) ? value.join(",") : value}`,
        )
        .join(" / ") || "STATUS AVAILABLE";
    appendObjectRow(container, name, summary);
  });
  if (!hardwareRows.length)
    appendEmpty(container, "NO OPTIONAL HARDWARE SENSORS REPORTED");
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
  if (!Object.keys(versions).length)
    appendEmpty(container, "UPDATE STATUS NOT AVAILABLE");
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
  const pending = Object.values(versions).filter((version) => {
    const current = version?.version || version?.current_version;
    return (
      current && version?.remote_version && current !== version.remote_version
    );
  }).length;
  setText("updates", Object.keys(versions).length ? `${pending} PENDING` : "—");
}

function renderQueue(queue) {
  setText("queueState", `QUEUE ${queue.queue_state || "—"}`);
  const container = byId("queueList");
  container.replaceChildren();
  const jobs = queue.queued_jobs || [];
  jobs.forEach((job, index) => {
    const row = document.createElement("div");
    row.className = "queue-row";
    const label = document.createElement("span");
    label.className = "queue-name";
    label.textContent = `${String(index + 1).padStart(2, "0")} / ${
      job.filename || job
    }`;
    const actions = document.createElement("span");
    actions.className = "queue-actions";
    if (job.job_id && index > 0) {
      const jump = document.createElement("button");
      jump.type = "button";
      jump.className = "subtle";
      jump.dataset.queueJump = job.job_id;
      jump.textContent = "TOP";
      actions.appendChild(jump);
    }
    if (job.job_id) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "subtle";
      remove.dataset.queueRemove = job.job_id;
      remove.textContent = "REMOVE";
      actions.appendChild(remove);
    }
    row.append(label, actions);
    container.appendChild(row);
  });
  if (!jobs.length) appendEmpty(container, "QUEUE EMPTY");
}

function renderFiles() {
  const select = byId("fileSel");
  const filter = (byId("fileSearch").value || "").toLowerCase();
  const visibleFiles = lastFiles.filter(
    (file) => !filter || file.path.toLowerCase().includes(filter),
  );
  select.replaceChildren();
  const list = byId("fileList");
  list.replaceChildren();
  if (!visibleFiles.length) {
    appendEmpty(list, filter ? "NO MATCHING FILES" : "NO G-CODE FILES FOUND");
    return;
  }
  visibleFiles.forEach((file) => {
    const option = document.createElement("option");
    option.value = file.path;
    option.textContent = file.path;
    select.appendChild(option);
    const item = document.createElement("button");
    item.type = "button";
    item.className = `file-option${
      file.path === selectedFile ? " selected" : ""
    }`;
    item.dataset.fileOption = file.path;
    const name = document.createElement("span");
    name.textContent = file.path;
    const size = document.createElement("span");
    size.textContent = file.size
      ? `${(Number(file.size) / 1048576).toFixed(1)} MB`
      : "GCODE";
    item.append(name, size);
    list.appendChild(item);
  });
  select.value = selectedFile;
}

function renderPower(devices) {
  const containers = [byId("powerRow")];
  containers.forEach((container) => {
    container.replaceChildren();
    if (!devices.length) {
      appendEmpty(container, "NO POWER DEVICES REPORTED");
      return;
    }
    devices.forEach((device) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `power-toggle${
        device.status === "on" ? " is-active" : ""
      }`;
      button.dataset.action = "power";
      button.dataset.device = device.device;
      button.dataset.powerAction = device.status === "on" ? "off" : "on";
      button.textContent = `${
        device.status === "on" ? "POWER ON" : "POWER OFF"
      } / ${device.device}`;
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
    caption.textContent = `KLIPPER MACRO / ${String(index + 1).padStart(
      2,
      "0",
    )}`;
    button.appendChild(caption);
    return button;
  });
  const full = byId("macroRow");
  full.replaceChildren(
    ...(buttons.length ? buttons : [emptyElement("NO MACROS DISCOVERED")]),
  );
  setText("macroCount", `${macros.length} MACROS`);
  const dashboard = byId("dashboardMacros");
  dashboard.replaceChildren(
    ...(buttons.length
      ? buttons.slice(0, 6).map((button) => button.cloneNode(true))
      : [emptyElement("NO MACROS REPORTED")]),
  );
}

function emptyElement(text) {
  const element = document.createElement("span");
  element.className = "empty-state";
  element.textContent = text;
  return element;
}

function selectFleetPrinter(id) {
  const select = byId("printerSel");
  if (!select || !id || id === printer) return;
  select.value = id;
  switchPrinter();
}

function renderFleet(data) {
  const strip = byId("fleetStrip");
  if (!strip) return;
  const label = byId("fleetLabel");
  const fleet = Array.isArray(data.fleet) ? data.fleet : [];
  const show = fleet.length > 1;
  strip.hidden = !show;
  if (label) label.hidden = !show;
  if (!show) {
    strip.replaceChildren();
    return;
  }
  strip.replaceChildren();
  fleet.forEach((member) => {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = `fleet-tile${
      member.id === data.entry_id ? " active" : ""
    }${member.available === false ? " bad" : ""}`;
    const name = document.createElement("span");
    name.className = "fleet-name";
    name.textContent = member.name || "PRINTER";
    const state = document.createElement("span");
    state.className = "fleet-state";
    const percent = Number.isFinite(Number(member.progress))
      ? ` ${(Number(member.progress) * 100).toFixed(0)}%`
      : "";
    state.textContent =
      member.available === false
        ? "OFFLINE"
        : `${String(member.state || "unknown").toUpperCase()}${percent}`;
    const temps = document.createElement("span");
    temps.className = "fleet-temps";
    temps.textContent = `E ${fmt(member.hotend, 0)}° / B ${fmt(
      member.bed,
      0,
    )}°`;
    const route = document.createElement("span");
    route.className = "fleet-route";
    const scores = (data.router && data.router.scores) || {};
    const routeInfo = scores[member.id];
    if (routeInfo && data.router.needs && data.router.needs.filename) {
      route.textContent = `FIT ${routeInfo.score}`;
      if (routeInfo.reasons && routeInfo.reasons.length) {
        route.title = routeInfo.reasons.join("; ");
      }
    }
    const oee = document.createElement("span");
    oee.className = "fleet-oee";
    const stats = member.oee || {};
    const oeeBits = [];
    if (Number.isFinite(Number(stats.utilization_pct))) {
      oeeBits.push(`U ${fmt(stats.utilization_pct, 0)}%`);
    }
    if (Number.isFinite(Number(stats.success_rate_pct))) {
      oeeBits.push(`OK ${fmt(stats.success_rate_pct, 0)}%`);
    }
    if (Number.isFinite(Number(stats.throughput_gh))) {
      oeeBits.push(`${fmt(stats.throughput_gh, 1)}g/h`);
    }
    oee.textContent = oeeBits.join(" · ");
    tile.append(name, state, route, temps, oee);
    tile.addEventListener("click", () => selectFleetPrinter(member.id));
    strip.appendChild(tile);
  });
}

const HEALTH_PATTERNS = [
  [/shutdown/i, "MCU SHUTDOWN LOGGED", "bad"],
  [/lost communication with mcu/i, "MCU LINK LOST", "bad"],
  [/timer too close/i, "TIMER TOO CLOSE", "warn"],
  [/not heating at expected rate/i, "HEATER UNDERPERFORMING", "warn"],
  [/move out of range/i, "MOVE OUT OF RANGE", "warn"],
  [
    /malformed command|unknown command|unknown pin|pin .* is not/i,
    "COMMAND ERRORS",
    "warn",
  ],
  [/temperature.*(exceed|too high|max)/i, "THERMAL ALERT LOGGED", "bad"],
];

function analyzePrinterHealth(data) {
  const status = data.status || {};
  const lines = Array.isArray(data.gcode_responses) ? data.gcode_responses : [];
  let retransmit = 0;
  let invalid = 0;
  Object.keys(status).forEach((name) => {
    if (!/^mcu/.test(name)) return;
    const stats = status[name]?.last_stats || {};
    retransmit += Number(stats.bytes_retransmit) || 0;
    invalid += Number(stats.bytes_invalid) || 0;
  });
  retransmitHistory.push({ at: Date.now(), total: retransmit + invalid });
  if (retransmitHistory.length > 60) retransmitHistory.shift();
  let trend = "STABLE";
  if (retransmitHistory.length >= 3) {
    const first = retransmitHistory[0];
    if (
      retransmit + invalid > first.total &&
      Date.now() - first.at < 10 * 60 * 1000
    )
      trend = "RISING";
  }
  const findings = [
    {
      severity: retransmit || invalid ? "warn" : "ok",
      label: "MCU RETRANSMIT",
      detail: `${retransmit} B / ${trend}`,
    },
  ];
  HEALTH_PATTERNS.forEach(([regex, label, severity]) => {
    const hits = lines.filter((line) => regex.test(line)).length;
    if (hits) findings.push({ severity, label, detail: `${hits}x` });
  });
  findings.push(...analyzeThermalHealth(status));
  if (lastFlowFinding) findings.push(lastFlowFinding);
  if (!findings.some((finding) => finding.severity !== "ok"))
    findings.push({
      severity: "ok",
      label: "NO CONSOLE FAULTS",
      detail: "CLEAN",
    });
  return findings;
}

function drawRetransmitSpark() {
  const canvas = byId("retransmitSpark");
  const ctx = canvas?.getContext?.("2d");
  if (!ctx) return;
  const width = canvas.width || 600;
  const height = canvas.height || 40;
  ctx.clearRect(0, 0, width, height);
  if (retransmitHistory.length < 2) {
    ctx.fillStyle = cssVar("--muted", "#4c745e");
    ctx.font = "8px monospace";
    ctx.fillText("COLLECTING RETRANSMIT SAMPLES", 8, height / 2 + 3);
    return;
  }
  const values = retransmitHistory.map((point) => point.total);
  const min = Math.min(...values);
  const span = Math.max(1e-9, Math.max(...values) - min);
  ctx.beginPath();
  values.forEach((value, index) => {
    const x = 8 + (index * (width - 16)) / Math.max(1, values.length - 1);
    const y = height - 6 - ((value - min) / span) * (height - 12);
    index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.strokeStyle = cssVar("--cyan", "#39e8bd");
  ctx.stroke();
}

function renderHealth(data) {
  const findings = analyzePrinterHealth(data);
  const container = byId("healthChips");
  if (container) {
    container.replaceChildren();
    findings.forEach((finding) => {
      const chip = document.createElement("span");
      chip.className = `health-chip ${finding.severity}`;
      const label = document.createElement("b");
      label.textContent = finding.label;
      const detail = document.createElement("span");
      detail.textContent = finding.detail;
      chip.append(label, detail);
      container.appendChild(chip);
    });
  }
  const worst = findings.some((finding) => finding.severity === "bad")
    ? "FAULTS LOGGED"
    : findings.some((finding) => finding.severity === "warn")
      ? "WARNINGS"
      : "CLEAN";
  setText("healthSummary", worst);
  drawRetransmitSpark();
}

// ---- bed mesh decay tracking ----

function meshStorageKey() {
  return `nexusMeshV1.${printer || "default"}`;
}

function analyzeMeshDecay(status) {
  const mesh = status.bed_mesh || {};
  const matrix = mesh.mesh_matrix || mesh.probed_matrix;
  if (!Array.isArray(matrix) || !matrix.length || !Array.isArray(matrix[0]))
    return null;
  let stored = null;
  try {
    stored = JSON.parse(
      window.localStorage?.getItem(meshStorageKey()) || "null",
    );
  } catch {
    stored = null;
  }
  const sameShape =
    Array.isArray(stored?.baseline) &&
    stored.baseline.length === matrix.length &&
    stored.baseline.every(
      (row, index) => Array.isArray(row) && row.length === matrix[index].length,
    );
  if (!sameShape) {
    const baseline = matrix.map((row) =>
      row.map((value) => Number(value) || 0),
    );
    try {
      window.localStorage?.setItem(
        meshStorageKey(),
        JSON.stringify({ baseline, at: Date.now() }),
      );
    } catch {
      /* storage full or unavailable */
    }
    return {
      baselineAt: Date.now(),
      rmsDrift: 0,
      maxDrift: 0,
      drift: matrix.map((row) => row.map(() => 0)),
      rows: matrix[0].length,
    };
  }
  let sumSquares = 0;
  let count = 0;
  let maxDrift = 0;
  const drift = matrix.map((row, i) =>
    row.map((value, j) => {
      const delta = Number(value) - Number(stored.baseline[i][j]);
      if (!Number.isFinite(delta)) return 0;
      sumSquares += delta * delta;
      count += 1;
      if (Math.abs(delta) > maxDrift) maxDrift = Math.abs(delta);
      return delta;
    }),
  );
  return {
    baselineAt: stored.at || 0,
    rmsDrift: count ? Math.sqrt(sumSquares / count) : 0,
    maxDrift,
    drift,
    rows: matrix[0].length,
  };
}

function renderMeshDecay(status) {
  const grid = byId("meshDriftMap");
  const summary = byId("meshDriftSummary");
  if (!grid || !summary) return;
  const analysis = analyzeMeshDecay(status);
  if (!analysis) {
    summary.className = "pill";
    summary.textContent = "NO MESH DATA";
    grid.replaceChildren();
    return;
  }
  const due = analysis.rmsDrift >= 0.1 || analysis.maxDrift >= 0.15;
  const warn = !due && (analysis.rmsDrift >= 0.05 || analysis.maxDrift >= 0.08);
  summary.className = `pill ${
    due ? "bad-text" : warn ? "warn-text" : "ok-text"
  }`;
  summary.textContent = due
    ? "RE-LEVEL SUGGESTED"
    : warn
      ? "DRIFT RISING"
      : "MESH STABLE";
  setText(
    "meshBaselineAt",
    analysis.baselineAt
      ? new Date(analysis.baselineAt).toLocaleDateString()
      : "—",
  );
  setText("meshRmsDrift", `${(analysis.rmsDrift * 1000).toFixed(0)} µm`);
  setText("meshMaxDrift", `${(analysis.maxDrift * 1000).toFixed(0)} µm`);
  grid.replaceChildren();
  grid.style.gridTemplateColumns = `repeat(${analysis.rows}, minmax(0, 1fr))`;
  for (const delta of analysis.drift.flat()) {
    const cell = document.createElement("div");
    cell.className = "mesh-cell";
    const magnitude = Math.min(1, Math.abs(delta) / 0.2);
    cell.style.background = `rgba(${statusRgb(delta >= 0 ? "ok" : "bad")}, ${(
      0.08 +
      magnitude * 0.5
    ).toFixed(2)})`;
    cell.title = `${Math.round(delta * 1000)} µm`;
    grid.appendChild(cell);
  }
  renderMeshSurface();
}

function renderMeshSurface() {
  const analysis = latestData?.analysis || {};
  const metrics = analysis.metrics || {};
  const history = Array.isArray(analysis.mesh_history)
    ? analysis.mesh_history
    : [];
  const cornerNames = ["FL", "FR", "BL", "BR"];
  const corners = Array.isArray(metrics.mesh_corner_offsets)
    ? metrics.mesh_corner_offsets
    : [];
  setText(
    "meshCorners",
    corners.length === 4
      ? corners
          .map(
            (value, index) =>
              `${cornerNames[index]} +${(Number(value) || 0).toFixed(2)}`,
          )
          .join(" · ")
      : "—",
  );
  const tiltDelta = Number(metrics.mesh_tilt_delta);
  setText(
    "meshTiltDelta",
    Number.isFinite(tiltDelta) && history.length > 1
      ? `${(tiltDelta * 1000).toFixed(0)} µm`
      : "—",
  );
  const surfaceDelta = Number(metrics.mesh_surface_delta_rms);
  setText(
    "meshSurfaceDelta",
    Number.isFinite(surfaceDelta) && history.length > 1
      ? `${(surfaceDelta * 1000).toFixed(0)} µm`
      : "—",
  );
  setText("meshSnapshots", history.length ? String(history.length) : "—");

  const grid = byId("meshSurfaceMap");
  if (!grid) return;
  grid.replaceChildren();
  const current = history[history.length - 1]?.residuals;
  const previous = history[history.length - 2]?.residuals;
  const sameShape =
    Array.isArray(current) &&
    Array.isArray(previous) &&
    current.length === previous.length &&
    current.every(
      (row, index) =>
        Array.isArray(row) &&
        Array.isArray(previous[index]) &&
        row.length === previous[index].length,
    );
  if (!sameShape) return;
  const rows = current.length;
  const cols = current[0]?.length || 0;
  grid.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
  for (let i = 0; i < rows; i++) {
    for (let j = 0; j < cols; j++) {
      const delta =
        (Number(current[i][j]) || 0) - (Number(previous[i][j]) || 0);
      const cell = document.createElement("div");
      cell.className = "mesh-cell";
      const magnitude = Math.min(1, Math.abs(delta) / 0.1);
      cell.style.background = `rgba(${statusRgb(
        delta >= 0 ? "ok" : "bad",
      )}, ${(0.08 + magnitude * 0.5).toFixed(2)})`;
      cell.title = `${Math.round(delta * 1000)} µm`;
      grid.appendChild(cell);
    }
  }
}

function resetMeshBaseline() {
  const mesh = latestData?.status?.bed_mesh || {};
  const matrix = mesh.mesh_matrix || mesh.probed_matrix;
  if (!Array.isArray(matrix) || !matrix.length) {
    toast("NO ACTIVE BED MESH TO BASELINE");
    return;
  }
  try {
    window.localStorage?.setItem(
      meshStorageKey(),
      JSON.stringify({
        baseline: matrix.map((row) => row.map((value) => Number(value) || 0)),
        at: Date.now(),
      }),
    );
  } catch {
    /* storage unavailable */
  }
  toast("MESH BASELINE RESET");
  if (latestData?.status) renderMeshDecay(latestData.status);
}

// ---- thermal health sentinel ----

let thermalSamples = {};

function heaterObjects(status) {
  const heaters = [];
  if (status.extruder) heaters.push(["EXTRUDER", status.extruder]);
  if (status.heater_bed) heaters.push(["BED", status.heater_bed]);
  for (const name of Object.keys(status)) {
    if (name.startsWith("heater_generic "))
      heaters.push([name.slice(15).toUpperCase(), status[name]]);
  }
  return heaters;
}

function analyzeThermalHealth(status) {
  const findings = [];
  const now = Date.now();
  for (const [label, heater] of heaterObjects(status)) {
    const temperature = Number(heater?.temperature);
    const duty = Number(heater?.power);
    const target = Number(heater?.target);
    if (!Number.isFinite(temperature) || !Number.isFinite(duty)) continue;
    const history = (thermalSamples[label] = (thermalSamples[label] || [])
      .concat({ at: now, t: temperature, p: duty })
      .slice(-120));
    if (history.length < 20 || !Number.isFinite(target) || target <= 5)
      continue;
    const recent = history.slice(-15);
    const meanDuty =
      recent.reduce((sum, sample) => sum + sample.p, 0) / recent.length;
    const slope = recent[recent.length - 1].t - recent[0].t;
    if (meanDuty > 0.95 && slope < -1) {
      findings.push({
        severity: "bad",
        label: `${label} SATURATED`,
        detail: "100% DUTY, TEMP FALLING",
      });
      continue;
    }
    const window = history.slice(-60);
    const temps = window.map((sample) => sample.t);
    const amplitude = Math.max(...temps) - Math.min(...temps);
    let crossings = 0;
    for (let i = 1; i < temps.length; i += 1) {
      if ((temps[i - 1] - target) * (temps[i] - target) < 0) crossings += 1;
    }
    if (amplitude > 3 && crossings >= 6) {
      findings.push({
        severity: "warn",
        label: `${label} PID OSCILLATION`,
        detail: `±${fmt(amplitude / 2, 1)}°C AROUND TARGET`,
      });
    }
  }
  return findings;
}

// ---- volumetric flow headroom ----

const FILAMENT_AREA_MM2 = (Math.PI * 1.75 * 1.75) / 4;
let maxFlowMm3 = 15;
let flowSaturatedSince = null;
let lastFlowFinding = null;

function loadFlowPrefs() {
  try {
    const stored = JSON.parse(
      window.localStorage?.getItem(`nexusMaxFlow.${printer || "default"}`) ||
        "null",
    );
    maxFlowMm3 = Number(stored) > 0 ? Number(stored) : 15;
  } catch {
    maxFlowMm3 = 15;
  }
  const input = byId("maxFlowInput");
  if (input) input.value = String(maxFlowMm3);
}

function saveFlowPrefs() {
  const input = byId("maxFlowInput");
  const value = Number(input?.value);
  if (Number.isFinite(value) && value > 0) maxFlowMm3 = value;
  try {
    window.localStorage?.setItem(
      `nexusMaxFlow.${printer || "default"}`,
      JSON.stringify(maxFlowMm3),
    );
  } catch {
    /* storage unavailable */
  }
}

function volumetricFlow(status) {
  const velocity = Number(status.motion_report?.live_extruder_velocity);
  if (!Number.isFinite(velocity) || velocity <= 0) return 0;
  return velocity * FILAMENT_AREA_MM2;
}

function renderFlowHeadroom(status) {
  const mm3 = volumetricFlow(status);
  setText("flowVolumetric", `${fmt(mm3, 1)} mm³/s`);
  setText("flowMaxRate", `${fmt(maxFlowMm3, 1)} mm³/s`);
  const ratio = maxFlowMm3 > 0 ? mm3 / maxFlowMm3 : 0;
  const headroom = Math.max(0, 100 - ratio * 100);
  setText("flowHeadroom", `${fmt(headroom, 0)}%`);
  const bar = byId("flowHeadroomBar");
  if (bar) bar.style.width = `${Math.min(100, ratio * 100)}%`;
  const pill = byId("flowHeadroomPill");
  if (pill) {
    pill.className = `pill ${
      ratio >= 0.95 ? "bad-text" : ratio >= 0.8 ? "warn-text" : "ok-text"
    }`;
    pill.textContent =
      mm3 <= 0
        ? "IDLE"
        : ratio >= 0.95
          ? "AT MELT LIMIT"
          : ratio >= 0.8
            ? "HIGH FLOW"
            : "HEADROOM OK";
  }
  if (ratio >= 0.95 && mm3 > 0) {
    if (!flowSaturatedSince) flowSaturatedSince = Date.now();
  } else {
    flowSaturatedSince = null;
  }
  return flowSaturatedSince && Date.now() - flowSaturatedSince >= 5000
    ? {
        severity: "warn",
        label: "FLOW SATURATED",
        detail: `${fmt(mm3, 1)} mm³/s AT MELT LIMIT`,
      }
    : null;
}

// ---- energy & cost accounting ----

let energyPrefs = { sensor: "", rate: 0 };
let energySession = { file: "", kwh: 0, lastAt: 0 };

function loadEnergyPrefs() {
  try {
    const stored = JSON.parse(
      window.localStorage?.getItem(`nexusEnergy.${printer || "default"}`) ||
        "null",
    );
    energyPrefs = {
      sensor: stored?.sensor || "",
      rate: Number(stored?.rate) > 0 ? Number(stored.rate) : 0,
    };
  } catch {
    energyPrefs = { sensor: "", rate: 0 };
  }
  const sensor = byId("energySensor");
  const rate = byId("energyRate");
  if (sensor) sensor.value = energyPrefs.sensor;
  if (rate) rate.value = energyPrefs.rate > 0 ? String(energyPrefs.rate) : "";
}

function saveEnergyPrefs() {
  energyPrefs = {
    sensor: byId("energySensor")?.value || "",
    rate: Number(byId("energyRate")?.value) || 0,
  };
  try {
    window.localStorage?.setItem(
      `nexusEnergy.${printer || "default"}`,
      JSON.stringify(energyPrefs),
    );
  } catch {
    /* storage unavailable */
  }
  updateEnergy(latestData);
}

function readPowerWatts() {
  if (!energyPrefs.sensor) return null;
  const entity = window.hass?.states?.[energyPrefs.sensor];
  const raw = Number(entity?.state);
  if (!Number.isFinite(raw)) return null;
  const unit = String(entity?.attributes?.unit_of_measurement || "W");
  return unit.toLowerCase() === "kw" ? raw * 1000 : raw;
}

function updateEnergy(data) {
  const watts = readPowerWatts();
  const statusPill = byId("energyStatus");
  if (statusPill) {
    statusPill.className = `pill ${watts === null ? "" : "ok-text"}`;
    statusPill.textContent = watts === null ? "NO SENSOR" : "TRACKING";
  }
  setText("energyNow", watts === null ? "NO SENSOR" : `${fmt(watts, 0)} W`);
  const now = Date.now();
  const state = data?.status?.print_stats?.state || "";
  const filename = data?.status?.print_stats?.filename || "";
  const active = state === "printing" || state === "paused";
  if (active && watts !== null) {
    if (energySession.file !== filename)
      energySession = { file: filename, kwh: 0, lastAt: now };
    const dtHours = (now - energySession.lastAt) / 3600000;
    if (dtHours > 0 && dtHours < 1)
      energySession.kwh += (watts * dtHours) / 1000;
    energySession.lastAt = now;
  }
  setText(
    "energyPrint",
    energySession.file ? `${fmt(energySession.kwh * 1000, 0)} Wh` : "—",
  );
  setText(
    "energyCost",
    energySession.file && energyPrefs.rate > 0
      ? `$${fmt(energySession.kwh * energyPrefs.rate, 2)}`
      : "—",
  );
}

function populateEnergyEntities() {
  const select = byId("energySensor");
  if (!select || select.dataset.populated) return;
  const states = window.hass?.states || {};
  for (const entityId of Object.keys(states).sort()) {
    if (!entityId.startsWith("sensor.")) continue;
    const unit = String(
      states[entityId]?.attributes?.unit_of_measurement || "",
    ).toLowerCase();
    const deviceClass = states[entityId]?.attributes?.device_class;
    if (deviceClass !== "power" && unit !== "w" && unit !== "kw") continue;
    const option = document.createElement("option");
    option.value = entityId;
    option.textContent =
      states[entityId]?.attributes?.friendly_name || entityId;
    select.appendChild(option);
  }
  select.dataset.populated = "1";
  select.value = energyPrefs.sensor;
}

const MAINTENANCE_DEFAULTS = [
  { name: "NOZZLE", kind: "hours", limit: 500 * 3600 },
  { name: "PTFE TUBE", kind: "hours", limit: 300 * 3600 },
  { name: "BELT CHECK", kind: "hours", limit: 200 * 3600 },
  { name: "LUBE RAILS", kind: "hours", limit: 100 * 3600 },
  { name: "PTFE WEAR", kind: "filament", limit: 5000 },
];

function maintenanceStorageKey() {
  return `nexusMaintV1.${printer || "default"}`;
}

function maintenanceItems(printSeconds, filamentMeters) {
  let stored = null;
  try {
    stored = JSON.parse(
      window.localStorage?.getItem(maintenanceStorageKey()) || "null",
    );
  } catch {
    stored = null;
  }
  if (!Array.isArray(stored) || stored.length !== MAINTENANCE_DEFAULTS.length) {
    stored = MAINTENANCE_DEFAULTS.map((item) => ({
      ...item,
      baseline: item.kind === "filament" ? filamentMeters : printSeconds,
    }));
    try {
      window.localStorage?.setItem(
        maintenanceStorageKey(),
        JSON.stringify(stored),
      );
    } catch {
      /* storage unavailable */
    }
  }
  return stored;
}

function resetMaintenanceItem(index, printSeconds, filamentMeters) {
  const items = maintenanceItems(printSeconds, filamentMeters);
  const item = items[index];
  if (!item) return;
  item.baseline = item.kind === "filament" ? filamentMeters : printSeconds;
  try {
    window.localStorage?.setItem(
      maintenanceStorageKey(),
      JSON.stringify(items),
    );
  } catch {
    /* storage unavailable */
  }
  renderMaintenance(latestData || {});
}

function renderMaintenance(data) {
  const container = byId("maintenanceList");
  if (!container) return;
  const totals = (data.history || {}).job_totals || {};
  const printSeconds =
    Number(totals.total_print_time ?? totals.total_time) || 0;
  const filamentMeters = (Number(totals.total_filament_used) || 0) / 1000;
  const items = maintenanceItems(printSeconds, filamentMeters);
  container.replaceChildren();
  let dueCount = 0;
  items.forEach((item, index) => {
    const current = item.kind === "filament" ? filamentMeters : printSeconds;
    const used = Math.max(0, current - (Number(item.baseline) || 0));
    const remaining = Math.max(0, item.limit - used);
    const due = remaining <= 0;
    if (due) dueCount += 1;
    const row = document.createElement("div");
    row.className = `maint-row${due ? " due" : ""}`;
    const name = document.createElement("span");
    name.className = "maint-name";
    name.textContent = item.name;
    const track = document.createElement("div");
    track.className = "maint-track";
    const fill = document.createElement("i");
    fill.style.width = `${Math.min(100, (used / item.limit) * 100)}%`;
    track.appendChild(fill);
    const remain = document.createElement("span");
    remain.className = "maint-remain";
    remain.textContent =
      item.kind === "filament"
        ? `${fmt(remaining, 0)} M LEFT`
        : `${fmt(remaining / 3600, 0)} H LEFT`;
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "subtle";
    reset.textContent = "RESET";
    reset.addEventListener("click", () =>
      resetMaintenanceItem(index, printSeconds, filamentMeters),
    );
    row.append(name, track, remain, reset);
    container.appendChild(row);
  });
  setText(
    "maintSummary",
    dueCount ? `${dueCount} SERVICE${dueCount > 1 ? "S" : ""} DUE` : "ALL OK",
  );
}

function resolveCameraAssignments(available, assignments, tileCount) {
  for (let index = 0; index < tileCount; index++) {
    if (
      assignments[index] === undefined ||
      (assignments[index] &&
        !available.some((camera) => camera.name === assignments[index]))
    ) {
      assignments[index] = available[index]?.name || "";
    }
  }
  return assignments;
}

function cameraFor(available, name) {
  return available.find((camera) => camera.name === name) || null;
}

function setCameraImage(image, camera, active) {
  const streamActive = active && Boolean(camera?.stream_url);
  image.style.display = streamActive ? "block" : "none";
  if (streamActive && image.dataset.streamUrl !== camera.stream_url) {
    image.src = camera.stream_url;
    image.dataset.streamUrl = camera.stream_url;
  } else if (!streamActive) {
    image.removeAttribute("src");
    delete image.dataset.streamUrl;
  }
  return streamActive;
}

function dashboardCameraCount() {
  return Math.min(Number(dashboardCameraLayout) || 1, 4);
}

function dashboardCameraStorageKey() {
  return `nexus-dashboard-cameras:${printer || "default"}`;
}

function loadDashboardCameraPrefs() {
  const key = dashboardCameraStorageKey();
  if (dashboardCameraPrefsKey === key) return;
  dashboardCameraPrefsKey = key;
  dashboardCameraLayout = "1";
  dashboardCameraAssignments = [];
  try {
    const saved = JSON.parse(window.localStorage?.getItem(key) || "null");
    if (["1", "2", "4"].includes(String(saved?.layout)))
      dashboardCameraLayout = String(saved.layout);
    if (Array.isArray(saved?.assignments))
      dashboardCameraAssignments = saved.assignments.slice(0, 4).map(String);
  } catch (_error) {
    // Preferences are optional; unavailable storage falls back to automatic selection.
  }
  dashboardCameraSignature = "";
}

function saveDashboardCameraPrefs() {
  try {
    resolveCameraAssignments(
      availableWebcams,
      dashboardCameraAssignments,
      dashboardCameraCount(),
    );
    window.localStorage?.setItem(
      dashboardCameraStorageKey(),
      JSON.stringify({
        layout: dashboardCameraLayout,
        assignments: dashboardCameraAssignments.slice(0, 4),
      }),
    );
  } catch (_error) {
    // Dashboard camera choices still apply for this session if storage is unavailable.
  }
}

function renderDashboardCameras() {
  const panel = byId("webcamCard");
  const grid = byId("dashboardCameraGrid");
  if (!panel || !grid) return;
  const dashboardVisible = activeScreen === "dashboard";
  const tileCount = dashboardCameraCount();
  resolveCameraAssignments(
    availableWebcams,
    dashboardCameraAssignments,
    tileCount,
  );
  const sourceSignature = availableWebcams
    .map(
      (camera) => `${camera.name}:${camera.stream_url}:${camera.snapshot_url}`,
    )
    .join("|");
  const signature = `${dashboardCameraLayout}/${sourceSignature}`;
  if (signature !== dashboardCameraSignature) {
    dashboardCameraSignature = signature;
    grid.replaceChildren();
    for (let index = 0; index < tileCount; index++) {
      const tile = document.createElement("section");
      tile.className = "dashboard-camera-tile";
      tile.dataset.dashboardTile = String(index);
      const header = document.createElement("div");
      header.className = "camera-tile-head";
      const title = document.createElement("span");
      title.className = "micro";
      title.dataset.dashboardCameraTitle = String(index);
      const fullscreen = document.createElement("button");
      fullscreen.type = "button";
      fullscreen.dataset.cameraFullscreen = "";
      fullscreen.textContent = "FULLSCREEN";
      header.append(title, fullscreen);
      const image = document.createElement("img");
      image.alt = `Printer camera ${index + 1}`;
      image.loading = "lazy";
      const placeholder = document.createElement("div");
      placeholder.className = "camera-tile-empty";
      tile.append(header, image, placeholder);
      grid.appendChild(tile);
    }
  }
  grid.dataset.layout = String(tileCount);
  Array.from(grid.querySelectorAll(".dashboard-camera-tile")).forEach(
    (tile, index) => {
      const camera = cameraFor(
        availableWebcams,
        dashboardCameraAssignments[index],
      );
      const streamActive = setCameraImage(
        tile.querySelector("img"),
        camera,
        dashboardVisible,
      );
      const placeholder = tile.querySelector(".camera-tile-empty");
      placeholder.textContent = !camera?.name
        ? "NO CAMERA ASSIGNED"
        : !camera.stream_url
          ? "STREAM UNAVAILABLE"
          : "STREAM PAUSED / OPEN DASHBOARD";
      placeholder.style.display = streamActive ? "none" : "grid";
      tile.querySelector("[data-dashboard-camera-title]").textContent =
        camera?.name || "NO CAMERA";
      tile.querySelector("[data-camera-fullscreen]").disabled = !streamActive;
    },
  );
  panel.style.display =
    dashboardVisible && availableWebcams.length ? "" : "none";
  setText(
    "dashboardCameraStatus",
    availableWebcams.length
      ? `${availableWebcams.length} SOURCES / ${tileCount} TILES`
      : "CAMERA SOURCE NOT CONFIGURED",
  );
}

function renderDashboardCameraConfig() {
  const list = byId("dashboardCameraOptions");
  if (!list) return;
  const tileCount = dashboardCameraCount();
  resolveCameraAssignments(
    availableWebcams,
    dashboardCameraAssignments,
    tileCount,
  );
  const layoutSelect = byId("dashboardCameraLayout");
  if (layoutSelect) layoutSelect.value = dashboardCameraLayout;
  list.replaceChildren();
  for (let index = 0; index < tileCount; index++) {
    const label = document.createElement("label");
    label.className = "config-row";
    const text = document.createElement("span");
    text.textContent = `TILE ${index + 1}`;
    const select = document.createElement("select");
    select.dataset.dashboardCameraSlot = String(index);
    select.setAttribute("aria-label", `Dashboard camera tile ${index + 1}`);
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "NO CAMERA";
    select.appendChild(emptyOption);
    availableWebcams.forEach((camera) => {
      const option = document.createElement("option");
      option.value = camera.name;
      option.textContent = camera.name;
      select.appendChild(option);
    });
    select.value =
      cameraFor(availableWebcams, dashboardCameraAssignments[index])?.name ||
      "";
    label.append(text, select);
    list.appendChild(label);
  }
  setText(
    "dashboardCameraSummary",
    `${availableWebcams.length} SOURCES / ${tileCount} TILES`,
  );
}

function openCameraConfig() {
  cameraConfigOpen = true;
  renderDashboardCameraConfig();
  byId("cameraConfig").hidden = false;
  byId("cameraConfigScrim").hidden = false;
  byId("cameraConfig").setAttribute("aria-hidden", "false");
  byId("dashboardCameraLayout")?.focus?.();
}

function closeCameraConfig() {
  cameraConfigOpen = false;
  byId("cameraConfig").hidden = true;
  byId("cameraConfigScrim").hidden = true;
  byId("cameraConfig").setAttribute("aria-hidden", "true");
}

function renderCamera(webcams) {
  availableWebcams = Array.isArray(webcams)
    ? webcams.map((camera, index) => ({
        ...(camera || {}),
        name: String(camera?.name || `Camera ${index + 1}`),
      }))
    : [];
  loadDashboardCameraPrefs();
  const cameraPageVisible = activeScreen === "camera";
  const layoutSelect = byId("cameraLayout");
  if (layoutSelect?.value) cameraLayout = layoutSelect.value;
  const tileCount = cameraLayout === "2x2" ? 4 : cameraLayout === "1x2" ? 2 : 1;
  resolveCameraAssignments(availableWebcams, cameraAssignments, tileCount);

  const grid = byId("cameraGrid");
  const sourceSignature = availableWebcams
    .map(
      (camera) => `${camera.name}:${camera.stream_url}:${camera.snapshot_url}`,
    )
    .join("|");
  const signature = `${cameraLayout}/${sourceSignature}`;
  grid.dataset.layout = cameraLayout;
  grid.style.display = availableWebcams.length ? "grid" : "none";
  grid.style.gridTemplateColumns =
    cameraLayout === "1x1" ? "minmax(0,1fr)" : "repeat(2,minmax(0,1fr))";
  if (signature !== cameraGridSignature) {
    cameraGridSignature = signature;
    grid.replaceChildren();
    for (let index = 0; index < tileCount; index++) {
      const tile = document.createElement("section");
      tile.className = "camera-tile";
      const header = document.createElement("div");
      header.className = "camera-tile-head";
      const selector = document.createElement("select");
      selector.dataset.cameraSlot = String(index);
      selector.setAttribute("aria-label", `Camera tile ${index + 1}`);
      const emptyOption = document.createElement("option");
      emptyOption.value = "";
      emptyOption.textContent = "NO CAMERA";
      selector.appendChild(emptyOption);
      availableWebcams.forEach((camera) => {
        const option = document.createElement("option");
        option.value = camera.name;
        option.textContent = camera.name;
        selector.appendChild(option);
      });
      const fullscreen = document.createElement("button");
      fullscreen.type = "button";
      fullscreen.dataset.cameraFullscreen = "";
      fullscreen.textContent = "FULLSCREEN";
      header.append(selector, fullscreen);
      const image = document.createElement("img");
      image.alt = `Printer camera ${index + 1}`;
      image.loading = "lazy";
      const placeholder = document.createElement("div");
      placeholder.className = "camera-tile-empty";
      placeholder.textContent = "NO CAMERA ASSIGNED";
      const footer = document.createElement("div");
      footer.className = "camera-tile-actions";
      const cameraStatus = document.createElement("span");
      cameraStatus.className = "micro";
      cameraStatus.dataset.cameraStatus = String(index);
      const snapshot = document.createElement("button");
      snapshot.type = "button";
      snapshot.className = "subtle";
      snapshot.dataset.cameraSnapshot = String(index);
      snapshot.textContent = "SNAPSHOT";
      footer.append(cameraStatus, snapshot);
      tile.append(header, image, placeholder, footer);
      grid.appendChild(tile);
    }
  }

  const tiles = Array.from(grid.querySelectorAll(".camera-tile"));
  tiles.forEach((tile, index) => {
    const selector = tile.querySelector("[data-camera-slot]");
    const camera = availableWebcams.find(
      (item) => item.name === cameraAssignments[index],
    );
    selector.value = camera?.name || "";
    const image = tile.querySelector("img");
    const placeholder = tile.querySelector(".camera-tile-empty");
    const streamActive = setCameraImage(image, camera, cameraPageVisible);
    placeholder.textContent = !camera?.name
      ? "NO CAMERA ASSIGNED"
      : !camera.stream_url
        ? "STREAM UNAVAILABLE"
        : "STREAM PAUSED / OPEN CAMERA PAGE";
    placeholder.style.display = streamActive ? "none" : "grid";
    const fullscreenButton = tile.querySelector("[data-camera-fullscreen]");
    fullscreenButton.disabled = !streamActive;
    const snapshotButton = tile.querySelector("[data-camera-snapshot]");
    snapshotButton.disabled = !camera?.snapshot_url;
    if (camera?.snapshot_url)
      snapshotButton.dataset.snapshotUrl = camera.snapshot_url;
    else delete snapshotButton.dataset.snapshotUrl;
    tile.querySelector("[data-camera-status]").textContent = camera?.name
      ? `SOURCE / ${camera.name}`
      : "UNASSIGNED";
  });

  renderDashboardCameras();
  if (cameraConfigOpen) renderDashboardCameraConfig();
  const primary =
    cameraFor(availableWebcams, cameraAssignments[0]) || availableWebcams[0];
  byId("cameraEmpty").style.display = availableWebcams.length ? "none" : "grid";
  setText(
    "cameraName",
    primary?.name
      ? `PRIMARY / ${primary.name}`
      : "CAMERA SOURCE NOT CONFIGURED",
  );
  setText(
    "cameraGridStatus",
    `${availableWebcams.length} CAMERAS / ${tileCount} TILES`,
  );
  setText("networkCameras", String(availableWebcams.length));
}

function renderConsole(lines) {
  const signature = lines.join("\n");
  if (signature === consoleSignature) return;
  const output = byId("console");
  output.textContent = signature;
  output.scrollTop = output.scrollHeight;
  consoleSignature = signature;
}

function recordSentCommand(command) {
  const normalized = String(command || "").trim();
  if (!normalized) return;
  sentCommandHistory.unshift({
    printer,
    time: new Date(),
    command: normalized,
  });
  sentCommandHistory = sentCommandHistory.slice(0, 100);
  renderSentCommandHistory();
}

function renderSentCommandHistory() {
  const history = byId("commandHistory");
  if (!history) return;
  history.replaceChildren();
  const entries = sentCommandHistory.filter(
    (entry) => entry.printer === printer,
  );
  setText("commandHistoryCount", `${entries.length} COMMANDS`);
  if (!entries.length) {
    appendEmpty(
      history,
      "COMMANDS SENT FROM THIS PRINTER SESSION WILL APPEAR HERE",
    );
    return;
  }
  entries.forEach((entry) => {
    const row = document.createElement("div");
    row.className = "command-entry";
    const timestamp = document.createElement("time");
    timestamp.textContent = entry.time.toLocaleTimeString([], {
      hour12: false,
    });
    const command = document.createElement("code");
    command.textContent = entry.command;
    row.append(timestamp, command);
    history.appendChild(row);
  });
}

async function act(action, value, preset, extra) {
  if (updateStaleness() && !STALE_EXEMPT_ACTIONS.has(action)) {
    toast("TELEMETRY STALE — COMMANDS HELD UNTIL THE LINK RESTORES");
    return;
  }
  const body = { entry_id: printer, action };
  if (
    [
      "set_speed",
      "set_flow",
      "set_fan",
      "set_extruder",
      "set_bed",
      "z_adjust",
      "z_set",
    ].includes(action)
  ) {
    if (value === "" || value == null || Number.isNaN(Number(value))) {
      toast("Enter a valid numeric value.");
      return;
    }
    body.value = Number(value);
  }
  if (preset) body.preset = preset;
  if (
    ["print_file", "select_file", "enqueue_file", "delete_file"].includes(
      action,
    )
  )
    body.filename = value;
  if (extra) Object.assign(body, extra);
  try {
    const result = await hassApi().callApi("POST", API.action, body);
    if (result.ok && ["run_gcode", "run_macro"].includes(action)) {
      recordSentCommand(extra?.script || value);
    }
    if (action === "emergency_stop") {
      toast(
        result.ok
          ? "EMERGENCY STOP DELIVERED"
          : `E-STOP DELIVERY FAILED / ${result.error || "REQUEST REJECTED"}`,
        6000,
      );
    } else {
      toast(
        result.ok
          ? `COMMAND OK / ${action.toUpperCase()}`
          : `COMMAND ERROR / ${result.error || action}`,
      );
    }
    refresh();
  } catch (error) {
    toast(
      action === "emergency_stop"
        ? `E-STOP DELIVERY FAILED / ${error.message || "request failed"}`
        : `COMMAND ERROR / ${error.message || "request failed"}`,
      action === "emergency_stop" ? 6000 : 3200,
    );
  }
}

function dispatchAction(button) {
  const action = button.dataset.action;
  if (!action) return;
  if (button.dataset.confirm && !confirm(button.dataset.confirm)) return;
  if (
    action === "start_queue" &&
    isQuietTime() &&
    Date.now() > queueQuietOverrideUntil
  ) {
    queueQuietOverrideUntil = Date.now() + 8000;
    toast("QUIET HOURS ACTIVE — PRESS START QUEUE AGAIN TO OVERRIDE", 6000);
    return;
  }
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
  if (button.dataset.powerAction)
    extra.power_action = button.dataset.powerAction;
  if (action === "jog") {
    extra.axis = button.dataset.axis;
    extra.dist = Number(button.dataset.dir) * jogStep;
  }
  if (action === "set_fan" && button.dataset.scale === "fan-percent")
    value = Math.round(Number(value) * 2.55);
  if (
    ["print_file", "enqueue_file", "delete_file"].includes(action) &&
    !value
  ) {
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
    const response = await hassApi().fetchWithAuth(API.upload, {
      method: "POST",
      body: form,
    });
    const result = await response.json().catch(() => ({}));
    toast(
      response.ok
        ? `UPLOAD OK / ${result.filename || file.name}`
        : `UPLOAD ERROR / ${result.error || response.status}`,
    );
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
  renderSentCommandHistory();
  latestData = null;
  availableWebcams = [];
  cameraAssignments = [];
  cameraGridSignature = "";
  renderCamera(availableWebcams);
  selectedFile = "";
  lastThumbnailKey = "";
  toolpathKey = "";
  toolpathReady = false;
  toolpathLoading = false;
  toolpathRequested = false;
  toolpathSegments = [];
  toolpathLayerStats = [];
  toolpathSimSeconds = 0;
  if (toolpathAbort) toolpathAbort.abort();
  void resetPanelPush();
  resetLiveTracking();
  alertState = {
    seeded: false,
    state: "",
    milestone: -1,
    filamentOk: true,
    klippy: "",
    lastKey: "",
    lastAt: 0,
  };
  alertPrefsKey = "";
  extHist = [];
  bedHist = [];
  retransmitHistory = [];
  thermalSamples = {};
  energySession = { file: "", kwh: 0, lastAt: 0 };
  flowSaturatedSince = null;
  lastFlowFinding = null;
  loadFlowPrefs();
  loadEnergyPrefs();
  renderToolpathStatus("WAITING FOR PRINTER DATA");
  refresh();
}

function detailRowsForScreen(name, data) {
  const status = data.status || {};
  const printStats = status.print_stats || {};
  const printerInfo = data.printer_info || {};
  const meta = data.meta || {};
  const rows = [];
  const add = (label, value) => {
    if (value === undefined || value === null || value === "") return;
    const formatted = Array.isArray(value) ? value.join(", ") : String(value);
    rows.push([label, formatted]);
  };
  const addObjects = (pattern) => {
    Object.entries(status).forEach(([objectName, values]) => {
      if (!pattern.test(objectName) || !values || typeof values !== "object")
        return;
      const fields = Object.entries(values)
        .filter(
          ([key, value]) =>
            /temperature|target|power|speed|rpm|position|state|status|offset|value/i.test(
              key,
            ) && value != null,
        )
        .slice(0, 8);
      if (fields.length)
        add(
          objectName,
          fields
            .map(
              ([key, value]) =>
                `${key}: ${Array.isArray(value) ? value.join(",") : value}`,
            )
            .join(" / "),
        );
    });
  };

  if (name === "dashboard" || name === "print") {
    add("Print state", printStats.state);
    add("Active file", printStats.filename || status.virtual_sdcard?.file_path);
    add("Print duration", duration(printStats.print_duration));
    add(
      "Current / total layer",
      `${printStats.info?.current_layer ?? "—"} / ${
        printStats.info?.total_layer ?? meta.layer_count ?? "—"
      }`,
    );
    add("Estimated duration", duration(meta.estimated_time));
    add(
      "Object height",
      meta.object_height == null ? null : `${fmt(meta.object_height, 2)} mm`,
    );
    add(
      "Filament estimate",
      meta.filament_total == null
        ? null
        : `${fmt(Number(meta.filament_total) / 1000, 2)} m`,
    );
    add(
      "Toolhead XYZ",
      status.toolhead?.position?.slice(0, 3).map((value) => fmt(value, 2)),
    );
    add("Homed axes", status.toolhead?.homed_axes);
  } else if (name === "movement") {
    add(
      "Machine position",
      status.toolhead?.position?.slice(0, 3).map((value) => fmt(value, 2)),
    );
    add("Homed axes", status.toolhead?.homed_axes);
    add("Move speed", status.gcode_move?.speed);
    add("Speed factor", status.gcode_move?.speed_factor);
    add(
      "Coordinate mode",
      status.gcode_move?.absolute_coordinates ? "ABSOLUTE" : "RELATIVE",
    );
    addObjects(/endstop|probe/i);
  } else if (name === "thermal") {
    addObjects(
      /^(extruder\d*|heater_bed|heater_generic|temperature_sensor|temperature_fan|fan|controller_fan|heater_fan)/i,
    );
  } else if (name === "extruder") {
    addObjects(/^(extruder\d*|filament_switch_sensor|filament_motion_sensor)/i);
    add("Flow factor", status.gcode_move?.extrude_factor);
    add(
      "Filament used",
      printStats.filament_used == null
        ? null
        : `${fmt(Number(printStats.filament_used) / 1000, 2)} m`,
    );
    add("Active tool", status.toolhead?.extruder);
  } else if (name === "bedmesh") {
    const mesh = status.bed_mesh || {};
    const matrix = Array.isArray(mesh.mesh_matrix)
      ? mesh.mesh_matrix.flat().map(Number).filter(Number.isFinite)
      : [];
    add("Profile", mesh.profile_name);
    add(
      "Mesh dimensions",
      mesh.mesh_matrix?.length
        ? `${mesh.mesh_matrix.length} × ${mesh.mesh_matrix[0]?.length || 0}`
        : null,
    );
    add(
      "Mesh min / max",
      matrix.length
        ? `${fmt(Math.min(...matrix), 4)} / ${fmt(Math.max(...matrix), 4)}`
        : null,
    );
    add("Probe", status.probe?.last_query);
    add("Homed axes", status.toolhead?.homed_axes);
  } else if (name === "tuning") {
    addObjects(/input_shaper|resonance_tester/i);
    add("Speed factor", status.gcode_move?.speed_factor);
    add("Flow factor", status.gcode_move?.extrude_factor);
    add("Max velocity", status.toolhead?.max_velocity);
    add("Max acceleration", status.toolhead?.max_accel);
  } else if (name === "macros") {
    add("Discovered macros", (data.macros || []).join(", ") || "None");
    add("Klippy state", printerInfo.klippy_state);
  } else if (name === "files") {
    const selected = (data.files || []).find(
      (file) => file.path === data.selected_file,
    );
    add("G-code file count", data.files?.length ?? 0);
    add("Selected file", data.selected_file);
    add(
      "Selected file size",
      selected?.size == null
        ? null
        : `${fmt(Number(selected.size) / 1048576, 2)} MB`,
    );
    add("Last modified", selected?.modified);
  } else if (name === "history") {
    Object.entries(data.history?.job_totals || {}).forEach(([key, value]) =>
      add(key.replace(/_/g, " "), value),
    );
  } else if (name === "camera") {
    add("Configured cameras", (data.webcams || []).length);
    (data.webcams || []).forEach((camera) =>
      add(
        camera.name,
        `STREAM ${camera.stream_url ? "AVAILABLE" : "MISSING"} / SNAPSHOT ${
          camera.snapshot_url ? "AVAILABLE" : "MISSING"
        }`,
      ),
    );
  } else if (name === "console") {
    add("Buffered G-code responses", data.gcode_responses?.length ?? 0);
    add(
      "Panel-session commands",
      sentCommandHistory.filter((entry) => entry.printer === printer).length,
    );
    add("Klippy state", printerInfo.klippy_state);
  } else if (name === "hardware") {
    (data.power_devices || []).forEach((device) =>
      add(
        `POWER / ${device.device}`,
        `${device.status || "UNKNOWN"}${
          device.locked_while_printing ? " / LOCKED WHILE PRINTING" : ""
        }`,
      ),
    );
    addObjects(/mcu|stepper|probe|sensor|fan|heater/i);
  } else if (name === "system") {
    add("Klippy state", printerInfo.klippy_state);
    add("Software version", printerInfo.software_version);
    add("System provider", data.system_info?.provider);
    add(
      "CPU model",
      data.system_info?.cpu_info?.model || data.system_info?.cpu_info?.cpu_desc,
    );
    add("Integration version", data.integration_version);
  } else if (name === "network") {
    const settings = data.settings || {};
    add(
      "Printer endpoint",
      settings.host ? `${settings.host}:${settings.port}` : null,
    );
    add("TLS", settings.tls ? "ENABLED" : "DISABLED");
    add(
      "API key",
      data.api_key_configured ? "CONFIGURED / VALUE HIDDEN" : "NOT CONFIGURED",
    );
    add("WebSocket push", "Moonraker status subscription");
  } else if (name === "settings") {
    const settings = data.settings || {};
    add(
      "Idle refresh",
      settings.idle_poll_seconds == null
        ? null
        : `${settings.idle_poll_seconds}s`,
    );
    add(
      "Print refresh",
      settings.print_poll_seconds == null
        ? null
        : `${settings.print_poll_seconds}s`,
    );
    add("Quiet unreachable logs", settings.quiet_unreachable ? "ON" : "OFF");
    add("Connected platforms", (data.platforms || []).join(", "));
  } else if (name === "components") {
    add("Loaded platforms", (data.platforms || []).join(", "));
    add("Available printer objects", (data.available_objects || []).length);
    (data.tracked_objects || []).forEach((object) =>
      add(
        object.name,
        object.fields == null ? "ALL FIELDS" : object.fields.join(", "),
      ),
    );
  }
  return rows;
}

function renderPageDetails(data = latestData) {
  if (!data) return;
  const rows = detailRowsForScreen(activeScreen, data);
  const drawer = byId("pageDetails");
  const scrollTop = drawer.scrollTop;
  setText("detailsTitle", `${SCREEN_TITLES[activeScreen][1]} / DETAILS`);
  setText(
    "detailsSummary",
    data.available
      ? `Snapshot received ${new Date().toLocaleTimeString([], {
          hour12: false,
        })}. Optional fields are omitted when unsupported.`
      : "Printer state is unavailable; displayed details may be stale.",
  );
  const container = byId("detailsRows");
  container.replaceChildren();
  rows.forEach(([name, value]) => appendObjectRow(container, name, value));
  if (!rows.length) appendEmpty(container, "NO ADDITIONAL DATA REPORTED");
  drawer.scrollTop = scrollTop;
}

function setScreen(name) {
  if (!SCREEN_TITLES[name]) return;
  activeScreen = name;
  if (detailsOpen) renderPageDetails();
  document
    .querySelectorAll(".screen")
    .forEach((screen) =>
      screen.classList.toggle("active", screen.dataset.screen === name),
    );
  document.querySelectorAll(".nav-item").forEach((item) => {
    const active = item.dataset.screenTarget === name;
    item.classList.toggle("active", active);
    if (active) {
      item.setAttribute("aria-current", "page");
      item.scrollIntoView?.({
        block: "nearest",
        inline: "center",
        behavior: reducedMotionPreferred() ? "auto" : "smooth",
      });
    } else item.removeAttribute("aria-current");
  });
  setText("pageKicker", SCREEN_TITLES[name][0]);
  setText("screenTitle", SCREEN_TITLES[name][1]);
  renderCamera(availableWebcams);
  if (name === "dashboard") requestAnimationFrame(drawToolpath);
}

function setJogStep(button) {
  jogStep = Number(button.dataset.jogStep) || 1;
  document
    .querySelectorAll("[data-jog-step]")
    .forEach((item) =>
      item.classList.toggle(
        "is-active",
        item.dataset.jogStep === button.dataset.jogStep,
      ),
    );
  setText("moveStepValue", String(jogStep));
}

function setToolpathView(view) {
  const preset = CAMERA_VIEWS[view];
  if (!preset) return;
  document
    .querySelectorAll("[data-toolpath-view]")
    .forEach((button) =>
      button.classList.toggle(
        "is-active",
        button.dataset.toolpathView === view,
      ),
    );
  animateCameraTo({
    yaw: preset.yaw,
    pitch: preset.pitch,
    zoom: 1,
    panX: 0,
    panY: 0,
  });
}

function animateCameraTo(target, durationMs = 380) {
  if (reducedMotionPreferred()) {
    for (const key of ["yaw", "pitch", "zoom", "panX", "panY"]) {
      if (target[key] !== undefined) toolpathCamera[key] = target[key];
    }
    drawToolpath();
    return;
  }
  cameraAnim = {
    from: {
      yaw: toolpathCamera.yaw,
      pitch: toolpathCamera.pitch,
      zoom: toolpathCamera.zoom,
      panX: toolpathCamera.panX,
      panY: toolpathCamera.panY,
    },
    to: target,
    start: Date.now(),
    duration: durationMs,
    frames: 0,
  };
  orbitVelocityX = 0;
  orbitVelocityY = 0;
  if (cameraAnimFrame === null)
    cameraAnimFrame = requestAnimationFrame(stepCameraAnimation);
}

function stepCameraAnimation() {
  cameraAnimFrame = null;
  if (!cameraAnim) return;
  const t = Math.min(1, (Date.now() - cameraAnim.start) / cameraAnim.duration);
  const eased = 1 - Math.pow(1 - t, 3);
  for (const key of ["yaw", "pitch", "zoom", "panX", "panY"]) {
    if (cameraAnim.to[key] !== undefined) {
      toolpathCamera[key] =
        cameraAnim.from[key] +
        (cameraAnim.to[key] - cameraAnim.from[key]) * eased;
    }
  }
  drawToolpath();
  if (t < 1 && ++cameraAnim.frames < 900) {
    cameraAnimFrame = requestAnimationFrame(stepCameraAnimation);
    return;
  }
  for (const key of ["yaw", "pitch", "zoom", "panX", "panY"]) {
    if (cameraAnim.to[key] !== undefined)
      toolpathCamera[key] = cameraAnim.to[key];
  }
  cameraAnim = null;
  drawToolpath();
}

function startOrbitInertia() {
  if (orbitInertiaFrame !== null || reducedMotionPreferred()) return;
  orbitInertiaFrame = requestAnimationFrame(stepOrbitInertia);
}

function stepOrbitInertia() {
  orbitInertiaFrame = null;
  if (toolpathCamera.dragging || cameraAnim) return;
  orbitVelocityX *= 0.9;
  orbitVelocityY *= 0.9;
  if (Math.abs(orbitVelocityX) < 0.0015 && Math.abs(orbitVelocityY) < 0.0015)
    return;
  toolpathCamera.yaw += orbitVelocityX;
  toolpathCamera.pitch = Math.max(
    0.025,
    Math.min(1.55, toolpathCamera.pitch + orbitVelocityY),
  );
  drawToolpath();
  orbitInertiaFrame = requestAnimationFrame(stepOrbitInertia);
}

function closePageDetails() {
  detailsOpen = false;
  byId("pageDetails").hidden = true;
  byId("detailsScrim").hidden = true;
  byId("pageDetails").setAttribute("aria-hidden", "true");
}

const NAV_KEY_STEPS = {
  ArrowDown: 1,
  ArrowRight: 1,
  ArrowUp: -1,
  ArrowLeft: -1,
};

function handleNavKeydown(event) {
  const current = event.target?.closest?.(".nav-item");
  if (!current) return;
  const items = [...document.querySelectorAll(".nav-item")];
  const index = items.indexOf(current);
  if (index < 0) return;
  let next;
  if (event.key === "Home") next = 0;
  else if (event.key === "End") next = items.length - 1;
  else if (NAV_KEY_STEPS[event.key])
    next = (index + NAV_KEY_STEPS[event.key] + items.length) % items.length;
  else return;
  event.preventDefault?.();
  items[next].focus();
}

const CANVAS_LABELS = {
  layerSpark: "Per-layer print time chart",
  tempGraph: "Hotend and bed temperature graph",
  tempGraphHistory: "Rolling temperature trace",
  retransmitSpark: "MCU retransmit trend",
};

function enhanceAccessibility() {
  for (const [id, label] of Object.entries(CANVAS_LABELS)) {
    const canvas = byId(id);
    if (!canvas || canvas.getAttribute("aria-label")) continue;
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", label);
  }
  const toastElement = byId("toast");
  if (toastElement && !toastElement.getAttribute("role")) {
    toastElement.setAttribute("role", "status");
    toastElement.setAttribute("aria-live", "polite");
    toastElement.setAttribute("aria-atomic", "true");
  }
  document.querySelectorAll('[data-action="jog"]').forEach((button) => {
    if (button.getAttribute("aria-label")) return;
    const direction = Number(button.dataset.dir) > 0 ? "plus" : "minus";
    button.setAttribute(
      "aria-label",
      `Jog ${button.dataset.axis} ${direction}`,
    );
  });
}

function bindInteractions() {
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-details-toggle]")) {
      detailsOpen = !detailsOpen;
      byId("pageDetails").hidden = !detailsOpen;
      byId("detailsScrim").hidden = !detailsOpen;
      byId("pageDetails").setAttribute("aria-hidden", String(!detailsOpen));
      if (detailsOpen) renderPageDetails();
      return;
    }
    if (event.target.closest("[data-details-close]")) {
      closePageDetails();
      return;
    }
    if (event.target.closest("[data-clear-command-history]")) {
      sentCommandHistory = sentCommandHistory.filter(
        (entry) => entry.printer !== printer,
      );
      renderSentCommandHistory();
      return;
    }
    if (event.target.closest("[data-camera-config]")) {
      openCameraConfig();
      return;
    }
    if (event.target.closest("[data-camera-config-close]")) {
      closeCameraConfig();
      return;
    }
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
      const tile = event.target.closest(".camera-tile, .dashboard-camera-tile");
      const image = tile?.querySelector("img");
      if (image?.requestFullscreen) image.requestFullscreen();
      return;
    }
    const snapshotButton = event.target.closest("[data-camera-snapshot]");
    if (snapshotButton) {
      if (snapshotButton.dataset.snapshotUrl)
        window.open(snapshotButton.dataset.snapshotUrl, "_blank", "noopener");
      else toast("NO SNAPSHOT URL CONFIGURED");
      return;
    }
    const fileOption = event.target.closest("[data-file-option]");
    if (fileOption) {
      selectedFile = fileOption.dataset.fileOption;
      byId("fileSel").value = selectedFile;
      renderFiles();
      loadFileAnalysis(selectedFile);
      act("select_file", selectedFile);
      return;
    }
    if (event.target.id === "jobDoneDismiss") {
      hideJobDoneCard();
      return;
    }
    if (event.target.id === "tlClear") {
      clearTimelapse();
      return;
    }
    const queueJump = event.target.closest("[data-queue-jump]");
    if (queueJump) {
      act("jump_queue_job", null, null, {
        job_id: queueJump.dataset.queueJump,
      });
      return;
    }
    const queueRemove = event.target.closest("[data-queue-remove]");
    if (queueRemove) {
      act("delete_queue_job", null, null, {
        job_id: queueRemove.dataset.queueRemove,
      });
      return;
    }
    const action = event.target.closest("[data-action]");
    if (action) dispatchAction(action);
  });

  document.addEventListener("change", (event) => {
    const target = event.target;
    if (target.id === "printerSel") switchPrinter();
    if (target.id === "cameraLayout") {
      cameraLayout = target.value;
      cameraGridSignature = "";
      renderCamera(availableWebcams);
    }
    if (target.id === "dashboardCameraLayout") {
      dashboardCameraLayout = target.value;
      dashboardCameraSignature = "";
      saveDashboardCameraPrefs();
      renderCamera(availableWebcams);
      renderDashboardCameraConfig();
    }
    if (target.matches("[data-camera-slot]")) {
      cameraAssignments[Number(target.dataset.cameraSlot)] = target.value;
      renderCamera(availableWebcams);
    }
    if (target.matches("[data-dashboard-camera-slot]")) {
      dashboardCameraAssignments[Number(target.dataset.dashboardCameraSlot)] =
        target.value;
      saveDashboardCameraPrefs();
      renderCamera(availableWebcams);
      renderDashboardCameraConfig();
    }
    if (target.id === "tlCamera") {
      timelapseViewCamera = target.value === "*" ? "*" : target.value;
      renderTimelapseStatus();
    }
    if (target.id === "fileSel") {
      selectedFile = target.value;
      loadFileAnalysis(selectedFile);
      act("select_file", selectedFile);
    }
    if (target.id === "speed") act("set_speed", target.value);
    if (target.id === "flow") act("set_flow", target.value);
    if (target.id === "fan")
      act("set_fan", Math.round(Number(target.value) * 2.55));
    if (target.id === "bedCleared") {
      const reprint = byId("jobDoneReprint");
      if (reprint) reprint.disabled = !target.checked;
    }
    if (target.id === "showFuturePath" || target.id === "clipFutureLayers")
      drawToolpath();
    if (target.id === "layerFollow") drawToolpath();
    if (target.id === "themeUpload") {
      handleThemeUpload(target.files?.[0]);
      return;
    }
    if (DISPLAY_CONTROL_IDS.includes(target.id)) {
      readDisplayControls();
      saveDisplayPrefs();
      applyDisplayPrefs();
      if (latestData) render(latestData);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && cameraConfigOpen) closeCameraConfig();
    else if (event.key === "Escape" && detailsOpen) closePageDetails();
    else handleNavKeydown(event);
  });

  document.addEventListener("input", (event) => {
    const target = event.target;
    if (target.id === "fileSearch") renderFiles();
    if (target.id === "layerScrub") {
      scrubZ = Number(target.value);
      const follow = byId("layerFollow");
      if (follow) follow.checked = false;
      drawToolpath();
      syncTimelapseToScrub();
    }
    if (target.id === "tlScrub") renderTimelapseFrame();
    if (["speed", "flow", "fan"].includes(target.id)) {
      const label = byId(`${target.id}Val`);
      if (label) label.textContent = `${Math.round(Number(target.value))}%`;
    }
  });

  document.addEventListener("submit", (event) => {
    if (event.target.id === "upForm") uploadFile(event);
    if (event.target.id === "gcodeForm") sendGcode(event);
  });
}

// The parser core lives in toolpath_parse.js (loaded as MoonrakerToolpathParse)
// so the same code runs in the page, the parsing worker, and tests. These
// wrappers keep the call sites unchanged and degrade if the module is missing.
const _tpCore =
  typeof MoonrakerToolpathParse !== "undefined" ? MoonrakerToolpathParse : null;

function parseGcodeLine(line, state, fraction, stride) {
  return _tpCore ? _tpCore.parseGcodeLine(line, state, fraction, stride) : null;
}

function addToolpathSegment(segments, bounds, segment, state) {
  if (_tpCore) _tpCore.addToolpathSegment(segments, bounds, segment, state);
}

function normalizeBounds(bounds) {
  return _tpCore ? _tpCore.normalizeBounds(bounds) : null;
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

function activeGcodeFilename(status) {
  const name = status?.print_stats?.filename || "";
  if (name) return name;
  const path = status?.virtual_sdcard?.file_path || "";
  if (path.includes("/gcodes/")) return path.split("/gcodes/").pop();
  return path.split("/").filter(Boolean).pop() || "";
}

function requestToolpath() {
  const data = latestData;
  const status = data?.status || {};
  const filename = activeGcodeFilename(status);
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
  const virtualSdcard = status.virtual_sdcard || {};
  const filename = activeGcodeFilename(status);
  const key = `${data.entry_id}:${filename}`;
  if (!filename) {
    if (toolpathAbort) toolpathAbort.abort();
    toolpathKey = "";
    toolpathReady = false;
    toolpathLoading = false;
    toolpathRequested = false;
    toolpathSegments = [];
    toolpathBounds = null;
    toolpathLayerStats = [];
    toolpathSimSeconds = 0;
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
    toolpathLayerStats = [];
    toolpathSimSeconds = 0;
    const fileSize = Number(virtualSdcard.file_size) || 0;
    toolpathRequested = fileSize > 0 && fileSize <= MAX_TOOLPATH_BYTES;
    const button = byId("toolpathLoadButton");
    button.disabled = fileSize > MAX_TOOLPATH_BYTES;
    button.textContent =
      fileSize > MAX_TOOLPATH_BYTES
        ? "FILE TOO LARGE"
        : toolpathRequested
          ? "LOAD TOOLPATH"
          : "LOAD 3D PREVIEW";
    if (!toolpathRequested) {
      renderToolpathStatus(
        fileSize > MAX_TOOLPATH_BYTES
          ? "FILE EXCEEDS 128 MB PREVIEW LIMIT"
          : "G-CODE READY / PRESS LOAD 3D PREVIEW",
      );
    }
  }
  if (
    toolpathRequested &&
    !toolpathReady &&
    !toolpathLoading &&
    !toolpathError
  ) {
    beginToolpathLoad(data, filename, key);
  }
  drawToolpath();
}

const TOOLPATH_CACHE_DB = "moonraker-toolpaths";
const TOOLPATH_CACHE_STORE = "paths";
const TOOLPATH_CACHE_MAX = 5;

function toolpathDb() {
  if (typeof indexedDB === "undefined") return Promise.resolve(null);
  return new Promise((resolve) => {
    try {
      const request = indexedDB.open(TOOLPATH_CACHE_DB, 1);
      request.onupgradeneeded = () =>
        request.result.createObjectStore(TOOLPATH_CACHE_STORE);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

async function toolpathCacheGet(key) {
  const db = await toolpathDb();
  if (!db) return null;
  try {
    return await new Promise((resolve) => {
      const request = db
        .transaction(TOOLPATH_CACHE_STORE, "readonly")
        .objectStore(TOOLPATH_CACHE_STORE)
        .get(key);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

async function toolpathCachePut(key, value) {
  const db = await toolpathDb();
  if (!db) return;
  try {
    await new Promise((resolve) => {
      const store = db
        .transaction(TOOLPATH_CACHE_STORE, "readwrite")
        .objectStore(TOOLPATH_CACHE_STORE);
      store.put(value, key);
      const keysRequest = store.getAllKeys();
      keysRequest.onsuccess = () => {
        const keys = keysRequest.result || [];
        keys
          .filter((existing) => existing !== key)
          .slice(0, Math.max(0, keys.length - TOOLPATH_CACHE_MAX))
          .forEach((existing) => store.delete(existing));
      };
      store.transaction.oncomplete = () => resolve();
      store.transaction.onerror = () => resolve();
      store.transaction.onabort = () => resolve();
    });
  } catch {
    /* toolpath cache is best-effort */
  }
}

function applyToolpathResult(result) {
  const segments = result.segments || [];
  toolpathSegments = segments;
  toolpathBounds = result.boundsNormalized
    ? result.boundsNormalized
    : normalizeBounds(result.bounds);
  toolpathLayerStats = result.layerStats || [];
  toolpathSimSeconds = result.simSeconds || 0;
  toolpathReady = segments.length > 0;
  toolpathError = segments.length
    ? ""
    : "NO EXTRUSION MOVES COULD BE PARSED FROM THIS FILE";
  renderToolpathStatus(
    toolpathReady
      ? `SIMULATED PATH / ${segments.length.toLocaleString()} SAMPLED MOVES`
      : toolpathError,
  );
  drawToolpath();
}

async function parseToolpathStream(response, options) {
  if (typeof Worker === "function" && !options.signal?.aborted) {
    const workerResult = await parseToolpathWithWorker(response, options);
    if (workerResult !== undefined) return workerResult;
    if (options.signal?.aborted) return null;
    // Worker never became ready — the body is untouched, so parse inline.
  }
  return parseToolpathInline(response, options);
}

async function parseToolpathWithWorker(response, options) {
  let worker;
  try {
    worker = new Worker("/api/moonraker/toolpath_worker.js");
  } catch {
    return undefined;
  }
  const { signal } = options;
  let streamed = false;
  const onAbort = () => worker.terminate();
  signal?.addEventListener?.("abort", onAbort, { once: true });
  try {
    const ready = await new Promise((resolve) => {
      const timer = setTimeout(() => resolve("timeout"), 5000);
      worker.onmessage = (event) => {
        if (event.data?.type === "ready") {
          clearTimeout(timer);
          resolve(true);
        }
      };
      worker.onerror = () => {
        clearTimeout(timer);
        resolve(false);
      };
      worker.postMessage({
        type: "start",
        rangeStart: options.rangeStart,
        rangeEnd: options.rangeEnd,
        stride: options.stride,
      });
    });
    if (ready !== true || signal?.aborted) return undefined;
    streamed = true;
    const donePromise = new Promise((resolve, reject) => {
      worker.onmessage = (event) => {
        const msg = event.data || {};
        if (msg.type === "progress")
          options.onProgress?.(Number(msg.segments) || 0);
        if (msg.type === "done") resolve(msg);
        if (msg.type === "error")
          reject(new Error(msg.error || "worker parse failed"));
      };
      worker.onerror = (event) =>
        reject(new Error(event.message || "worker parse failed"));
    });
    const decoder = new TextDecoder();
    const reader = response.body?.getReader?.();
    if (!reader) {
      worker.postMessage({ type: "text", text: await response.text() });
    } else {
      while (true) {
        if (signal?.aborted) return null;
        const { value, done } = await reader.read();
        if (done) break;
        worker.postMessage({
          type: "text",
          text: decoder.decode(value, { stream: true }),
        });
      }
      const tail = decoder.decode();
      if (tail) worker.postMessage({ type: "text", text: tail });
    }
    worker.postMessage({ type: "end" });
    const result = await donePromise;
    if (signal?.aborted) return null;
    return result;
  } catch (error) {
    if (!streamed) return undefined;
    throw error;
  } finally {
    signal?.removeEventListener?.("abort", onAbort);
    worker.terminate();
  }
}

async function parseToolpathInline(response, options) {
  const { rangeStart, rangeEnd, stride } = options;
  const rangeBytes = Number.isFinite(rangeEnd)
    ? Math.max(1, rangeEnd - rangeStart)
    : 1;
  const fractionAt = (offset) =>
    Number.isFinite(rangeEnd)
      ? Math.max(0, Math.min((offset - rangeStart) / rangeBytes, 1))
      : 0;
  const state = _tpCore
    ? _tpCore.createParseState(stride)
    : {
        xyzAbsolute: true,
        eAbsolute: true,
        unit: 1,
        position: { x: 0, y: 0, z: 0, e: 0 },
        extrusions: 0,
        sampleStride: stride,
        feedrate: 0,
        simSeconds: 0,
        layerTimes: new Map(),
      };
  const bounds = _tpCore
    ? _tpCore.createBounds()
    : {
        minX: Infinity,
        maxX: -Infinity,
        minY: Infinity,
        maxY: -Infinity,
        minZ: Infinity,
        maxZ: -Infinity,
      };
  const segments = [];
  const decoder = new TextDecoder();
  const reader = response.body?.getReader?.();
  if (!reader) {
    const text = await response.text();
    let offset = 0;
    const lines = text.split(/\r?\n/);
    for (let index = 0; index < lines.length; index++) {
      offset += lines[index].length + 1;
      const segment = parseGcodeLine(
        lines[index],
        state,
        fractionAt(offset),
        stride,
      );
      if (segment && offset >= rangeStart && offset <= rangeEnd)
        addToolpathSegment(segments, bounds, segment, state);
      if (index > 0 && index % 6000 === 0)
        await new Promise(requestAnimationFrame);
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
        const segment = parseGcodeLine(
          line,
          state,
          fractionAt(parsedChars),
          stride,
        );
        if (segment && parsedChars >= rangeStart && parsedChars <= rangeEnd)
          addToolpathSegment(segments, bounds, segment, state);
        lineCount += 1;
      }
      if (lineCount && lineCount % 7000 < lines.length) {
        options.onProgress?.(segments.length);
        await new Promise(requestAnimationFrame);
      }
    }
    buffer += decoder.decode();
    if (buffer) {
      parsedChars += buffer.length;
      const segment = parseGcodeLine(
        buffer,
        state,
        fractionAt(parsedChars),
        stride,
      );
      if (segment && parsedChars >= rangeStart && parsedChars <= rangeEnd)
        addToolpathSegment(segments, bounds, segment, state);
    }
  }
  if (!Number.isFinite(rangeEnd) && segments.length > 1) {
    segments.forEach((segment, index) => {
      segment.fraction = index / (segments.length - 1);
    });
  }
  return {
    segments,
    bounds,
    layerStats: [...state.layerTimes]
      .map(([z, seconds]) => ({ z, seconds }))
      .sort((a, b) => a.z - b.z),
    simSeconds: state.simSeconds || 0,
  };
}

async function loadToolpath(data, filename, key, signal) {
  const entryId = data.entry_id;
  const metadata = data.meta || {};
  const reportedSize = Number(data.status?.virtual_sdcard?.file_size) || 0;
  const cacheKey = `${entryId}|${filename}|${reportedSize}`;
  renderToolpathStatus("LOADING ACTIVE G-CODE / BUILDING 3D PATH…");
  try {
    const cached = await toolpathCacheGet(cacheKey);
    if (key !== toolpathKey || signal?.aborted) return;
    if (cached?.segments?.length) {
      applyToolpathResult(cached);
      return;
    }
    const response = await hassApi().fetchWithAuth(
      API.gcode(entryId, filename),
      { signal },
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || `file request ${response.status}`);
    }
    const totalBytes =
      Number(response.headers.get("Content-Length")) || reportedSize;
    if (totalBytes > MAX_TOOLPATH_BYTES)
      throw new Error(
        "G-code file exceeds the 128 MB interactive preview limit",
      );
    const startCandidate = Number(metadata.gcode_start_byte);
    const endCandidate = Number(metadata.gcode_end_byte);
    const rangeStart = Number.isFinite(startCandidate) ? startCandidate : 0;
    const hasMetadataRange =
      Number.isFinite(endCandidate) && endCandidate > rangeStart;
    const rangeEnd = hasMetadataRange
      ? endCandidate
      : totalBytes || Number.POSITIVE_INFINITY;
    const stride = Math.max(
      1,
      Math.ceil(totalBytes / (MAX_TOOLPATH_SEGMENTS * 70)),
    );
    const result = await parseToolpathStream(response, {
      rangeStart,
      rangeEnd,
      stride,
      signal,
      onProgress: (count) =>
        renderToolpathStatus(
          `PARSING G-CODE / ${count.toLocaleString()} PATH SEGMENTS`,
        ),
    });
    if (result === null || key !== toolpathKey) return;
    applyToolpathResult(result);
    if (result.segments?.length) {
      toolpathCachePut(cacheKey, {
        segments: result.segments,
        boundsNormalized: toolpathBounds,
        layerStats: toolpathLayerStats,
        simSeconds: toolpathSimSeconds,
      });
    }
  } catch (error) {
    if (error.name === "AbortError" || key !== toolpathKey) return;
    toolpathReady = false;
    toolpathError = error.message || "TOOLPATH PREVIEW UNAVAILABLE";
    renderToolpathStatus(toolpathError.toUpperCase());
    drawToolpath();
  }
}

function renderToolpathStatus(text) {
  const element = byId("toolpathStatus");
  if (element) element.textContent = text;
}

function projectPoint(point, camera, scale, centerU, centerV, width, height) {
  const cosYaw = Math.cos(camera.yaw),
    sinYaw = Math.sin(camera.yaw);
  const cosPitch = Math.cos(camera.pitch),
    sinPitch = Math.sin(camera.pitch);
  const u = point[0] * cosYaw - point[1] * sinYaw;
  const horizontal = point[0] * sinYaw + point[1] * cosYaw;
  const v = horizontal * cosPitch + point[2] * sinPitch;
  const depth = -horizontal * sinPitch + point[2] * cosPitch;
  return {
    x: width / 2 + (u - centerU) * scale + (camera.panX || 0),
    y: height * 0.53 - (v - centerV) * scale + (camera.panY || 0),
    depth,
  };
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
  const width = rect.width,
    height = rect.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = cssVar("--bg", "#030d0a");
  ctx.fillRect(0, 0, width, height);

  const bounds = toolpathBounds;
  if (!bounds) {
    drawEmptyBuildPlate(ctx, width, height);
    return;
  }
  const corners = [
    [bounds.minX - 5, bounds.minY - 5, 0],
    [bounds.maxX + 5, bounds.minY - 5, 0],
    [bounds.maxX + 5, bounds.maxY + 5, 0],
    [bounds.minX - 5, bounds.maxY + 5, 0],
    [bounds.minX - 5, bounds.minY - 5, bounds.maxZ],
    [bounds.maxX + 5, bounds.minY - 5, bounds.maxZ],
    [bounds.maxX + 5, bounds.maxY + 5, bounds.maxZ],
    [bounds.minX - 5, bounds.maxY + 5, bounds.maxZ],
  ];
  const cosYaw = Math.cos(toolpathCamera.yaw),
    sinYaw = Math.sin(toolpathCamera.yaw);
  const cosPitch = Math.cos(toolpathCamera.pitch),
    sinPitch = Math.sin(toolpathCamera.pitch);
  const transformed = corners.map((point) => {
    const u = point[0] * cosYaw - point[1] * sinYaw;
    const horizontal = point[0] * sinYaw + point[1] * cosYaw;
    return {
      u,
      v: horizontal * cosPitch + point[2] * sinPitch,
      d: -horizontal * sinPitch + point[2] * cosPitch,
    };
  });
  const minU = Math.min(...transformed.map((point) => point.u));
  const maxU = Math.max(...transformed.map((point) => point.u));
  const minV = Math.min(...transformed.map((point) => point.v));
  const maxV = Math.max(...transformed.map((point) => point.v));
  const centerU = (minU + maxU) / 2,
    centerV = (minV + maxV) / 2;
  const scale = Math.max(
    0.01,
    Math.min(
      (width - 54) / Math.max(1, maxU - minU),
      (height - 42) / Math.max(1, maxV - minV),
    ) * toolpathCamera.zoom,
  );
  const project = (point) =>
    projectPoint(point, toolpathCamera, scale, centerU, centerV, width, height);

  drawBuildPlate(ctx, project, bounds);
  const progress = getLiveProgress(latestData);
  const showFuture = byId("showFuturePath")?.checked !== false;
  const depthMin = Math.min(...transformed.map((point) => point.d));
  const depthSpan = Math.max(
    1e-6,
    Math.max(...transformed.map((point) => point.d)) - depthMin,
  );
  const zSpan = Math.max(1e-6, bounds.maxZ - bounds.minZ);
  const position = liveHeadDrawn || currentToolheadPosition();
  const headZ = position ? position[2] : Number.NaN;
  const clipFuture =
    byId("clipFutureLayers")?.checked === true && Number.isFinite(headZ);

  const scrubControl = byId("layerScrub");
  const followControl = byId("layerFollow");
  if (scrubControl) {
    scrubControl.disabled = false;
    const lo = bounds.minZ,
      hi = Math.max(bounds.maxZ, bounds.minZ + 0.1);
    if (Number(scrubControl.max) !== hi || Number(scrubControl.min) !== lo) {
      scrubControl.min = lo;
      scrubControl.max = hi;
      scrubControl.step = Math.max(0.05, (hi - lo) / 400);
    }
  }
  if (followControl && followControl.checked && Number.isFinite(headZ))
    scrubZ = headZ;
  if (
    scrubControl &&
    document.activeElement !== scrubControl &&
    Number.isFinite(scrubZ)
  ) {
    scrubControl.value = Math.min(
      Math.max(scrubZ, Number(scrubControl.min)),
      Number(scrubControl.max),
    );
  }
  setText(
    "layerScrubLabel",
    Number.isFinite(scrubZ) ? `Z ${fmt(scrubZ, 2)}` : "Z —",
  );
  const splitZ = Number.isFinite(scrubZ) ? scrubZ : null;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  const drawPass = (futureMode) => {
    const buckets = new Map();
    for (const segment of toolpathSegments) {
      const midZ = (segment.a[2] + segment.b[2]) / 2;
      const isFuture =
        splitZ != null ? midZ > splitZ : (segment.fraction ?? 0) > progress;
      if (isFuture !== futureMode) continue;
      if (futureMode && clipFuture && midZ > headZ + 0.5) continue;
      const a = project(segment.a),
        b = project(segment.b);
      const depthNorm = Math.max(
        0,
        Math.min(((a.depth + b.depth) / 2 - depthMin) / depthSpan, 1),
      );
      const zNorm = Math.max(0, Math.min((midZ - bounds.minZ) / zSpan, 1));
      const activeLayer =
        !futureMode && Number.isFinite(headZ) && Math.abs(midZ - headZ) <= 0.45;
      const key = activeLayer
        ? 900 + Math.round(depthNorm * 7)
        : Math.round(depthNorm * 7) * 16 + Math.round(zNorm * 15);
      let bucket = buckets.get(key);
      if (!bucket)
        buckets.set(
          key,
          (bucket = { depthNorm, zNorm, activeLayer, lines: [] }),
        );
      bucket.lines.push(a.x, a.y, b.x, b.y);
    }
    const ordered = [...buckets.values()].sort(
      (left, right) => left.depthNorm - right.depthNorm,
    );
    for (const bucket of ordered) {
      if (bucket.activeLayer) {
        ctx.lineWidth = 1.6;
        ctx.strokeStyle = `rgba(247,203,100,${(
          0.55 +
          0.45 * bucket.depthNorm
        ).toFixed(3)})`;
        ctx.shadowColor = cssRgba("--amber", 0.4, "rgba(247,203,100,.4)");
        ctx.shadowBlur = 4;
      } else if (futureMode) {
        ctx.lineWidth = 1;
        ctx.strokeStyle = `rgba(22,130,82,${(
          0.08 +
          0.42 * bucket.depthNorm
        ).toFixed(3)})`;
        ctx.shadowBlur = 0;
      } else {
        ctx.lineWidth = 1.35;
        const r = Math.round(53 * (1 - bucket.zNorm));
        const g = Math.round(232 + 7 * bucket.zNorm);
        const b = Math.round(189 - 44 * bucket.zNorm);
        ctx.strokeStyle = `rgba(${r},${g},${b},${(
          0.42 +
          0.58 * bucket.depthNorm
        ).toFixed(3)})`;
        ctx.shadowColor = cssRgba("--green", 0.28, "rgba(0,239,145,.28)");
        ctx.shadowBlur = 3;
      }
      ctx.beginPath();
      const lines = bucket.lines;
      for (let index = 0; index < lines.length; index += 4) {
        ctx.moveTo(lines[index], lines[index + 1]);
        ctx.lineTo(lines[index + 2], lines[index + 3]);
      }
      ctx.stroke();
    }
    ctx.shadowBlur = 0;
  };
  if (showFuture) drawPass(true);
  drawPass(false);

  if (position) {
    const head = project(position);
    const foot = project([position[0], position[1], 0]);
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1;
    ctx.strokeStyle = cssRgba("--amber", 0.35, "rgba(247,203,100,.35)");
    ctx.beginPath();
    ctx.moveTo(head.x, head.y);
    ctx.lineTo(foot.x, foot.y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.arc(foot.x, foot.y, 6, 0, Math.PI * 2);
    ctx.strokeStyle = cssRgba("--amber", 0.5, "rgba(247,203,100,.5)");
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(head.x, head.y, 4.5, 0, Math.PI * 2);
    ctx.fillStyle = cssVar("--amber", "#f7cb64");
    ctx.shadowColor = cssVar("--amber", "#f7cb64");
    ctx.shadowBlur = 10;
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.beginPath();
    ctx.moveTo(head.x - 8, head.y);
    ctx.lineTo(head.x + 8, head.y);
    ctx.moveTo(head.x, head.y - 8);
    ctx.lineTo(head.x, head.y + 8);
    ctx.strokeStyle = cssVar("--amber", "#f7cb64");
    ctx.lineWidth = 1;
    ctx.stroke();
  }
  const headText = position
    ? ` / HEAD X${fmt(position[0], 1)} Y${fmt(position[1], 1)} Z${fmt(
        position[2],
        1,
      )}`
    : "";
  renderToolpathStatus(
    toolpathReady
      ? `SIMULATED EXTRUSION PATH / ${toolpathSegments.length.toLocaleString()} SAMPLES / ${(
          progress * 100
        ).toFixed(1)}%${headText}`
      : toolpathError || "LOADING ACTIVE G-CODE",
  );
  drawLayerSpark();
}

function drawLayerSpark() {
  const canvas = byId("layerSpark");
  const ctx = canvas?.getContext?.("2d");
  if (!toolpathLayerStats.length) {
    if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    setText("layerEta", "LAYER —");
    setText("simEta", "SIM ETA —");
    return;
  }
  const position = liveHeadDrawn || currentToolheadPosition();
  const printing = ["printing", "paused"].includes(
    String(latestData?.status?.print_stats?.state),
  );
  const headZ = printing && position ? position[2] : Number.NaN;
  const maxSeconds = Math.max(
    ...toolpathLayerStats.map((layer) => layer.seconds),
  );
  let layerSeconds = null;
  let currentIndex = -1;
  let remaining = toolpathSimSeconds;
  toolpathLayerStats.forEach((layer, index) => {
    if (Number.isFinite(headZ) && layer.z <= headZ + 0.001) {
      layerSeconds = layer.seconds;
      remaining -= layer.seconds;
      currentIndex = index;
    }
  });
  if (ctx) {
    const width = canvas.width,
      height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    const barWidth = Math.max(1, width / toolpathLayerStats.length);
    toolpathLayerStats.forEach((layer, index) => {
      const barHeight = Math.max(
        1,
        (layer.seconds / (maxSeconds || 1)) * (height - 4),
      );
      ctx.fillStyle =
        index === currentIndex
          ? cssVar("--amber", "#f7cb64")
          : Number.isFinite(headZ) && index > currentIndex
            ? cssVar("--line-hi", "#1c6844")
            : cssVar("--green", "#00ef91");
      ctx.fillRect(
        index * barWidth,
        height - barHeight,
        Math.max(1, barWidth - 0.5),
        barHeight,
      );
    });
  }
  setText(
    "layerEta",
    `LAYER ${Number.isFinite(layerSeconds) ? duration(layerSeconds) : "—"}`,
  );
  setText("simEta", `SIM ETA ${duration(Math.max(0, remaining))}`);
}

function drawBuildPlate(ctx, project, bounds) {
  const minX = Math.min(0, bounds.minX - 5),
    maxX = Math.max(220, bounds.maxX + 5);
  const minY = Math.min(0, bounds.minY - 5),
    maxY = Math.max(220, bounds.maxY + 5);
  const step = Math.max(
    10,
    Math.ceil(Math.max(maxX - minX, maxY - minY) / 22 / 10) * 10,
  );
  ctx.lineWidth = 1;
  ctx.strokeStyle = cssRgba("--line-hi", 0.42, "rgba(28,104,68,.42)");
  ctx.beginPath();
  for (let x = Math.ceil(minX / step) * step; x <= maxX; x += step) {
    const a = project([x, minY, 0]),
      b = project([x, maxY, 0]);
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
  }
  for (let y = Math.ceil(minY / step) * step; y <= maxY; y += step) {
    const a = project([minX, y, 0]),
      b = project([maxX, y, 0]);
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
  }
  ctx.stroke();
  const floor = [
    [minX, minY, 0],
    [maxX, minY, 0],
    [maxX, maxY, 0],
    [minX, maxY, 0],
  ];
  ctx.beginPath();
  floor.forEach((point, index) => {
    const p = project(point);
    index ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y);
  });
  ctx.closePath();
  ctx.strokeStyle = cssRgba("--green", 0.7, "rgba(0,239,145,.7)");
  ctx.stroke();
  const top = [
    [minX, minY, bounds.maxZ],
    [maxX, minY, bounds.maxZ],
    [maxX, maxY, bounds.maxZ],
    [minX, maxY, bounds.maxZ],
  ];
  ctx.beginPath();
  floor.forEach((point, index) => {
    const p = project(point);
    index ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y);
  });
  ctx.closePath();
  top.forEach((point, index) => {
    const a = project(floor[index]),
      b = project(point);
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
  });
  ctx.strokeStyle = cssRgba("--green", 0.17, "rgba(0,239,145,.17)");
  ctx.stroke();
  const origin = project([0, 0, 0]);
  const xAxis = project([Math.min(maxX, 25), 0, 0]);
  const yAxis = project([0, Math.min(maxY, 25), 0]);
  const zAxis = project([0, 0, Math.max(bounds.maxZ, 25)]);
  ctx.lineWidth = 1.5;
  [
    [origin, xAxis, cssVar("--red", "#ff536b"), "X"],
    [origin, yAxis, cssVar("--cyan", "#35e8bd"), "Y"],
    [origin, zAxis, cssVar("--green", "#00ef91"), "Z"],
  ].forEach(([a, b, color, label]) => {
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.strokeStyle = color;
    ctx.stroke();
    ctx.fillStyle = color;
    ctx.font = "7px monospace";
    ctx.fillText(label, b.x + 3, b.y - 2);
  });
}

function drawEmptyBuildPlate(ctx, width, height) {
  ctx.strokeStyle = cssRgba("--line-hi", 0.35, "rgba(0,130,76,.35)");
  ctx.lineWidth = 1;
  const pad = 26;
  for (let x = pad; x < width - pad; x += 20) {
    ctx.beginPath();
    ctx.moveTo(x, pad);
    ctx.lineTo(x, height - pad);
    ctx.stroke();
  }
  for (let y = pad; y < height - pad; y += 20) {
    ctx.beginPath();
    ctx.moveTo(pad, y);
    ctx.lineTo(width - pad, y);
    ctx.stroke();
  }
  ctx.strokeStyle = cssRgba("--green", 0.65, "rgba(0,239,145,.65)");
  ctx.strokeRect(pad, pad, width - pad * 2, height - pad * 2);
}

function getLiveProgress(data) {
  if (Number.isFinite(liveProgress)) return liveProgress;
  const status = data?.status || {};
  const card = status.virtual_sdcard || {};
  const position = Number(card.file_position);
  const start = Number(data?.meta?.gcode_start_byte);
  const end = Number(data?.meta?.gcode_end_byte);
  if (
    Number.isFinite(position) &&
    Number.isFinite(start) &&
    Number.isFinite(end) &&
    end > start
  ) {
    return Math.max(0, Math.min((position - start) / (end - start), 1));
  }
  const size = Number(card.file_size);
  if (Number.isFinite(position) && Number.isFinite(size) && size > 0) {
    return Math.max(0, Math.min(position / size, 1));
  }
  const fallback = Number(
    status.display_status?.progress ?? card.progress ?? 0,
  );
  return Number.isFinite(fallback) ? Math.max(0, Math.min(fallback, 1)) : 0;
}

const LIVE_ENTITY_KINDS = {
  toolhead_position_x: 0,
  toolhead_position_y: 1,
  toolhead_position_z: 2,
  progress: "progress",
  current_layer: "layer",
};

async function resolveLiveEntities() {
  const hass = window.hass;
  let entries = Object.values(hass?.entities || {});
  if (!entries.length && hass?.connection?.sendMessagePromise) {
    try {
      entries = await hass.connection.sendMessagePromise({
        type: "config/entity_registry/list",
      });
    } catch {
      entries = [];
    }
  }
  liveEntityIds = {};
  if (printer && entries.length) {
    for (const entry of entries) {
      const uniqueId = String(entry?.unique_id || "");
      if (!uniqueId.startsWith(`${printer}_`) || !entry?.entity_id) continue;
      const kind = LIVE_ENTITY_KINDS[uniqueId.slice(printer.length + 1)];
      if (kind !== undefined) liveEntityIds[entry.entity_id] = kind;
    }
  }
  if (!Object.keys(liveEntityIds).length) {
    const candidates = {};
    for (const entityId of Object.keys(hass?.states || {})) {
      for (const [suffix, kind] of Object.entries(LIVE_ENTITY_KINDS)) {
        if (!entityId.startsWith("sensor.") || !entityId.endsWith(`_${suffix}`))
          continue;
        (candidates[kind] = candidates[kind] || []).push(entityId);
      }
    }
    for (const [kind, ids] of Object.entries(candidates)) {
      if (ids.length === 1) liveEntityIds[ids[0]] = kind;
    }
  }
}

function ensureLiveSubscription() {
  const connection = window.hass?.connection;
  if (liveSubscription || !connection?.subscribeEvents) return;
  liveSubscription = true;
  const generation = ++liveSubscriptionGeneration;
  try {
    Promise.resolve(
      connection.subscribeEvents(handleLiveStateChanged, "state_changed"),
    )
      .then((unsubscribe) => {
        if (generation !== liveSubscriptionGeneration) {
          if (typeof unsubscribe === "function") unsubscribe();
          return;
        }
        liveSubscriptionUnsub =
          typeof unsubscribe === "function" ? unsubscribe : null;
      })
      .catch(() => {
        if (generation === liveSubscriptionGeneration) liveSubscription = false;
      });
  } catch {
    if (generation === liveSubscriptionGeneration) liveSubscription = false;
  }
}

function stopLiveSubscription() {
  liveSubscriptionGeneration += 1;
  liveSubscription = false;
  const unsubscribe = liveSubscriptionUnsub;
  liveSubscriptionUnsub = null;
  if (typeof unsubscribe === "function") {
    try {
      unsubscribe();
    } catch {}
  }
}

function currentToolheadPosition() {
  const position = latestData?.status?.toolhead?.position;
  if (!Array.isArray(position) || position.length < 3) return null;
  const xyz = position.slice(0, 3).map(Number);
  return xyz.every(Number.isFinite) ? xyz : null;
}

function handleLiveStateChanged(event) {
  const kind = liveEntityIds[event?.data?.entity_id];
  if (kind === undefined) return;
  const value = Number(event.data.new_state?.state);
  if (!Number.isFinite(value)) return;
  if (kind === "progress") {
    liveProgress = Math.max(0, Math.min(value / 100, 1));
  } else if (kind === "layer") {
    const layer = Math.round(value);
    if (
      liveLayer !== null &&
      layer > liveLayer &&
      latestData?.status?.print_stats?.state === "printing"
    ) {
      captureTimelapseFrame();
    }
    liveLayer = layer;
    return;
  } else {
    if (!liveHeadTarget)
      liveHeadTarget = currentToolheadPosition() || [0, 0, 0];
    liveHeadTarget[kind] = value;
  }
  scheduleHeadAnimation();
}

function scheduleHeadAnimation() {
  if (headAnimFrame !== null) return;
  headAnimFrame = requestAnimationFrame(stepHeadAnimation);
}

function stepHeadAnimation() {
  headAnimFrame = null;
  const rect = byId("toolpathCanvas")?.getBoundingClientRect?.();
  if (!rect || rect.width < 8 || rect.height < 8) {
    liveHeadDrawn = null;
    return;
  }
  if (liveHeadTarget) {
    const previous = liveHeadDrawn || liveHeadTarget;
    const next = previous.map(
      (value, index) => value + (liveHeadTarget[index] - value) * 0.38,
    );
    liveHeadDrawn = next.every(
      (value, index) => Math.abs(value - liveHeadTarget[index]) < 0.05,
    )
      ? liveHeadTarget.slice()
      : next;
    const toolhead = latestData?.status?.toolhead;
    if (toolhead) {
      const base = Array.isArray(toolhead.position) ? toolhead.position : [];
      toolhead.position = [...liveHeadDrawn, ...base.slice(3)];
    }
  }
  drawToolpath();
  if (
    liveHeadDrawn &&
    liveHeadTarget &&
    liveHeadDrawn.some(
      (value, index) => Math.abs(value - liveHeadTarget[index]) >= 0.05,
    )
  ) {
    scheduleHeadAnimation();
  }
}

function resetLiveTracking() {
  liveEntityIds = {};
  liveHeadTarget = null;
  liveHeadDrawn = null;
  liveProgress = null;
  liveLayer = null;
  scrubZ = null;
}

const ALERT_EVENT_KEYS = [
  "start",
  "progress",
  "pause",
  "finish",
  "error",
  "runout",
];
let alertPrefs = {
  engine: "off",
  players: [],
  quietStart: "",
  quietEnd: "",
  quietBypass: true,
  events: {
    start: true,
    progress: true,
    pause: true,
    finish: true,
    error: true,
    runout: true,
  },
};
let alertState = {
  seeded: false,
  state: "",
  milestone: -1,
  filamentOk: true,
  klippy: "",
  lastKey: "",
  lastAt: 0,
};
let alertPrefsKey = "";
let queueQuietOverrideUntil = 0;
let lastDataAt = 0;
let panelRefreshInFlight = false;
let panelPushUnsub = null;
let panelPushRequest = null;
let panelPushLive = false;
const STALE_AFTER_MS = 8000;
const STALE_EXEMPT_ACTIONS = new Set(["emergency_stop", "refresh_files"]);

function updateStaleness() {
  const printing = ["printing", "paused"].includes(
    String(latestData?.status?.print_stats?.state),
  );
  const intervalSeconds = printing
    ? Number(latestData?.settings?.print_poll_seconds) || 40 / 3
    : Number(latestData?.settings?.idle_poll_seconds) || 40;
  const limit = Math.max(STALE_AFTER_MS, intervalSeconds * 1000 * 1.6 + 3000);
  const age = lastDataAt ? Date.now() - lastDataAt : Number.POSITIVE_INFINITY;
  const stale =
    !Number.isFinite(age) || age > limit || latestData?.available === false;
  document.body?.classList?.toggle?.("stale-data", stale);
  const banner = byId("staleBanner");
  if (banner) {
    banner.hidden = !stale;
    if (stale)
      setText("staleAge", lastDataAt ? `${Math.floor(age / 1000)}S` : "—");
  }
  return stale;
}

function alertStorageKey() {
  return `nexus-alerts:${printer || "default"}`;
}

function alertEventInputId(key) {
  return `alert${key[0].toUpperCase()}${key.slice(1)}`;
}

function loadAlertPrefs() {
  const key = alertStorageKey();
  if (alertPrefsKey === key) return;
  alertPrefsKey = key;
  try {
    const saved = JSON.parse(window.localStorage?.getItem(key) || "null");
    if (saved && typeof saved === "object") {
      alertPrefs.engine = String(saved.engine || "off");
      alertPrefs.players = Array.isArray(saved.players)
        ? saved.players.map(String)
        : saved.player
          ? [String(saved.player)]
          : [];
      alertPrefs.quietStart = String(saved.quietStart || "");
      alertPrefs.quietEnd = String(saved.quietEnd || "");
      alertPrefs.quietBypass = saved.quietBypass !== false;
      for (const event of ALERT_EVENT_KEYS) {
        if (typeof saved.events?.[event] === "boolean")
          alertPrefs.events[event] = saved.events[event];
      }
    }
  } catch {
    /* ignore corrupt prefs */
  }
  applyAlertPrefs();
}

function applyAlertPrefs() {
  const assign = (id, value, prop = "value") => {
    const element = byId(id);
    if (element) element[prop] = value;
  };
  assign("ttsEngine", alertPrefs.engine);
  const playerSelect = byId("ttsPlayer");
  if (playerSelect) {
    for (const option of playerSelect.children || [])
      option.selected = alertPrefs.players.includes(option.value);
  }
  assign("ttsQuietStart", alertPrefs.quietStart);
  assign("ttsQuietEnd", alertPrefs.quietEnd);
  assign("ttsQuietBypass", alertPrefs.quietBypass, "checked");
  for (const event of ALERT_EVENT_KEYS)
    assign(
      alertEventInputId(event),
      alertPrefs.events[event] !== false,
      "checked",
    );
}

function saveAlertPrefs() {
  alertPrefs.engine = byId("ttsEngine")?.value || "off";
  alertPrefs.players = [...(byId("ttsPlayer")?.children || [])]
    .filter((option) => option.selected)
    .map((option) => option.value);
  alertPrefs.quietStart = byId("ttsQuietStart")?.value || "";
  alertPrefs.quietEnd = byId("ttsQuietEnd")?.value || "";
  alertPrefs.quietBypass = byId("ttsQuietBypass")?.checked !== false;
  for (const event of ALERT_EVENT_KEYS) {
    alertPrefs.events[event] =
      byId(alertEventInputId(event))?.checked !== false;
  }
  window.localStorage?.setItem(alertStorageKey(), JSON.stringify(alertPrefs));
}

function populateAlertEntities() {
  const engine = byId("ttsEngine");
  const player = byId("ttsPlayer");
  if (!engine || !player || engine.dataset.populated) return;
  const states = window.hass?.states || {};
  for (const entityId of Object.keys(states).sort()) {
    if (entityId.startsWith("tts.")) {
      const option = document.createElement("option");
      option.value = entityId;
      option.textContent =
        states[entityId]?.attributes?.friendly_name || entityId;
      engine.appendChild(option);
    } else if (entityId.startsWith("media_player.")) {
      const option = document.createElement("option");
      option.value = entityId;
      option.textContent =
        states[entityId]?.attributes?.friendly_name || entityId;
      player.appendChild(option);
    }
  }
  engine.dataset.populated = "1";
  engine.value = alertPrefs.engine;
  for (const option of player.children || [])
    option.selected = alertPrefs.players.includes(option.value);
}

function isQuietTime(minutes) {
  if (!alertPrefs.quietStart || !alertPrefs.quietEnd) return false;
  const parse = (text) => {
    const [hours, mins] = String(text).split(":").map(Number);
    return Number.isFinite(hours) && Number.isFinite(mins)
      ? hours * 60 + mins
      : null;
  };
  const start = parse(alertPrefs.quietStart);
  const end = parse(alertPrefs.quietEnd);
  if (start === null || end === null) return false;
  const now =
    minutes ??
    (() => {
      const d = new Date();
      return d.getHours() * 60 + d.getMinutes();
    })();
  return start <= end ? now >= start && now < end : now >= start || now < end;
}

function speak(message) {
  if (alertPrefs.engine === "browser") {
    try {
      const Utterance = window.SpeechSynthesisUtterance;
      if (window.speechSynthesis?.speak && Utterance)
        window.speechSynthesis.speak(new Utterance(message));
    } catch {
      /* speech unavailable */
    }
    return;
  }
  if (
    !alertPrefs.engine ||
    alertPrefs.engine === "off" ||
    !alertPrefs.players.length
  )
    return;
  for (const player of alertPrefs.players) {
    try {
      hassApi()
        .callApi("POST", "services/tts/speak", {
          entity_id: alertPrefs.engine,
          media_player_entity_id: player,
          message,
        })
        .catch(() => {});
    } catch {
      /* no hass api */
    }
  }
}

function announce(kind, message) {
  if (!alertPrefs.events[kind]) return;
  const severe = kind === "error" || kind === "runout";
  if (isQuietTime() && !(severe && alertPrefs.quietBypass)) return;
  const key = `${kind}:${message}`;
  const now = Date.now();
  if (key === alertState.lastKey && now - alertState.lastAt < 60000) return;
  alertState.lastKey = key;
  alertState.lastAt = now;
  speak(message);
}

function checkAlerts(data) {
  loadAlertPrefs();
  const status = data?.status || {};
  const printState = String(status.print_stats?.state || "");
  const klippy = String(data?.printer_info?.state || "");
  const filename = status.print_stats?.filename || "the print";
  const active = printState === "printing" || printState === "paused";
  const runout =
    active &&
    Object.entries(status).some(
      ([name, value]) =>
        name.startsWith("filament_switch_sensor") &&
        value?.filament_detected === false,
    );

  if (!alertState.seeded) {
    alertState.seeded = true;
    alertState.state = printState;
    alertState.klippy = klippy;
    alertState.filamentOk = !runout;
    return;
  }

  if (printState !== alertState.state) {
    const previous = alertState.state;
    alertState.state = printState;
    if (printState === "printing" && previous === "paused")
      announce("start", "Print resumed");
    else if (printState === "printing") {
      alertState.milestone = -1;
      clearTimelapse();
      announce("start", `Print started: ${filename}`);
    } else if (printState === "paused") announce("pause", "Print paused");
    else if (printState === "complete") {
      announce("finish", `Print complete: ${filename}`);
      showJobDoneCard(data);
    } else if (printState === "cancelled")
      announce("finish", `Print cancelled: ${filename}`);
    else if (printState === "error")
      announce("error", `Print error: ${filename}`);
    const transitionToast = {
      printing:
        previous === "paused" ? "PRINT RESUMED" : `PRINT STARTED / ${filename}`,
      paused: "PRINT PAUSED",
      complete: `BUILD COMPLETE / ${filename}`,
      cancelled: `PRINT CANCELLED / ${filename}`,
      error: `PRINT ERROR / ${filename}`,
    }[printState];
    if (transitionToast) toast(transitionToast, 6000);
  }

  if (printState === "printing") {
    const percent = getLiveProgress(data) * 100;
    for (const mark of [25, 50, 75, 90]) {
      if (percent >= mark && alertState.milestone < mark) {
        alertState.milestone = mark;
        announce("progress", `Print is ${mark} percent complete`);
        break;
      }
    }
  }

  if (runout && alertState.filamentOk) {
    alertState.filamentOk = false;
    announce("runout", "Filament runout detected");
  } else if (!runout) {
    alertState.filamentOk = true;
  }

  if (klippy && klippy !== alertState.klippy) {
    alertState.klippy = klippy;
    if (klippy === "error" || klippy === "shutdown")
      announce("error", `Printer fault: Klippy reports ${klippy}`);
  }
}

function showJobDoneCard(data) {
  const card = byId("jobDoneCard");
  if (!card) return;
  const stats = data?.status?.print_stats || {};
  const info = stats.info || {};
  const meta = data?.meta || {};
  setText("jobDoneName", String(stats.filename || "—").toUpperCase());
  setText(
    "jobDoneTime",
    duration(stats.print_duration ?? stats.total_duration),
  );
  const estimate = Number(meta.estimated_time);
  const actual = Number(stats.print_duration);
  setText(
    "jobDoneDelta",
    Number.isFinite(estimate) && estimate > 0 && Number.isFinite(actual)
      ? `${actual >= estimate ? "+" : "−"}${Math.abs(
          ((actual - estimate) / estimate) * 100,
        ).toFixed(0)}%`
      : "—",
  );
  setText("jobDoneFil", `${fmt((stats.filament_used || 0) / 1000, 2)} m`);
  setText(
    "jobDoneLayers",
    `${info.current_layer ?? "—"} / ${
      info.total_layer ?? meta.layer_count ?? "—"
    }`,
  );
  const image = byId("jobDoneThumb");
  if (image) {
    if (data.meta?.thumbnails_path)
      loadAuthedImage(image, `${API.thumb(data.entry_id)}&t=${Date.now()}`);
    else clearAuthedImage(image);
  }
  const photo = byId("jobDonePhoto");
  if (photo) {
    const camera = timelapseCamera();
    if (camera) loadAuthedImage(photo, API.snapshot(printer, camera.name));
    else clearAuthedImage(photo);
  }
  const reprint = byId("jobDoneReprint");
  if (reprint) {
    reprint.dataset.value = stats.filename || "";
    reprint.disabled = true;
  }
  const cleared = byId("bedCleared");
  if (cleared) cleared.checked = false;
  card.hidden = false;
}

function hideJobDoneCard() {
  const card = byId("jobDoneCard");
  if (card) card.hidden = true;
}

const DISPLAY_DEFAULTS = {
  largeTouch: false,
  reduceMotion: false,
  theme: "nexus",
  textSize: "normal",
  colorSafe: false,
  language: "auto",
};

// CSS custom properties a theme may set. Color vars require a color value;
// font vars accept a font-family stack.
const THEME_COLOR_VARS = [
  "--bg",
  "--panel",
  "--panel-hi",
  "--line",
  "--line-hi",
  "--green",
  "--green-soft",
  "--cyan",
  "--red",
  "--amber",
  "--text",
  "--muted",
  "--glow",
  "--grid",
  "--input-bg",
  "--input-text",
  "--input-line",
  "--on-accent",
];
const THEME_FONT_VARS = ["--mono", "--sans"];
const THEME_VARS = [...THEME_COLOR_VARS, ...THEME_FONT_VARS];
// Vars every theme file must define.
const THEME_OPTIONAL_COLOR_VARS = [
  "--glow",
  "--grid",
  "--input-bg",
  "--input-text",
  "--input-line",
  "--on-accent",
];
const THEME_REQUIRED_VARS = THEME_COLOR_VARS.filter(
  (name) => !THEME_OPTIONAL_COLOR_VARS.includes(name),
);

const THEMES = {
  nexus: {
    label: "NEXUS DARK",
    vars: {},
  },
  midnight: {
    label: "MIDNIGHT OPS",
    vars: {
      "--input-bg": "#071122",
      "--input-text": "#c8dcf0",
      "--input-line": "#1d3a5f",
      "--on-accent": "#03101f",
      "--bg": "#050b16",
      "--panel": "#0a1424",
      "--panel-hi": "#101d33",
      "--line": "#1d3a5f",
      "--line-hi": "#2f6db3",
      "--green": "#4ade80",
      "--green-soft": "#a7f3c9",
      "--cyan": "#4fc3ff",
      "--red": "#ff5d73",
      "--amber": "#f5b94e",
      "--text": "#c8dcf0",
      "--muted": "#5d7d9e",
      "--glow": "rgba(79, 195, 255, 0.1)",
      "--grid": "rgba(47, 109, 179, 0.06)",
    },
  },
  ember: {
    label: "EMBER FORGE",
    vars: {
      "--input-bg": "#170d07",
      "--input-text": "#f0dcc8",
      "--input-line": "#57301a",
      "--on-accent": "#1c0e05",
      "--bg": "#130a05",
      "--panel": "#1c110a",
      "--panel-hi": "#291a10",
      "--line": "#57301a",
      "--line-hi": "#a35a26",
      "--green": "#ffb454",
      "--green-soft": "#ffd8a8",
      "--cyan": "#ff8a5c",
      "--red": "#ff5470",
      "--amber": "#f5d020",
      "--text": "#f0dcc8",
      "--muted": "#96755c",
      "--glow": "rgba(255, 138, 76, 0.1)",
      "--grid": "rgba(163, 90, 38, 0.07)",
    },
  },
  carbon: {
    label: "CARBON",
    vars: {
      "--input-bg": "#0e1216",
      "--input-text": "#d7dde4",
      "--input-line": "#2c343e",
      "--on-accent": "#0b0d10",
      "--bg": "#0c0e11",
      "--panel": "#13161b",
      "--panel-hi": "#1b2027",
      "--line": "#2c343e",
      "--line-hi": "#4a5563",
      "--green": "#7dc4ff",
      "--green-soft": "#bfe1ff",
      "--cyan": "#8fd0d8",
      "--red": "#e46a76",
      "--amber": "#d9b13b",
      "--text": "#d7dde4",
      "--muted": "#6e7a88",
      "--glow": "rgba(125, 196, 255, 0.07)",
      "--grid": "rgba(90, 100, 110, 0.07)",
    },
  },
  solarized: {
    label: "SOLARIZED DARK",
    vars: {
      "--input-bg": "#073642",
      "--input-text": "#93a1a1",
      "--input-line": "#164f5c",
      "--on-accent": "#002b36",
      "--bg": "#002b36",
      "--panel": "#073642",
      "--panel-hi": "#0b4553",
      "--line": "#164f5c",
      "--line-hi": "#2a6b78",
      "--green": "#859900",
      "--green-soft": "#b7c95c",
      "--cyan": "#2aa198",
      "--red": "#dc322f",
      "--amber": "#b58900",
      "--text": "#93a1a1",
      "--muted": "#586e75",
      "--glow": "rgba(42, 161, 152, 0.1)",
      "--grid": "rgba(42, 161, 152, 0.07)",
    },
  },
  solarized_light: {
    label: "SOLARIZED LIGHT",
    vars: {
      "--input-bg": "#eee8d5",
      "--input-text": "#586e75",
      "--input-line": "#c8bfa2",
      "--on-accent": "#fdf6e3",
      "--bg": "#fdf6e3",
      "--panel": "#eee8d5",
      "--panel-hi": "#e3dcc3",
      "--line": "#c8bfa2",
      "--line-hi": "#a89a76",
      "--green": "#719e07",
      "--green-soft": "#4a6b04",
      "--cyan": "#2aa198",
      "--red": "#dc322f",
      "--amber": "#b58900",
      "--text": "#586e75",
      "--muted": "#93a1a1",
      "--glow": "rgba(42, 161, 152, 0.08)",
      "--grid": "rgba(101, 123, 131, 0.1)",
    },
  },
  violet: {
    label: "VIOLET GRID",
    vars: {
      "--input-bg": "#150a26",
      "--input-text": "#d8cdea",
      "--input-line": "#41286b",
      "--on-accent": "#100420",
      "--bg": "#11071f",
      "--panel": "#1a0d2e",
      "--panel-hi": "#251542",
      "--line": "#41286b",
      "--line-hi": "#6b47ab",
      "--green": "#b07dff",
      "--green-soft": "#d9c2ff",
      "--cyan": "#5ce8d5",
      "--red": "#ff5c8a",
      "--amber": "#f0c75e",
      "--text": "#d8cdea",
      "--muted": "#7d6a9e",
      "--glow": "rgba(176, 125, 255, 0.11)",
      "--grid": "rgba(107, 71, 171, 0.08)",
    },
  },
  arctic: {
    label: "ARCTIC",
    vars: {
      "--input-bg": "#ffffff",
      "--input-text": "#20344a",
      "--input-line": "#c3d3e0",
      "--on-accent": "#ffffff",
      "--bg": "#e8f0f6",
      "--panel": "#f4f8fb",
      "--panel-hi": "#ffffff",
      "--line": "#c3d3e0",
      "--line-hi": "#88aac4",
      "--green": "#1a8754",
      "--green-soft": "#0d5c38",
      "--cyan": "#1177a8",
      "--red": "#c92a42",
      "--amber": "#9c7a12",
      "--text": "#20344a",
      "--muted": "#5f7e96",
      "--glow": "rgba(23, 119, 168, 0.08)",
      "--grid": "rgba(70, 100, 125, 0.08)",
    },
  },
  stealth: {
    label: "STEALTH",
    vars: {
      "--input-bg": "#050505",
      "--input-text": "#9aa5ae",
      "--input-line": "#1f1f1f",
      "--on-accent": "#000000",
      "--bg": "#050505",
      "--panel": "#0a0a0a",
      "--panel-hi": "#101010",
      "--line": "#1f1f1f",
      "--line-hi": "#383838",
      "--green": "#8f9aa3",
      "--green-soft": "#c3ccd4",
      "--cyan": "#7d97a8",
      "--red": "#b0575f",
      "--amber": "#a89563",
      "--text": "#9aa5ae",
      "--muted": "#4a525a",
      "--glow": "rgba(150, 160, 170, 0.05)",
      "--grid": "rgba(80, 88, 96, 0.05)",
    },
  },
  clinical: {
    label: "CLINICAL",
    vars: {
      "--input-bg": "#ffffff",
      "--input-text": "#1e2a33",
      "--input-line": "#c9d4dc",
      "--on-accent": "#ffffff",
      "--bg": "#f2f5f7",
      "--panel": "#ffffff",
      "--panel-hi": "#e9eef2",
      "--line": "#c9d4dc",
      "--line-hi": "#7c9bad",
      "--green": "#157a4e",
      "--green-soft": "#0c5234",
      "--cyan": "#0e7490",
      "--red": "#be123c",
      "--amber": "#a16207",
      "--text": "#1e2a33",
      "--muted": "#5c7383",
      "--glow": "rgba(14, 116, 144, 0.07)",
      "--grid": "rgba(90, 110, 125, 0.08)",
    },
  },
};

// Structural themes handled by CSS in panel.html rather than a var map.
const STRUCTURAL_THEMES = ["daylight", "contrast"];
const CUSTOM_THEMES_KEY = "nexus-custom-themes";
let customThemes = {};

const DISPLAY_THEMES = Object.keys(THEMES).concat(STRUCTURAL_THEMES, ["auto"]);
const DISPLAY_TEXT_SIZES = ["normal", "large", "xlarge"];
const DISPLAY_CONTROL_IDS = [
  "displayLargeTouch",
  "displayReduceMotion",
  "displayTheme",
  "displayTextSize",
  "displayColorSafe",
  "displayLanguage",
];
let displayPrefs = { ...DISPLAY_DEFAULTS };

function loadDisplayPrefs() {
  const key = `nexus-display:${printer}`;
  loadCustomThemes();
  if (key === displayPrefsKey) {
    if (displayPrefs.theme === "auto") applyTheme();
    return;
  }
  displayPrefsKey = key;
  try {
    displayPrefs = {
      ...DISPLAY_DEFAULTS,
      ...(JSON.parse(window.localStorage?.getItem(key) || "null") || {}),
    };
  } catch {
    displayPrefs = { ...DISPLAY_DEFAULTS };
  }
  applyDisplayPrefs();
}

function readDisplayControls() {
  const theme = byId("displayTheme")?.value;
  const textSize = byId("displayTextSize")?.value;
  displayPrefs = {
    ...displayPrefs,
    largeTouch: byId("displayLargeTouch")?.checked === true,
    reduceMotion: byId("displayReduceMotion")?.checked === true,
    colorSafe: byId("displayColorSafe")?.checked === true,
    theme:
      theme === "auto" || (theme && resolveTheme(theme) === theme)
        ? theme
        : "nexus",
    textSize: DISPLAY_TEXT_SIZES.includes(textSize) ? textSize : "normal",
    language: byId("displayLanguage")?.value || "auto",
  };
}

function resolveTheme(choice) {
  if (
    choice &&
    choice !== "auto" &&
    (THEMES[choice] ||
      STRUCTURAL_THEMES.includes(choice) ||
      customThemes[choice])
  )
    return choice;
  if (choice !== "auto") return "nexus";
  const darkMode = window.hass?.themes?.darkMode;
  if (typeof darkMode === "boolean") return darkMode ? "nexus" : "daylight";
  try {
    return window.matchMedia?.("(prefers-color-scheme: light)")?.matches
      ? "daylight"
      : "nexus";
  } catch {
    return "nexus";
  }
}

function clearThemeVars() {
  const style = document.documentElement?.style;
  if (!style) return;
  for (const name of THEME_VARS) style.removeProperty(name);
}

function applyTheme() {
  const root = document.documentElement;
  if (!root?.dataset) return;
  const theme = resolveTheme(displayPrefs.theme);
  clearThemeVars();
  if (theme === "nexus") {
    delete root.dataset.theme;
    return;
  }
  root.dataset.theme = theme;
  const vars = (THEMES[theme] || customThemes[theme] || {}).vars;
  if (vars && root.style)
    for (const [name, value] of Object.entries(vars))
      root.style.setProperty(name, value);
}

function validateTheme(data) {
  const errors = [];
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return { ok: false, errors: ["theme file must be a JSON object"] };
  }
  if (
    typeof data.name !== "string" ||
    !data.name.trim() ||
    data.name.length > 50
  )
    errors.push('"name" must be a string of 1-50 characters');
  const vars = data.vars;
  if (!vars || typeof vars !== "object" || Array.isArray(vars)) {
    errors.push('"vars" must be an object of CSS custom properties');
    return { ok: false, errors };
  }
  const colorPattern =
    /^(#[0-9a-f]{3,4}|#[0-9a-f]{6}|#[0-9a-f]{8}|rgba?\([\d\s.,%]+\)|hsla?\([\d\s.,%deg]+\))$/i;
  const fontPattern = /^[\w\s'",.-]{1,120}$/;
  for (const name of THEME_REQUIRED_VARS)
    if (typeof vars[name] !== "string")
      errors.push(`missing required variable "${name}"`);
  for (const [name, value] of Object.entries(vars)) {
    if (!THEME_VARS.includes(name)) {
      errors.push(`unknown variable "${name}"`);
      continue;
    }
    if (typeof value !== "string") {
      errors.push(`"${name}" must be a string`);
      continue;
    }
    if (
      THEME_COLOR_VARS.includes(name)
        ? !colorPattern.test(value.trim())
        : !fontPattern.test(value)
    )
      errors.push(`"${name}" has an invalid value`);
  }
  return { ok: errors.length === 0, errors };
}

function themeKeyFor(name) {
  return `custom:${name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")}`;
}

function loadCustomThemes() {
  try {
    const raw = JSON.parse(
      window.localStorage?.getItem(CUSTOM_THEMES_KEY) || "{}",
    );
    customThemes =
      raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  } catch {
    customThemes = {};
  }
}

function saveCustomThemes() {
  try {
    window.localStorage?.setItem(
      CUSTOM_THEMES_KEY,
      JSON.stringify(customThemes),
    );
  } catch {
    /* storage unavailable */
  }
}

function handleThemeUpload(file) {
  const status = byId("themeUploadStatus");
  const say = (msg) => {
    if (status) status.textContent = msg;
  };
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(String(reader.result || ""));
      const result = validateTheme(data);
      if (!result.ok) {
        say(`Theme rejected: ${result.errors.join("; ")}`);
        return;
      }
      const key = themeKeyFor(data.name);
      customThemes[key] = {
        label: data.name.trim().toUpperCase(),
        vars: data.vars,
      };
      saveCustomThemes();
      populateThemeSelect();
      displayPrefs.theme = key;
      saveDisplayPrefs();
      applyDisplayPrefs();
      say(`Theme "${data.name.trim()}" installed`);
    } catch {
      say("Theme rejected: not valid JSON");
    }
  };
  reader.onerror = () => say("Theme rejected: could not read file");
  reader.readAsText(file);
}

function populateThemeSelect() {
  const select = byId("displayTheme");
  if (!select) return;
  select.replaceChildren();
  const add = (value, label) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.append(option);
  };
  for (const [key, theme] of Object.entries(THEMES)) add(key, theme.label);
  add("daylight", "DAYLIGHT");
  add("contrast", "HIGH CONTRAST");
  for (const [key, theme] of Object.entries(customThemes))
    add(key, `${theme.label} (CUSTOM)`);
  add("auto", "FOLLOW HOME ASSISTANT");
}

function saveDisplayPrefs() {
  try {
    window.localStorage?.setItem(displayPrefsKey, JSON.stringify(displayPrefs));
  } catch {
    /* storage unavailable */
  }
}

function reducedMotionPreferred() {
  if (displayPrefs.reduceMotion) return true;
  try {
    return (
      window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true
    );
  } catch {
    return false;
  }
}

function applyDisplayPrefs() {
  document.body?.classList?.toggle?.("large-touch", displayPrefs.largeTouch);
  document.body?.classList?.toggle?.(
    "reduced-motion",
    reducedMotionPreferred(),
  );
  const largeTouch = byId("displayLargeTouch");
  if (largeTouch) largeTouch.checked = displayPrefs.largeTouch;
  const reduceMotion = byId("displayReduceMotion");
  if (reduceMotion) reduceMotion.checked = displayPrefs.reduceMotion;
  const colorSafe = byId("displayColorSafe");
  if (colorSafe) colorSafe.checked = displayPrefs.colorSafe;
  const theme = byId("displayTheme");
  if (theme) {
    if (!theme.options || !theme.options.length) populateThemeSelect();
    theme.value = displayPrefs.theme;
  }
  const textSize = byId("displayTextSize");
  if (textSize) textSize.value = displayPrefs.textSize;
  const language = byId("displayLanguage");
  if (language) language.value = displayPrefs.language;
  const root = document.documentElement;
  if (root?.dataset) {
    if (displayPrefs.textSize === "normal") delete root.dataset.textSize;
    else root.dataset.textSize = displayPrefs.textSize;
    if (displayPrefs.colorSafe) root.dataset.colorSafe = "1";
    else delete root.dataset.colorSafe;
  }
  applyTheme();
  applyPanelLanguage(displayPrefs.language);
}

function cssVar(name, fallback) {
  const root = document.documentElement;
  const inline = root?.style?.getPropertyValue?.(name) || root?.style?.[name];
  if (inline) return String(inline).trim();
  const computed = window.getComputedStyle?.(root)?.getPropertyValue?.(name);
  const value = computed && String(computed).trim();
  return value || fallback;
}

function cssRgbTriplet(name, fallback) {
  const raw = cssVar(name, "");
  const hex = raw.match(/^#([0-9a-f]{3,8})$/i);
  if (hex) {
    let digits = hex[1];
    if (digits.length === 3 || digits.length === 4)
      digits = digits
        .split("")
        .map((char) => char + char)
        .join("");
    return `${parseInt(digits.slice(0, 2), 16)}, ${parseInt(
      digits.slice(2, 4),
      16,
    )}, ${parseInt(digits.slice(4, 6), 16)}`;
  }
  const rgb = raw.match(/^rgba?\(([^)]+)\)$/);
  if (rgb) return rgb[1].split(",").slice(0, 3).join(",");
  return fallback;
}

function cssRgba(name, alpha, fallback) {
  return `rgba(${cssRgbTriplet(name, "") || fallback}, ${alpha})`;
}

function statusRgb(kind) {
  const safe = displayPrefs.colorSafe;
  return kind === "bad"
    ? safe
      ? "255, 122, 61"
      : cssRgbTriplet("--red", "255, 83, 107")
    : safe
      ? "86, 180, 233"
      : cssRgbTriplet("--green", "0, 239, 145");
}

async function loadFileAnalysis(filename) {
  const card = byId("fileAnalysis");
  const empty = byId("analysisEmpty");
  if (!card) return;
  analysisFile = filename || "";
  if (!filename) {
    card.hidden = true;
    const verdict = byId("analysisVerdict");
    if (verdict) verdict.hidden = true;
    if (empty) empty.hidden = false;
    setText("analysisStatus", "SELECT A FILE");
    setText("analysisName", "FILE ANALYSIS");
    return;
  }
  if (empty) empty.hidden = true;
  card.hidden = false;
  setText("analysisName", String(filename).toUpperCase());
  setText("analysisStatus", "READING SLICER METADATA…");
  byId("analysisStats")?.replaceChildren();
  byId("analysisWarnings")?.replaceChildren();
  try {
    const meta = await hassApi().callApi(
      "GET",
      `moonraker/panel_file_meta?printer=${encodeURIComponent(
        printer,
      )}&filename=${encodeURIComponent(filename)}`,
    );
    if (analysisFile !== filename) return;
    renderFileAnalysis(meta);
  } catch (_error) {
    if (analysisFile === filename)
      setText("analysisStatus", "METADATA UNAVAILABLE");
  }
}

function renderFileAnalysis(meta) {
  const empty = byId("analysisEmpty");
  if (empty) empty.hidden = true;
  if (!meta || meta.error) {
    const verdict = byId("analysisVerdict");
    if (verdict) verdict.hidden = true;
    setText(
      "analysisStatus",
      meta?.error ? String(meta.error).toUpperCase() : "METADATA UNAVAILABLE",
    );
    return;
  }
  const warnings = [];
  const blockers = [];
  const status = latestData?.status || {};
  const axisMax = status.toolhead?.axis_maximum;
  const bedBounds = latestData?.bed_bounds || {};
  const xMax = Number.isFinite(bedBounds.x?.max)
    ? bedBounds.x.max
    : axisMax?.[0];
  const yMax = Number.isFinite(bedBounds.y?.max)
    ? bedBounds.y.max
    : axisMax?.[1];
  const zMax = Number.isFinite(bedBounds.z?.max)
    ? bedBounds.z.max
    : axisMax?.[2];
  const hasBounds = [meta.x_min, meta.x_max, meta.y_min, meta.y_max].every(
    (value) => Number.isFinite(Number(value)),
  );
  const spoolDetails = latestData?.spool_details || {};
  const spoolFilament = spoolDetails.filament || {};
  const stats = [
    ["ESTIMATED TIME", duration(meta.estimated_time)],
    [
      "FILAMENT",
      meta.filament_total != null
        ? `${fmt(Number(meta.filament_total) / 1000, 2)} m`
        : "—",
    ],
    ["LAYERS", meta.layer_count ?? "—"],
    [
      "OBJECT HEIGHT",
      meta.object_height != null ? `${fmt(meta.object_height)} mm` : "—",
    ],
    [
      "SLICER",
      [meta.slicer, meta.slicer_version].filter(Boolean).join(" ") || "—",
    ],
    [
      "FIRST LAYER",
      meta.first_layer_height != null ? `${meta.first_layer_height} mm` : "—",
    ],
    [
      "NOZZLE / BED",
      `${meta.first_layer_extr_temp ?? "—"}° / ${
        meta.first_layer_bed_temp ?? "—"
      }°`,
    ],
  ];
  if (spoolFilament.name || spoolFilament.material) {
    const spoolLabel = [
      spoolFilament.vendor,
      spoolFilament.name || spoolFilament.material,
      spoolFilament.material && spoolFilament.name
        ? `(${spoolFilament.material})`
        : "",
    ]
      .filter(Boolean)
      .join(" ");
    stats.push([
      "ACTIVE SPOOL",
      `${spoolLabel}${
        Number.isFinite(Number(spoolDetails.remaining_weight))
          ? ` · ${fmt(spoolDetails.remaining_weight, 0)} g LEFT`
          : ""
      }`,
    ]);
  }
  if (hasBounds) {
    stats.push([
      "OBJECT BOUNDS",
      `X ${fmt(meta.x_min, 0)}–${fmt(meta.x_max, 0)} · Y ${fmt(
        meta.y_min,
        0,
      )}–${fmt(meta.y_max, 0)}`,
    ]);
    if (
      Number.isFinite(xMax) &&
      (meta.x_min < -0.5 || meta.x_max > xMax + 0.5)
    ) {
      blockers.push(`OBJECT EXCEEDS BED X RANGE (0–${fmt(xMax, 0)} MM)`);
    }
    if (
      Number.isFinite(yMax) &&
      (meta.y_min < -0.5 || meta.y_max > yMax + 0.5)
    ) {
      blockers.push(`OBJECT EXCEEDS BED Y RANGE (0–${fmt(yMax, 0)} MM)`);
    }
    if (
      Number.isFinite(zMax) &&
      Number.isFinite(Number(meta.object_height)) &&
      Number(meta.object_height) > zMax + 0.5
    ) {
      blockers.push(`OBJECT EXCEEDS Z HEIGHT (MAX ${fmt(zMax, 0)} MM)`);
    }
  } else {
    warnings.push("OBJECT BOUNDS NOT REPORTED BY SLICER");
  }
  if (!meta.has_thumbnail) warnings.push("NO EMBEDDED THUMBNAIL");
  if (!meta.layer_count) warnings.push("LAYER COUNT NOT REPORTED");
  if (!meta.estimated_time) warnings.push("PRINT TIME NOT ESTIMATED BY SLICER");
  const remainingWeight = Number(spoolDetails.remaining_weight);
  const neededWeight = Number(meta.filament_weight_total);
  if (
    Number.isFinite(remainingWeight) &&
    Number.isFinite(neededWeight) &&
    neededWeight > 0
  ) {
    if (neededWeight > remainingWeight) {
      blockers.push(
        `NEEDS ${fmt(neededWeight, 0)} G BUT SPOOL HOLDS ${fmt(
          remainingWeight,
          0,
        )} G`,
      );
    } else if (neededWeight > remainingWeight * 0.9) {
      warnings.push(
        `FILAMENT TIGHT — ${fmt(neededWeight, 0)} G OF ${fmt(
          remainingWeight,
          0,
        )} G REMAINING`,
      );
    }
  }
  const remainingLength = Number(spoolDetails.remaining_length);
  const neededLength = Number(meta.filament_total);
  if (
    !Number.isFinite(neededWeight) &&
    Number.isFinite(remainingLength) &&
    Number.isFinite(neededLength) &&
    neededLength > remainingLength
  ) {
    blockers.push(
      `NEEDS ${fmt(neededLength / 1000, 1)} M BUT SPOOL HOLDS ${fmt(
        remainingLength / 1000,
        1,
      )} M`,
    );
  }
  const metaMaterial = String(meta.filament_type || "")
    .trim()
    .toUpperCase();
  const spoolMaterial = String(spoolFilament.material || "")
    .trim()
    .toUpperCase();
  if (
    metaMaterial &&
    spoolMaterial &&
    !spoolMaterial.startsWith(metaMaterial) &&
    !metaMaterial.startsWith(spoolMaterial)
  ) {
    blockers.push(
      `MATERIAL MISMATCH — FILE WANTS ${metaMaterial}, SPOOL IS ${spoolMaterial}`,
    );
  }
  if (Number.isFinite(Number(meta.estimated_time)) && meta.estimated_time > 0) {
    const finish = new Date(Date.now() + Number(meta.estimated_time) * 1000);
    if (isQuietTime(finish.getHours() * 60 + finish.getMinutes())) {
      warnings.push("PRINT FINISHES DURING QUIET HOURS");
    }
  }
  const verdict = byId("analysisVerdict");
  if (verdict) {
    verdict.hidden = false;
    verdict.classList.remove("ok-text", "warn-text", "bad-text");
    if (blockers.length) {
      verdict.textContent = "NO-GO";
      verdict.classList.add("bad-text");
    } else if (warnings.length) {
      verdict.textContent = "CAUTION";
      verdict.classList.add("warn-text");
    } else {
      verdict.textContent = "GO";
      verdict.classList.add("ok-text");
    }
  }
  setText(
    "analysisStatus",
    `${meta.size ? `${(meta.size / 1048576).toFixed(1)} MB · ` : ""}${
      blockers.length ? "BLOCKED" : "READY"
    }`,
  );
  const statsContainer = byId("analysisStats");
  if (statsContainer) {
    statsContainer.replaceChildren();
    stats.forEach(([key, value]) => {
      const row = document.createElement("div");
      row.className = "system-item";
      const label = document.createElement("span");
      label.textContent = key;
      const text = document.createElement("span");
      text.textContent = value;
      row.append(label, text);
      statsContainer.appendChild(row);
    });
  }
  const warningsContainer = byId("analysisWarnings");
  if (warningsContainer) {
    warningsContainer.replaceChildren();
    blockers.forEach((text) => {
      const item = document.createElement("div");
      item.className = "analysis-warning bad-text";
      item.textContent = `⛔ ${text}`;
      warningsContainer.appendChild(item);
    });
    warnings.forEach((text) => {
      const item = document.createElement("div");
      item.className = "analysis-warning";
      item.textContent = `⚠ ${text}`;
      warningsContainer.appendChild(item);
    });
  }
  const thumb = byId("analysisThumb");
  if (thumb) {
    if (meta.has_thumbnail)
      loadAuthedImage(
        thumb,
        `${API.thumb(printer)}&filename=${encodeURIComponent(
          analysisFile,
        )}&t=${Date.now()}`,
      );
    else clearAuthedImage(thumb);
  }
}

function timelapseCameras() {
  const cameras = dashboardCameraAssignments
    .filter(Boolean)
    .map((name) =>
      availableWebcams.find((candidate) => candidate.name === name),
    )
    .filter((camera) => camera?.snapshot_url);
  if (cameras.length) return cameras;
  const fallback = availableWebcams.find((candidate) => candidate.snapshot_url);
  return fallback ? [fallback] : [];
}

function timelapseCamera() {
  return timelapseCameras()[0] || null;
}

function maybeTimelapse(data, currentLayer) {
  const layer = Number(currentLayer);
  if (data?.status?.print_stats?.state !== "printing") {
    if (liveLayer !== null) liveLayer = null;
    return;
  }
  if (!Number.isFinite(layer) || layer <= 0) return;
  if (liveLayer === null || liveLayer === undefined) {
    liveLayer = layer;
    return;
  }
  if (layer > liveLayer) {
    liveLayer = layer;
    captureTimelapseFrame();
  }
}

async function captureTimelapseFrame() {
  const cameras = timelapseCameras();
  if (!cameras.length || timelapseAbort) return;
  const controller = new AbortController();
  const generation = timelapseGeneration;
  timelapseAbort = controller;
  const headPosition = currentToolheadPosition();
  const entry = {
    layer: liveLayer,
    z: headPosition ? headPosition[2] : null,
    shots: {},
    size: 0,
  };
  try {
    for (const camera of cameras) {
      if (generation !== timelapseGeneration) return;
      try {
        const response = await hassApi().fetchWithAuth(
          API.snapshot(printer, camera.name),
          { signal: controller.signal },
        );
        if (!response?.ok) continue;
        const contentLength = Number(response.headers?.get?.("Content-Length"));
        if (contentLength > MAX_TIMELAPSE_BYTES) {
          await response.body?.cancel?.();
          continue;
        }
        const blob = await response.blob();
        if (!blob.size || blob.size > MAX_TIMELAPSE_BYTES) continue;
        const url = URL.createObjectURL(blob);
        entry.shots[camera.name] = { url, size: blob.size };
        entry.size += blob.size;
      } catch {
        /* camera snapshot optional */
      }
    }
    if (generation !== timelapseGeneration) return;
    if (!Object.keys(entry.shots).length) return;
    timelapseFrames.push(entry);
    timelapseBytes += entry.size;
    evictTimelapseFrames();
    renderTimelapseStatus(true);
  } finally {
    if (timelapseAbort === controller) timelapseAbort = null;
    if (!timelapseFrames.includes(entry)) revokeTimelapseEntry(entry);
  }
}

function revokeTimelapseEntry(entry) {
  if (!entry) return;
  for (const shot of Object.values(entry.shots || {})) {
    URL.revokeObjectURL(shot.url);
  }
  if (entry.url) URL.revokeObjectURL(entry.url);
}

function evictTimelapseFrames() {
  while (
    timelapseFrames.length > MAX_TIMELAPSE_FRAMES ||
    timelapseBytes > MAX_TIMELAPSE_BYTES
  ) {
    const oldest = timelapseFrames.shift();
    revokeTimelapseEntry(oldest);
    timelapseBytes -= oldest.size || 0;
  }
}

function syncTimelapseToScrub() {
  if (!timelapseFrames.length || !Number.isFinite(scrubZ)) return;
  let best = 0;
  let bestDelta = Infinity;
  timelapseFrames.forEach((frame, index) => {
    if (frame.z == null) return;
    const delta = Math.abs(frame.z - scrubZ);
    if (delta < bestDelta) {
      bestDelta = delta;
      best = index;
    }
  });
  const scrub = byId("tlScrub");
  if (scrub) scrub.value = best;
  renderTimelapseFrame();
}

function timelapseShotNames() {
  const names = [];
  for (const entry of timelapseFrames) {
    for (const name of Object.keys(entry.shots || {})) {
      if (!names.includes(name)) names.push(name);
    }
  }
  return names;
}

function timelapseEntryShot(entry) {
  const shots = entry?.shots || {};
  if (timelapseViewCamera && shots[timelapseViewCamera]) {
    return shots[timelapseViewCamera];
  }
  return Object.values(shots)[0] || (entry?.url ? entry : null);
}

function renderTimelapseStatus(showLatest = false) {
  const count = timelapseFrames.length;
  setText("tlStatus", `${count} FRAME${count === 1 ? "" : "S"}`);
  const scrub = byId("tlScrub");
  if (scrub) {
    scrub.disabled = !count;
    scrub.max = Math.max(0, count - 1);
    if (showLatest || !count) scrub.value = Math.max(0, count - 1);
  }
  const cameraSelect = byId("tlCamera");
  if (cameraSelect) {
    const names = timelapseShotNames();
    cameraSelect.hidden = names.length < 2;
    if (!names.includes(timelapseViewCamera) && timelapseViewCamera !== "*") {
      timelapseViewCamera = names[0] || "";
    }
    const wanted = [...names, "*"];
    const existing = Array.from(cameraSelect.options || []).map(
      (option) => option.value,
    );
    if (JSON.stringify(existing) !== JSON.stringify(wanted)) {
      cameraSelect.replaceChildren();
      for (const name of wanted) {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name === "*" ? "GRID" : name;
        cameraSelect.appendChild(option);
      }
    }
    cameraSelect.value = timelapseViewCamera || names[0] || "*";
  }
  const empty = byId("tlEmpty");
  if (empty) empty.hidden = count > 0;
  const frame = byId("tlFrame");
  if (frame) frame.hidden = !count || timelapseViewCamera === "*";
  const gridView = byId("tlGrid");
  if (gridView) gridView.hidden = !(count && timelapseViewCamera === "*");
  if (count) renderTimelapseFrame();
}

function renderTimelapseFrame() {
  const scrub = byId("tlScrub");
  const frame = byId("tlFrame");
  const gridView = byId("tlGrid");
  if (!timelapseFrames.length) return;
  const index = Math.min(
    Math.max(Number(scrub?.value) || 0, 0),
    timelapseFrames.length - 1,
  );
  const entry = timelapseFrames[index];
  if (gridView && timelapseViewCamera === "*") {
    gridView.replaceChildren();
    for (const [name, shot] of Object.entries(entry.shots || {})) {
      const cell = document.createElement("div");
      cell.className = "tl-grid-cell";
      const label = document.createElement("span");
      label.className = "tl-grid-name";
      label.textContent = name;
      const image = document.createElement("img");
      image.src = shot.url;
      image.alt = `Timelapse frame ${name}`;
      cell.append(image, label);
      gridView.appendChild(cell);
    }
    gridView.hidden = false;
  }
  if (frame) {
    const shot = timelapseEntryShot(entry);
    if (shot) {
      if (frame.getAttribute("src") !== shot.url) frame.src = shot.url;
      frame.hidden = timelapseViewCamera === "*";
    } else {
      frame.hidden = true;
    }
  }
  setText(
    "tlLayer",
    entry.layer != null ? `LAYER ${entry.layer}` : `FRAME ${index + 1}`,
  );
}

function clearTimelapse() {
  timelapseGeneration += 1;
  if (timelapseAbort) {
    timelapseAbort.abort();
    timelapseAbort = null;
  }
  while (timelapseFrames.length) revokeTimelapseEntry(timelapseFrames.pop());
  timelapseBytes = 0;
  timelapseViewCamera = "";
  const frame = byId("tlFrame");
  if (frame) {
    frame.removeAttribute("src");
    frame.hidden = true;
  }
  const gridView = byId("tlGrid");
  if (gridView) {
    gridView.replaceChildren();
    gridView.hidden = true;
  }
  renderTimelapseStatus();
}

function bindAlertSettings() {
  loadAlertPrefs();
  loadFlowPrefs();
  loadEnergyPrefs();
  for (const id of [
    "ttsEngine",
    "ttsPlayer",
    "ttsQuietStart",
    "ttsQuietEnd",
    "ttsQuietBypass",
    ...ALERT_EVENT_KEYS.map(alertEventInputId),
  ]) {
    byId(id)?.addEventListener?.("change", saveAlertPrefs);
  }
  byId("energySensor")?.addEventListener?.("change", saveEnergyPrefs);
  byId("energyRate")?.addEventListener?.("change", saveEnergyPrefs);
  byId("maxFlowInput")?.addEventListener?.("change", saveFlowPrefs);
  byId("meshRebaseline")?.addEventListener?.("click", resetMeshBaseline);
  byId("ttsTest")?.addEventListener?.("click", () => {
    if (
      alertPrefs.engine !== "browser" &&
      alertPrefs.engine !== "off" &&
      !alertPrefs.players.length
    ) {
      toast("SELECT A MEDIA PLAYER FOR TTS OUTPUT");
      return;
    }
    speak("Nexus control voice alert test");
  });
}

function bindToolpathCanvas() {
  const canvas = byId("toolpathCanvas");
  byId("clipFutureLayers")?.addEventListener?.("change", drawToolpath);
  byId("showFuturePath")?.addEventListener?.("change", drawToolpath);
  const pointers = new Map();
  let lastPinchDistance = 0;
  let panMode = false;

  canvas.addEventListener("pointerdown", (event) => {
    canvas.setPointerCapture?.(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    cameraAnim = null;
    orbitVelocityX = 0;
    orbitVelocityY = 0;
    if (pointers.size === 1) {
      panMode = event.button === 2 || event.shiftKey;
      toolpathCamera.dragging = true;
      toolpathCamera.dragX = event.clientX;
      toolpathCamera.dragY = event.clientY;
    } else if (pointers.size === 2) {
      toolpathCamera.dragging = false;
      const [first, second] = [...pointers.values()];
      lastPinchDistance = Math.hypot(first.x - second.x, first.y - second.y);
    }
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 2) {
      const [first, second] = [...pointers.values()];
      const distance = Math.hypot(first.x - second.x, first.y - second.y);
      if (lastPinchDistance > 0 && distance > 0) {
        toolpathCamera.zoom = Math.max(
          0.45,
          Math.min(3.5, (toolpathCamera.zoom * distance) / lastPinchDistance),
        );
        drawToolpath();
      }
      lastPinchDistance = distance;
      return;
    }
    if (!toolpathCamera.dragging) return;
    const deltaX = event.clientX - toolpathCamera.dragX;
    const deltaY = event.clientY - toolpathCamera.dragY;
    toolpathCamera.dragX = event.clientX;
    toolpathCamera.dragY = event.clientY;
    if (panMode) {
      toolpathCamera.panX += deltaX;
      toolpathCamera.panY += deltaY;
    } else {
      toolpathCamera.yaw += deltaX * 0.009;
      toolpathCamera.pitch = Math.max(
        0.025,
        Math.min(1.55, toolpathCamera.pitch + deltaY * 0.008),
      );
      orbitVelocityX = deltaX * 0.009;
      orbitVelocityY = deltaY * 0.008;
    }
    drawToolpath();
  });
  const endPointer = (event) => {
    pointers.delete(event.pointerId);
    if (pointers.size < 2) lastPinchDistance = 0;
    if (pointers.size === 0) {
      toolpathCamera.dragging = false;
      if (
        !panMode &&
        (Math.abs(orbitVelocityX) > 0.004 || Math.abs(orbitVelocityY) > 0.004)
      )
        startOrbitInertia();
      panMode = false;
    }
  };
  canvas.addEventListener("pointerup", endPointer);
  canvas.addEventListener("pointercancel", endPointer);
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  canvas.addEventListener("dblclick", () => setToolpathView("iso"));
  canvas.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      toolpathCamera.zoom = Math.max(
        0.45,
        Math.min(3.5, toolpathCamera.zoom * (event.deltaY < 0 ? 1.1 : 0.91)),
      );
      drawToolpath();
    },
    { passive: false },
  );
  window.addEventListener("resize", drawToolpath);
}

function startPanelTimers() {
  if (document.hidden) return;
  if (!window.moonrakerRefreshTimer) {
    window.moonrakerRefreshTimer = setInterval(refresh, PANEL_FALLBACK_POLL_MS);
  }
  if (!window.moonrakerStalenessTimer) {
    window.moonrakerStalenessTimer = setInterval(
      updateStaleness,
      PANEL_STALENESS_CHECK_MS,
    );
  }
}

function stopPanelTimers() {
  if (window.moonrakerRefreshTimer) {
    clearInterval(window.moonrakerRefreshTimer);
    window.moonrakerRefreshTimer = null;
  }
  if (window.moonrakerStalenessTimer) {
    clearInterval(window.moonrakerStalenessTimer);
    window.moonrakerStalenessTimer = null;
  }
}

function handlePanelVisibilityChange() {
  if (document.hidden) stopPanelTimers();
  else {
    startPanelTimers();
    refresh();
  }
}

function cleanupPanel() {
  panelStopped = true;
  stopPanelTimers();
  stopLiveSubscription();
  resetLiveTracking();
  void resetPanelPush();
  if (toolpathAbort) {
    toolpathAbort.abort();
    toolpathAbort = null;
  }
  for (const frame of [cameraAnimFrame, orbitInertiaFrame, headAnimFrame]) {
    if (frame !== null) cancelAnimationFrame(frame);
  }
  cameraAnimFrame = null;
  orbitInertiaFrame = null;
  headAnimFrame = null;
  cameraAnim = null;
  clearTimelapse();
  clearAuthedImage(byId("thumb"));
  clearAuthedImage(byId("jobDoneThumb"));
  clearAuthedImage(byId("jobDonePhoto"));
  clearAuthedImage(byId("analysisThumb"));
  const toastTimer = byId("toast")?._timer;
  if (toastTimer) clearTimeout(toastTimer);
  latestData = null;
  toolpathSegments = [];
  toolpathBounds = null;
  toolpathLayerStats = [];
  toolpathSimSeconds = 0;
  lastFiles = [];
  availableWebcams = [];
  sentCommandHistory = [];
  retransmitHistory = [];
  thermalSamples = {};
  energySession = { file: "", kwh: 0, lastAt: 0 };
  flowSaturatedSince = null;
  lastFlowFinding = null;
}

function handlePanelPageHide(event) {
  if (!event.persisted) cleanupPanel();
}

function initializePanel() {
  panelStopped = false;
  bindInteractions();
  bindToolpathCanvas();
  bindAlertSettings();
  enhanceAccessibility();
  document.addEventListener("visibilitychange", handlePanelVisibilityChange);
  window.addEventListener("pagehide", handlePanelPageHide);
  byId("pageDetails").setAttribute("aria-hidden", "true");
  renderSentCommandHistory();
  setScreen("dashboard");
  refresh();
  startPanelTimers();
}

function startPanel() {
  if (window.moonrakerPanelStarted) return;
  window.moonrakerPanelStarted = true;
  initializePanel();
}

window.addEventListener("moonraker-hass-ready", startPanel);
if (window.hass?.callApi) startPanel();
