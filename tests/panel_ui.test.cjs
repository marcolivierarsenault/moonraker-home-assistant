const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.style = {};
    this.style.setProperty = (name, value) => {
      this.style[name] = value;
    };
    this.style.removeProperty = (name) => {
      delete this.style[name];
    };
    this.dataset = {};
    this.attributes = {};
    this.className = "";
    this.value = "";
    this.src = "";
    this.disabled = false;
    this.hidden = false;
    this.scrollTop = 0;
    this.scrollHeight = 0;
    this.listeners = {};
    this._text = "";
    this.classList = {
      add: (name) => this._setClass(name, true),
      remove: (name) => this._setClass(name, false),
      contains: (name) => this.className.split(/\s+/).includes(name),
      toggle: (name, force) => this._toggleClass(name, force),
    };
  }

  get textContent() {
    return this._text;
  }

  set textContent(value) {
    this._text = String(value);
    this.children = [];
  }

  _setClass(name, enabled) {
    const classes = new Set(this.className.split(/\s+/).filter(Boolean));
    if (enabled) classes.add(name);
    else classes.delete(name);
    this.className = [...classes].join(" ");
  }

  _toggleClass(name, force) {
    const enabled =
      force === undefined ? !this.classList.contains(name) : Boolean(force);
    this._setClass(name, enabled);
    return enabled;
  }

  append(...nodes) {
    nodes.forEach((node) => this.appendChild(node));
  }

  appendChild(node) {
    node.parentElement = this;
    this.children.push(node);
    return node;
  }

  closest(selector) {
    let current = this;
    while (current) {
      if (matches(current, selector)) return current;
      current = current.parentElement;
    }
    return null;
  }

  matches(selector) {
    return matches(this, selector);
  }

  focus() {}

  getBoundingClientRect() {
    return {
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      width: 0,
      height: 0,
    };
  }

  setPointerCapture() {}

  replaceChildren(...nodes) {
    this.children = [];
    this.append(...nodes);
  }

  get options() {
    return this.children.filter((child) => child.tagName === "OPTION");
  }

  addEventListener(type, callback) {
    this.listeners[type] = callback;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === "src") this.src = String(value);
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  hasAttribute(name) {
    return Object.hasOwn(this.attributes, name);
  }

  removeAttribute(name) {
    delete this.attributes[name];
    if (name === "src") this.src = "";
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  querySelectorAll(selector) {
    const found = [];
    const visit = (node) => {
      node.children.forEach((child) => {
        if (matches(child, selector)) found.push(child);
        visit(child);
      });
    };
    visit(this);
    return found;
  }
}

function matches(element, selector) {
  if (selector.includes(","))
    return selector.split(",").some((part) => matches(element, part.trim()));
  if (selector.startsWith("."))
    return element.className.split(/\s+/).includes(selector.slice(1));
  if (selector === "img") return element.tagName === "IMG";
  const attribute = selector.match(/^\[data-([\w-]+)\]$/);
  if (attribute) {
    const key = attribute[1].replace(/-([a-z])/g, (_match, letter) =>
      letter.toUpperCase(),
    );
    return Object.hasOwn(element.dataset, key);
  }
  const plainAttribute = selector.match(/^\[([\w-]+)\]$/);
  if (plainAttribute) return element.hasAttribute(plainAttribute[1]);
  if (/^[a-z][a-z0-9]*$/.test(selector))
    return element.tagName === selector.toUpperCase();
  return false;
}

class FakeDocument {
  constructor(ids = []) {
    this.elements = new Map(ids.map((id) => [id, new FakeElement()]));
    this.listeners = {};
  }

  getElementById(id) {
    if (!this.elements.has(id)) this.elements.set(id, new FakeElement());
    return this.elements.get(id);
  }

  createElement(tagName) {
    return new FakeElement(tagName);
  }

  addEventListener(type, callback) {
    this.listeners[type] = callback;
  }

  querySelectorAll() {
    return [];
  }
}

function createPanelClient() {
  const ids = [
    "cameraLayout",
    "cameraGrid",
    "webcamCard",
    "cameraEmpty",
    "cameraName",
    "cameraGridStatus",
    "dashboardCameraGrid",
    "dashboardCameraLayout",
    "dashboardCameraOptions",
    "dashboardCameraStatus",
    "dashboardCameraSummary",
    "cameraConfig",
    "cameraConfigScrim",
    "networkCameras",
    "commandHistory",
    "commandHistoryCount",
    "detailsTitle",
    "detailsSummary",
    "detailsRows",
    "pageDetails",
    "detailsScrim",
    "detailsToggle",
    "console",
    "toast",
    "sysPrinterState",
    "sysKlippy",
    "sysKlipperVersion",
    "sysMoonrakerVersion",
    "sysCpu",
    "sysHostTemp",
    "systemPrinterState",
    "systemKlippy",
    "systemKlipperVersion",
    "systemMoonrakerVersion",
    "systemCpu",
    "systemHostTemp",
    "systemLive",
    "dashboardSystemLive",
  ];
  const document = new FakeDocument(ids);
  document.getElementById("cameraLayout").value = "1x1";
  const storage = new Map();
  const window = {
    addEventListener() {},
    removeEventListener() {},
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: (key) => storage.delete(key),
      _storage: storage,
    },
  };
  const context = vm.createContext({
    document,
    window,
    console,
    requestAnimationFrame: (callback) => callback(),
    setTimeout: () => 0,
    clearTimeout: () => {},
  });
  const parseSource = fs.readFileSync(
    path.join(__dirname, "../custom_components/moonraker/toolpath_parse.js"),
    "utf8",
  );
  vm.runInContext(parseSource, context, { filename: "toolpath_parse.js" });
  const source = fs.readFileSync(
    path.join(__dirname, "../custom_components/moonraker/panel_client.js"),
    "utf8",
  );
  vm.runInContext(source, context, { filename: "panel_client.js" });
  return { context, document, window };
}

function deepText(element) {
  return [element.textContent, ...element.children.map(deepText)].join(" ");
}

test("camera page supports 1x1, 1x2, and 2x2 layouts and pauses hidden streams", () => {
  const { context, document } = createPanelClient();
  context.webcams = [
    {
      name: "Front",
      stream_url: "http://camera/front",
      snapshot_url: "http://camera/front.jpg",
    },
    { name: "Side", stream_url: "http://camera/side", snapshot_url: null },
  ];

  for (const [layout, expectedTiles] of [
    ["1x1", 1],
    ["1x2", 2],
    ["2x2", 4],
  ]) {
    document.getElementById("cameraLayout").value = layout;
    vm.runInContext(
      `activeScreen = "camera"; cameraLayout = ${JSON.stringify(
        layout,
      )}; cameraGridSignature = ""; renderCamera(webcams);`,
      context,
    );
    const grid = document.getElementById("cameraGrid");
    const tiles = grid.querySelectorAll(".camera-tile");
    assert.equal(grid.dataset.layout, layout);
    assert.equal(tiles.length, expectedTiles);
    assert.equal(tiles[0].querySelector("img").src, "http://camera/front");
    assert.equal(tiles[0].querySelector("[data-camera-slot]").value, "Front");
  }

  vm.runInContext('activeScreen = "files"; renderCamera(webcams);', context);
  const tiles = document
    .getElementById("cameraGrid")
    .querySelectorAll(".camera-tile");
  assert.ok(tiles.every((tile) => tile.querySelector("img").src === ""));
  assert.ok(
    document
      .getElementById("dashboardCameraGrid")
      .querySelectorAll("img")
      .every((image) => image.src === ""),
  );
});

test("camera selectors can assign a source to a tile", () => {
  const { context, document } = createPanelClient();
  context.webcams = [
    { name: "Front", stream_url: "http://camera/front" },
    { name: "Side", stream_url: "http://camera/side" },
  ];
  document.getElementById("cameraLayout").value = "1x2";
  vm.runInContext(
    'activeScreen = "camera"; cameraLayout = "1x2"; cameraGridSignature = ""; renderCamera(webcams);',
    context,
  );
  const tiles = document
    .getElementById("cameraGrid")
    .querySelectorAll(".camera-tile");
  const secondSelector = tiles[1].querySelector("[data-camera-slot]");
  secondSelector.value = "Front";
  vm.runInContext(
    'cameraAssignments[1] = "Front"; renderCamera(webcams);',
    context,
  );
  assert.equal(tiles[1].querySelector("img").src, "http://camera/front");
});

test("dashboard renders one, two, and four selected camera streams", () => {
  const { context, document } = createPanelClient();
  context.webcams = [
    { name: "Front", stream_url: "http://camera/front" },
    { name: "Side", stream_url: "http://camera/side" },
    { name: "Top", stream_url: "http://camera/top" },
    { name: "Chamber", stream_url: "http://camera/chamber" },
  ];

  for (const [layout, expectedTiles] of [
    ["1", 1],
    ["2", 2],
    ["4", 4],
  ]) {
    vm.runInContext(
      `activeScreen = "dashboard"; dashboardCameraLayout = ${JSON.stringify(
        layout,
      )}; dashboardCameraSignature = ""; renderCamera(webcams);`,
      context,
    );
    const grid = document.getElementById("dashboardCameraGrid");
    const tiles = grid.querySelectorAll(".dashboard-camera-tile");
    assert.equal(grid.dataset.layout, layout);
    assert.equal(tiles.length, expectedTiles);
    assert.equal(tiles[0].querySelector("img").src, "http://camera/front");
  }

  const fourTiles = document
    .getElementById("dashboardCameraGrid")
    .querySelectorAll(".dashboard-camera-tile");
  assert.equal(fourTiles[1].querySelector("img").src, "http://camera/side");
  assert.equal(fourTiles[3].querySelector("img").src, "http://camera/chamber");

  vm.runInContext('activeScreen = "files"; renderCamera(webcams);', context);
  assert.ok(fourTiles.every((tile) => tile.querySelector("img").src === ""));
});

test("dashboard camera popup assigns sources, handles missing cameras, and persists choices", () => {
  const { context, document, window } = createPanelClient();
  context.webcams = [
    { name: "Front", stream_url: "http://camera/front" },
    { name: "Side", stream_url: "http://camera/side" },
  ];
  vm.runInContext(
    'printer = "printer-a"; activeScreen = "dashboard"; renderCamera(webcams); bindInteractions();',
    context,
  );

  const click = document.listeners.click;
  click({
    target: {
      closest: (selector) => (selector === "[data-camera-config]" ? {} : null),
    },
  });
  assert.equal(document.getElementById("cameraConfig").hidden, false);
  assert.equal(document.getElementById("cameraConfigScrim").hidden, false);

  const change = document.listeners.change;
  change({
    target: {
      id: "dashboardCameraLayout",
      value: "4",
      matches: () => false,
    },
  });
  assert.equal(
    document
      .getElementById("dashboardCameraGrid")
      .querySelectorAll(".dashboard-camera-tile").length,
    4,
  );
  assert.equal(
    document.getElementById("dashboardCameraOptions").children.length,
    4,
  );

  change({
    target: {
      id: "",
      value: "Side",
      dataset: { dashboardCameraSlot: "3" },
      matches: (selector) => selector === "[data-dashboard-camera-slot]",
    },
  });
  const tiles = document
    .getElementById("dashboardCameraGrid")
    .querySelectorAll(".dashboard-camera-tile");
  assert.equal(tiles[3].querySelector("img").src, "http://camera/side");
  assert.equal(tiles[2].querySelector("img").src, "");
  assert.match(
    tiles[2].querySelector(".camera-tile-empty").textContent,
    /NO CAMERA ASSIGNED/,
  );

  const saved = JSON.parse(
    window.localStorage.getItem("nexus-dashboard-cameras:printer-a"),
  );
  assert.equal(saved.layout, "4");
  assert.equal(saved.assignments[3], "Side");

  click({
    target: {
      closest: (selector) =>
        selector === "[data-camera-config-close]" ? {} : null,
    },
  });
  assert.equal(document.getElementById("cameraConfig").hidden, true);
  assert.equal(document.getElementById("cameraConfigScrim").hidden, true);

  context.openCameraConfig();
  document.listeners.keydown({ key: "Escape" });
  assert.equal(document.getElementById("cameraConfig").hidden, true);
});

test("toolpath projection renders increasing Z upward on screen", () => {
  const { context } = createPanelClient();
  const read = (expression) =>
    JSON.parse(vm.runInContext(`JSON.stringify(${expression})`, context));

  for (const camera of [
    { yaw: 0, pitch: 1.5 },
    { yaw: -0.72, pitch: 0.7 },
  ]) {
    const low = read(
      `projectPoint([0,0,0], ${JSON.stringify(camera)}, 1, 0, 0, 800, 600)`,
    );
    const high = read(
      `projectPoint([0,0,50], ${JSON.stringify(camera)}, 1, 0, 0, 800, 600)`,
    );
    assert.ok(
      high.y < low.y,
      `z=50 must project above z=0 at pitch ${camera.pitch}`,
    );
  }

  const topBack = read(
    `projectPoint([0,50,0], { yaw: 0, pitch: 0.035 }, 1, 0, 0, 800, 600)`,
  );
  const topFront = read(
    `projectPoint([0,0,0], { yaw: 0, pitch: 0.035 }, 1, 0, 0, 800, 600)`,
  );
  assert.ok(
    topBack.y < topFront.y,
    "top view should render +Y toward the top of the screen",
  );
});

test("toolpath view presets cover seven angles and settle on target", () => {
  const { context } = createPanelClient();
  const views = JSON.parse(
    vm.runInContext("JSON.stringify(CAMERA_VIEWS)", context),
  );
  assert.deepEqual(Object.keys(views).sort(), [
    "back",
    "front",
    "iso",
    "iso2",
    "left",
    "right",
    "top",
  ]);

  vm.runInContext(
    'toolpathCamera.panX = 30; toolpathCamera.zoom = 2; setToolpathView("back");',
    context,
  );
  const settled = JSON.parse(
    vm.runInContext(
      "JSON.stringify({ yaw: toolpathCamera.yaw, pitch: toolpathCamera.pitch, zoom: toolpathCamera.zoom, panX: toolpathCamera.panX, anim: cameraAnim })",
      context,
    ),
  );
  assert.equal(settled.anim, null);
  assert.equal(settled.yaw, Math.PI);
  assert.equal(settled.pitch, 1.5);
  assert.equal(settled.zoom, 1);
  assert.equal(settled.panX, 0);
});

test("live entity pushes update toolhead target and progress", async () => {
  const { context, window } = createPanelClient();
  context.toast = () => {};
  const subscriptions = [];
  window.hass = {
    callApi: async () => ({}),
    fetchWithAuth: async () => null,
    entities: {
      "sensor.p5_toolhead_position_x": {
        entity_id: "sensor.p5_toolhead_position_x",
        unique_id: "entry-1_toolhead_position_x",
      },
      "sensor.p5_toolhead_position_y": {
        entity_id: "sensor.p5_toolhead_position_y",
        unique_id: "entry-1_toolhead_position_y",
      },
      "sensor.p5_toolhead_position_z": {
        entity_id: "sensor.p5_toolhead_position_z",
        unique_id: "entry-1_toolhead_position_z",
      },
      "sensor.p5_progress": {
        entity_id: "sensor.p5_progress",
        unique_id: "entry-1_progress",
      },
      "sensor.other_toolhead_position_x": {
        entity_id: "sensor.other_toolhead_position_x",
        unique_id: "entry-2_toolhead_position_x",
      },
    },
    connection: {
      subscribeEvents: async (callback, eventType) => {
        subscriptions.push({ callback, eventType });
        return () => {};
      },
      sendMessagePromise: async () => [],
    },
  };
  vm.runInContext(
    'printer = "entry-1"; latestData = { status: { toolhead: { position: [10, 20, 5, 0] } } };',
    context,
  );
  await context.resolveLiveEntities();
  context.ensureLiveSubscription();
  assert.equal(subscriptions.length, 1);
  assert.equal(subscriptions[0].eventType, "state_changed");
  const read = (expression) =>
    JSON.parse(vm.runInContext(`JSON.stringify(${expression})`, context));
  assert.deepEqual(read("liveEntityIds"), {
    "sensor.p5_toolhead_position_x": 0,
    "sensor.p5_toolhead_position_y": 1,
    "sensor.p5_toolhead_position_z": 2,
    "sensor.p5_progress": "progress",
  });

  const callback = subscriptions[0].callback;
  callback({
    data: {
      entity_id: "sensor.other_toolhead_position_x",
      new_state: { state: "999" },
    },
  });
  assert.equal(read("liveHeadTarget"), null);

  callback({
    data: {
      entity_id: "sensor.p5_toolhead_position_x",
      new_state: { state: "42.5" },
    },
  });
  assert.deepEqual(read("liveHeadTarget"), [42.5, 20, 5]);
  callback({
    data: {
      entity_id: "sensor.p5_toolhead_position_x",
      new_state: { state: "unavailable" },
    },
  });
  assert.deepEqual(read("liveHeadTarget"), [42.5, 20, 5]);

  callback({
    data: { entity_id: "sensor.p5_progress", new_state: { state: "55.5" } },
  });
  assert.equal(vm.runInContext("getLiveProgress({})", context), 0.555);

  vm.runInContext("resetLiveTracking()", context);
  assert.equal(read("liveHeadTarget"), null);
  assert.equal(read("liveProgress"), null);
});

test("tts alerts respect quiet hours, event toggles, and announce transitions", () => {
  const { context, window } = createPanelClient();
  const spoken = [];
  window.SpeechSynthesisUtterance = class {
    constructor(text) {
      this.text = text;
    }
  };
  window.speechSynthesis = {
    speak: (utterance) => spoken.push(utterance.text),
  };

  vm.runInContext(
    `printer = "entry-1";
    alertPrefs.engine = "browser";
    alertPrefs.quietStart = "22:00"; alertPrefs.quietEnd = "07:00";`,
    context,
  );
  const quiet = (minutes) =>
    vm.runInContext(`isQuietTime(${minutes})`, context);
  assert.equal(quiet(23 * 60), true);
  assert.equal(quiet(6 * 60), true);
  assert.equal(quiet(12 * 60), false);
  assert.equal(quiet(22 * 60), true);
  assert.equal(quiet(7 * 60), false);
  vm.runInContext(
    'alertPrefs.quietStart = "08:00"; alertPrefs.quietEnd = "17:00";',
    context,
  );
  assert.equal(quiet(9 * 60), true);
  assert.equal(quiet(20 * 60), false);

  const data = (state) => ({
    printer_info: { klippy_state: "ready" },
    status: {
      print_stats: { state, filename: "part.gcode" },
      display_status: { progress: 0.1 },
      virtual_sdcard: {},
    },
  });
  vm.runInContext(
    'alertPrefs.quietStart = ""; alertPrefs.quietEnd = ""; alertPrefsKey = "seed"; checkAlerts(' +
      JSON.stringify(data("standby")) +
      ")",
    context,
  );
  assert.equal(spoken.length, 0);

  vm.runInContext(
    "checkAlerts(" + JSON.stringify(data("printing")) + ")",
    context,
  );
  assert.deepEqual(spoken, ["Print started: part.gcode"]);

  vm.runInContext(
    "checkAlerts(" + JSON.stringify(data("paused")) + ")",
    context,
  );
  assert.match(spoken[1], /paused/);

  vm.runInContext(
    "checkAlerts(" + JSON.stringify(data("complete")) + ")",
    context,
  );
  assert.match(spoken[2], /complete/);

  const runoutData = {
    printer_info: {},
    status: {
      print_stats: { state: "printing", filename: "x" },
      "filament_switch_sensor runout": { filament_detected: false },
    },
  };
  vm.runInContext("checkAlerts(" + JSON.stringify(runoutData) + ")", context);
  assert.ok(spoken.some((text) => /runout/i.test(text)));

  const before = spoken.length;
  vm.runInContext(
    "alertPrefs.events.progress = false; checkAlerts(" +
      JSON.stringify(data("printing")) +
      ")",
    context,
  );
  assert.ok(!spoken.slice(before).some((text) => /percent/i.test(text)));

  vm.runInContext(
    'alertPrefs.quietStart = "00:00"; alertPrefs.quietEnd = "23:59";',
    context,
  );
  vm.runInContext(
    "checkAlerts(" +
      JSON.stringify({
        printer_info: { klippy_state: "shutdown" },
        status: { print_stats: { state: "error", filename: "x" } },
      }) +
      ")",
    context,
  );
  assert.ok(
    spoken.some((text) => /fault|error/i.test(text)),
    "errors bypass quiet hours",
  );
});

test("tts announcements fan out to every selected media player", () => {
  const { context, window } = createPanelClient();
  const calls = [];
  window.hass = {
    callApi: async (method, path, body) => {
      calls.push({ method, path, body });
      return {};
    },
    fetchWithAuth: async () => null,
  };
  vm.runInContext(
    `alertPrefs.engine = "tts.google_translate_en_com";
    alertPrefs.players = ["media_player.kitchen", "media_player.living_room"];
    alertPrefs.quietStart = ""; alertPrefs.quietEnd = "";`,
    context,
  );
  context.speak("Print complete");
  assert.equal(calls.length, 2);
  assert.equal(calls[0].path, "services/tts/speak");
  assert.equal(calls[0].body.media_player_entity_id, "media_player.kitchen");
  assert.equal(
    calls[1].body.media_player_entity_id,
    "media_player.living_room",
  );
  assert.equal(calls[0].body.message, "Print complete");

  calls.length = 0;
  vm.runInContext("alertPrefs.players = [];", context);
  context.speak("Print complete");
  assert.equal(calls.length, 0);
});

test("command history is bounded, per-printer, session-only, and only records successful sends", async () => {
  const { context, document, window } = createPanelClient();
  context.toast = () => {};
  context.refresh = () => {};
  vm.runInContext('printer = "printer-a";', context);
  for (let index = 0; index < 105; index++)
    context.recordSentCommand(`G1 X${index}`);
  assert.equal(
    document.getElementById("commandHistory").querySelectorAll(".command-entry")
      .length,
    100,
  );
  assert.equal(
    document.getElementById("commandHistoryCount").textContent,
    "100 COMMANDS",
  );

  window.hass = {
    callApi: async () => ({ ok: true }),
    fetchWithAuth: async () => null,
  };
  vm.runInContext(
    "lastDataAt = Date.now(); latestData = { available: true };",
    context,
  );
  await context.act("run_gcode", null, null, { script: "M105" });
  assert.equal(
    document.getElementById("commandHistoryCount").textContent,
    "100 COMMANDS",
  );
  assert.match(deepText(document.getElementById("commandHistory")), /M105/);

  window.hass.callApi = async () => ({ ok: false, error: "rejected" });
  await context.act("run_gcode", null, null, { script: "G1 X999" });
  assert.doesNotMatch(
    deepText(document.getElementById("commandHistory")),
    /G1 X999/,
  );

  vm.runInContext(
    'printer = "printer-b"; renderSentCommandHistory();',
    context,
  );
  assert.equal(
    document.getElementById("commandHistoryCount").textContent,
    "0 COMMANDS",
  );
});

test("stale telemetry holds mutating commands but never blocks emergency stop", async () => {
  const { context, document, window } = createPanelClient();
  const calls = [];
  const toasts = [];
  window.hass = {
    callApi: async (method, path) => {
      calls.push(path);
      return { ok: true };
    },
    fetchWithAuth: async () => null,
  };
  context.toast = (message) => toasts.push(message);
  context.refresh = () => {};

  vm.runInContext(
    "latestData = { available: true, settings: { idle_poll_seconds: 5 }, status: {} }; lastDataAt = Date.now() - 30000;",
    context,
  );
  assert.equal(context.updateStaleness(), true);
  assert.equal(document.getElementById("staleBanner").hidden, false);

  await context.act("jog", null, null, { axis: "X", dist: 1 });
  assert.equal(calls.length, 0);
  assert.ok(toasts.some((text) => /STALE/i.test(text)));

  await context.act("emergency_stop");
  assert.deepEqual(calls, ["moonraker/panel_action"]);
  assert.ok(toasts.some((text) => /EMERGENCY STOP DELIVERED/i.test(text)));

  vm.runInContext(
    "lastDataAt = Date.now(); latestData = { available: true };",
    context,
  );
  assert.equal(context.updateStaleness(), false);
  assert.equal(document.getElementById("staleBanner").hidden, true);
  await context.act("jog", null, null, { axis: "X", dist: 1 });
  assert.equal(calls.length, 2);

  vm.runInContext("latestData = { available: false };", context);
  assert.equal(context.updateStaleness(), true);
});

test("system status binds printer, firmware, server, CPU, and host temperature values", () => {
  const { context, document } = createPanelClient();
  const data = {
    available: true,
    printer_info: {
      state: "ready",
      klippy_state: "ready",
      software_version: "klipper-v0.12",
    },
    machine_update: { version_info: {} },
    server_info: { moonraker_version: "moonraker-v0.9" },
    system_info: { cpu_info: { model: "Test SBC" } },
  };
  context.renderSystem(
    data,
    { "temperature_host host_temp": { temperature: 42.5 } },
    "PRINTING",
  );

  assert.equal(
    document.getElementById("systemPrinterState").textContent,
    "ready",
  );
  assert.equal(document.getElementById("systemKlippy").textContent, "ready");
  assert.equal(
    document.getElementById("systemKlipperVersion").textContent,
    "klipper-v0.12",
  );
  assert.equal(
    document.getElementById("systemMoonrakerVersion").textContent,
    "moonraker-v0.9",
  );
  assert.equal(document.getElementById("systemCpu").textContent, "Test SBC");
  assert.equal(document.getElementById("systemHostTemp").textContent, "42.5°C");
  assert.equal(document.getElementById("sysPrinterState").textContent, "ready");

  context.renderSystem(data, {}, "PRINTING");
  assert.equal(
    document.getElementById("systemHostTemp").textContent,
    "NOT REPORTED",
  );
});

test("page details cover each page and never reveal a raw API key", () => {
  const { context, document } = createPanelClient();
  context.testData = {
    available: true,
    printer: "Test Printer",
    entry_id: "test",
    api_key_configured: true,
    api_key: "must-not-appear",
    settings: { host: "printer.local", port: 7125, tls: false },
    printer_info: { klippy_state: "ready", software_version: "v0.12" },
    system_info: { provider: "test", cpu_info: { model: "Test CPU" } },
    platforms: ["sensor", "camera"],
    tracked_objects: [{ name: "extruder", fields: ["temperature", "target"] }],
    available_objects: ["extruder", "toolhead"],
    files: [{ path: "part.gcode", size: 1024, modified: 1 }],
    selected_file: "part.gcode",
    history: { job_totals: { total_jobs: 3 } },
    webcams: [
      { name: "Front", stream_url: "http://camera/front", snapshot_url: null },
    ],
    macros: ["PRINT_START"],
    gcode_responses: ["ok"],
    power_devices: [
      { device: "psu", status: "on", locked_while_printing: false },
    ],
    machine_update: {},
    queue: {},
    spoolman: {},
    meta: { estimated_time: 60, filament_total: 1000, layer_count: 10 },
    status: {
      print_stats: {
        state: "printing",
        filename: "part.gcode",
        print_duration: 10,
        filament_used: 50,
        info: { current_layer: 2, total_layer: 10 },
      },
      virtual_sdcard: {
        file_path: "part.gcode",
        file_position: 10,
        file_size: 100,
      },
      toolhead: {
        position: [1, 2, 3, 4],
        homed_axes: "xyz",
        max_velocity: 300,
        max_accel: 5000,
      },
      gcode_move: {
        speed: 5,
        speed_factor: 1,
        extrude_factor: 1,
        absolute_coordinates: true,
      },
      extruder: { temperature: 200, target: 210 },
      heater_bed: { temperature: 60, target: 60 },
      fan: { speed: 0.5 },
      bed_mesh: {
        profile_name: "default",
        mesh_matrix: [
          [0.1, -0.1],
          [0, 0.2],
        ],
      },
      probe: { last_query: 0 },
      input_shaper: { shaper_type_x: "mzv" },
      "temperature_sensor chamber": { temperature: 35, target: 0, power: 0 },
      "filament_switch_sensor runout": { filament_detected: true },
      "gcode_macro PRINT_START": { state: "ready" },
    },
  };

  const screens = [
    "dashboard",
    "print",
    "movement",
    "thermal",
    "extruder",
    "bedmesh",
    "tuning",
    "macros",
    "files",
    "history",
    "camera",
    "console",
    "hardware",
    "system",
    "network",
    "settings",
    "components",
  ];
  for (const screen of screens) {
    vm.runInContext(
      `activeScreen = ${JSON.stringify(screen)}; renderPageDetails(testData);`,
      context,
    );
    assert.ok(
      document.getElementById("detailsRows").children.length > 0,
      `${screen} should render details`,
    );
  }
  vm.runInContext(
    'activeScreen = "network"; renderPageDetails(testData);',
    context,
  );
  const detailsText = deepText(document.getElementById("detailsRows"));
  assert.match(detailsText, /CONFIGURED \/ VALUE HIDDEN/);
  assert.doesNotMatch(detailsText, /must-not-appear/);
});

test("detail drawer opens and closes through its controls", () => {
  const { context, document } = createPanelClient();
  context.testData = {
    available: true,
    status: {},
    printer_info: {},
    settings: {},
    meta: {},
  };
  vm.runInContext("latestData = testData; bindInteractions();", context);
  const click = document.listeners.click;
  click({
    target: {
      closest: (selector) => (selector === "[data-details-toggle]" ? {} : null),
    },
  });
  assert.equal(document.getElementById("pageDetails").hidden, false);
  assert.equal(document.getElementById("detailsScrim").hidden, false);
  click({
    target: {
      closest: (selector) => (selector === "[data-details-close]" ? {} : null),
    },
  });
  assert.equal(document.getElementById("pageDetails").hidden, true);
  assert.equal(document.getElementById("detailsScrim").hidden, true);
});

test("panel markup exposes the camera layouts, dashboard camera popup, wide console, and page details control", () => {
  const html = fs.readFileSync(
    path.join(__dirname, "../custom_components/moonraker/panel.html"),
    "utf8",
  );
  assert.match(html, /<option value="1x1">/);
  assert.match(html, /<option value="1x2">/);
  assert.match(html, /<option value="2x2">/);
  assert.match(html, /id="dashboardCameraGrid"/);
  assert.match(html, /id="cameraConfig"[\s\S]*role="dialog"/);
  assert.match(
    html,
    /id="dashboardCameraLayout"[\s\S]*<option value="1">1 camera<\/option>[\s\S]*<option value="2">2 cameras stacked<\/option>[\s\S]*<option value="4">4 cameras<\/option>/,
  );
  assert.match(html, /id="dashboardCameraOptions"/);
  assert.match(html, /data-camera-config/);
  assert.match(html, /id="commandHistory"/);
  assert.match(html, /data-details-toggle/);
  assert.match(html, /id="screen-console"[\s\S]*?class="panel span-12"/);
  assert.match(html, /id="systemPrinterState"/);
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => id);
  assert.deepEqual(
    ids.filter((id, index) => ids.indexOf(id) !== index),
    [],
  );
  assert.match(
    html,
    /\.toolpath-box\s*\{[^}]*height:\s*clamp\(280px,\s*44vh,\s*560px\)/,
  );
  assert.match(
    html,
    /@media \(max-width: 720px\)[\s\S]*\.toolpath-box\s*\{\s*height:\s*clamp\(260px,\s*52vh,\s*420px\)/,
  );
});

test("custom panel sizes its iframe to the available viewport and responds to resize", () => {
  const listeners = new Map();
  const viewportListeners = new Map();
  const window = {
    innerHeight: 800,
    addEventListener: (name, callback) => listeners.set(name, callback),
    removeEventListener: (name) => listeners.delete(name),
    visualViewport: {
      height: 800,
      addEventListener: (name, callback) =>
        viewportListeners.set(name, callback),
      removeEventListener: (name) => viewportListeners.delete(name),
    },
  };
  class FakeHTMLElement extends FakeElement {
    attachShadow() {
      this.shadowRoot = new FakeElement("shadow-root");
      return this.shadowRoot;
    }

    getBoundingClientRect() {
      return { top: 72 };
    }
  }
  let registeredClass;
  const customElements = {
    define: (_name, definition) => {
      registeredClass = definition;
    },
  };
  const document = { createElement: (tagName) => new FakeElement(tagName) };
  const context = vm.createContext({
    HTMLElement: FakeHTMLElement,
    customElements,
    document,
    window,
    location: { href: "http://ha.local/" },
    requestAnimationFrame: (callback) => callback(),
  });
  const source = fs.readFileSync(
    path.join(__dirname, "../custom_components/moonraker/panel_module.js"),
    "utf8",
  );
  vm.runInContext(source, context, { filename: "panel_module.js" });
  const panel = new registeredClass();
  panel.connectedCallback();
  assert.equal(panel.style.height, "728px");

  window.innerHeight = 900;
  window.visualViewport.height = 900;
  listeners.get("resize")();
  assert.equal(panel.style.height, "828px");

  panel.disconnectedCallback();
  assert.equal(listeners.has("resize"), false);
  assert.equal(viewportListeners.has("resize"), false);
});

test("toolpath sampling keeps the full build height when G-code exceeds the segment cap", () => {
  const { context } = createPanelClient();
  const result = vm.runInContext(
    `(() => {
    const state = {
      xyzAbsolute: true,
      eAbsolute: true,
      unit: 1,
      position: { x: 0, y: 0, z: 0, e: 0 },
      extrusions: 0,
      sampleStride: 1,
    };
    const segments = [];
    const bounds = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity, minZ: Infinity, maxZ: -Infinity };
    parseGcodeLine("G90", state, 0, 1);
    parseGcodeLine("M83", state, 0, 1);
    let lastLayer172Index = 0;
    let hasLayer173 = false;
    for (let layer = 0; layer < 298; layer++) {
      const z = layer < 172
        ? ((layer + 1) * 24.2 / 172).toFixed(6)
        : (24.2 + (layer - 171) * 25.2 / 126).toFixed(6);
      parseGcodeLine("G1 Z" + z, state, layer / 298, 1);
      parseGcodeLine("G92 E0", state, layer / 298, 1);
      const moves = layer < 54 ? 162 : layer < 171 ? 161 : layer === 171 ? 488 : layer < 190 ? 151 : 150;
      for (let move = 0; move < moves; move++) {
        const x = state.extrusions % 2 === 0 ? 11 : 10;
        const segment = parseGcodeLine("G1 X" + x + " Y" + (layer + 1) + " E0.2", state, state.extrusions / 46991, 1);
        if (segment) {
          addToolpathSegment(segments, bounds, segment, state);
          if (layer === 171) lastLayer172Index = Math.max(lastLayer172Index, segment.extrusionIndex);
          if (layer === 172) hasLayer173 = true;
        }
      }
    }
    return {
      count: segments.length,
      extrusions: state.extrusions,
      maxZ: Math.max(...segments.map(segment => segment.b[2])),
      lastLayer172Index,
      hasLayer173,
      stride: state.sampleStride,
    };
  })()`,
    context,
  );

  assert.ok(result.count <= 28000);
  assert.equal(result.stride, 2);
  assert.equal(result.extrusions, 46991);
  assert.ok(result.lastLayer172Index > 28000);
  assert.equal(result.hasLayer173, true);
  assert.ok(Math.abs(result.maxZ - 49.4) < 0.001);
});

test("authenticated thumbnails stay hidden until the image decodes", async () => {
  const { context, document, window } = createPanelClient();
  const revoked = [];
  let objectUrlIndex = 0;
  context.URL = {
    createObjectURL: () => `blob:thumbnail-${++objectUrlIndex}`,
    revokeObjectURL: (url) => revoked.push(url),
  };
  window.hass = {
    callApi: async () => ({}),
    fetchWithAuth: async () => ({ ok: false }),
  };
  const image = document.getElementById("jobDoneThumb");
  image._objectUrl = "blob:old-thumbnail";
  image.src = "blob:old-thumbnail";
  image.hidden = false;

  assert.equal(await context.loadAuthedImage(image, "/thumbnail"), false);
  assert.equal(image.hidden, true);
  assert.equal(image.style.display, "none");
  assert.equal(image.src, "");
  assert.deepEqual(revoked, ["blob:old-thumbnail"]);

  window.hass.fetchWithAuth = async () => ({
    ok: true,
    blob: async () => ({ size: 10 }),
  });
  image.decode = async () => {};
  assert.equal(await context.loadAuthedImage(image, "/thumbnail"), true);
  assert.equal(image.hidden, false);
  assert.equal(image.style.display, "");
  assert.equal(image.src, "blob:thumbnail-1");

  image.decode = async () => {
    throw new Error("not an image");
  };
  assert.equal(await context.loadAuthedImage(image, "/invalid-image"), false);
  assert.equal(image.hidden, true);
  assert.equal(image.style.display, "none");
  assert.equal(image.src, "");
  assert.deepEqual(revoked, [
    "blob:old-thumbnail",
    "blob:thumbnail-1",
    "blob:thumbnail-2",
  ]);
});

test("completion card hides absent thumbnails with inline display state", () => {
  const { context, document } = createPanelClient();
  context.showJobDoneCard({
    status: { print_stats: { filename: "part.gcode" } },
    meta: {},
  });
  const image = document.getElementById("jobDoneThumb");
  assert.equal(image.hidden, true);
  assert.equal(image.style.display, "none");
  assert.equal(image.src, "");
});

test("panel polling uses the reduced cadence and unload releases subscriptions", async () => {
  const { context, document, window } = createPanelClient();
  const intervals = [];
  const cleared = [];
  let unsubscribed = 0;
  context.setInterval = (_callback, milliseconds) => {
    intervals.push(milliseconds);
    return intervals.length;
  };
  context.clearInterval = (id) => cleared.push(id);
  window.hass = {
    callApi: async () => ({}),
    fetchWithAuth: async () => ({}),
    connection: {
      subscribeEvents: async (_callback, eventType) => {
        assert.equal(eventType, "state_changed");
        return () => {
          unsubscribed += 1;
        };
      },
    },
  };

  context.startPanelTimers();
  context.ensureLiveSubscription();
  await Promise.resolve();
  await Promise.resolve();
  assert.deepEqual(intervals, [2667, 1333]);

  document.hidden = true;
  context.handlePanelVisibilityChange();
  assert.deepEqual(cleared, [1, 2]);
  context.cleanupPanel();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(unsubscribed, 1);
  assert.equal(window.moonrakerRefreshTimer, null);
  assert.equal(window.moonrakerStalenessTimer, null);
});

test("timelapse captures are serialized and bounded by retained image bytes", async () => {
  const { context, window } = createPanelClient();
  const revoked = [];
  let objectUrlIndex = 0;
  const pending = [];
  context.AbortController = AbortController;
  context.URL = {
    createObjectURL: () => `blob:frame-${++objectUrlIndex}`,
    revokeObjectURL: (url) => revoked.push(url),
  };
  window.hass = {
    callApi: async () => ({}),
    fetchWithAuth: () => new Promise((resolve) => pending.push(resolve)),
  };
  vm.runInContext(
    `printer = "p";
    availableWebcams = [{ name: "Front", snapshot_url: "/snapshot" }];
    dashboardCameraAssignments = ["Front"];
    liveLayer = 1;`,
    context,
  );

  const firstCapture = context.captureTimelapseFrame();
  await context.captureTimelapseFrame();
  assert.equal(pending.length, 1);
  pending.shift()({
    ok: true,
    headers: { get: () => null },
    blob: async () => ({ size: 40 * 1024 * 1024 }),
  });
  await firstCapture;

  vm.runInContext("liveLayer = 2", context);
  const secondCapture = context.captureTimelapseFrame();
  pending.shift()({
    ok: true,
    headers: { get: () => null },
    blob: async () => ({ size: 40 * 1024 * 1024 }),
  });
  await secondCapture;

  assert.equal(vm.runInContext("timelapseFrames.length", context), 1);
  assert.equal(vm.runInContext("timelapseBytes", context), 40 * 1024 * 1024);
  assert.deepEqual(revoked, ["blob:frame-1"]);

  context.clearTimelapse();
  assert.equal(vm.runInContext("timelapseBytes", context), 0);
  assert.deepEqual(revoked, ["blob:frame-1", "blob:frame-2"]);

  let responseCanceled = false;
  window.hass.fetchWithAuth = async () => ({
    ok: true,
    headers: { get: () => String(65 * 1024 * 1024) },
    body: {
      cancel: async () => {
        responseCanceled = true;
      },
    },
  });
  await context.captureTimelapseFrame();
  assert.equal(responseCanceled, true);
  assert.equal(vm.runInContext("timelapseFrames.length", context), 0);
});

test("active G-code filename falls back to virtual sdcard path tail", () => {
  const { context } = createPanelClient();
  const filename = (status) =>
    vm.runInContext(`activeGcodeFilename(${JSON.stringify(status)})`, context);
  assert.equal(
    filename({ print_stats: { filename: "job.gcode" } }),
    "job.gcode",
  );
  assert.equal(
    filename({
      virtual_sdcard: {
        file_path: "/home/pi/printer_data/gcodes/sub/job.gcode",
      },
    }),
    "sub/job.gcode",
  );
  assert.equal(
    filename({
      virtual_sdcard: { file_path: "/home/pi/printer_data/gcodes/job.gcode" },
    }),
    "job.gcode",
  );
  assert.equal(filename({}), "");
});

test("resetPanelPush clears the live flag while a subscription request is pending", async () => {
  const { context, window } = createPanelClient();
  let resolveRequest;
  window.hass = {
    callApi: async () => ({}),
    fetchWithAuth: async () => ({}),
    connection: {
      subscribeMessage: () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        }),
    },
  };
  vm.runInContext("panelPushLive = true; subscribePanelPush();", context);
  const reset = context.resetPanelPush();
  resolveRequest(() => {});
  await reset;
  assert.equal(vm.runInContext("panelPushLive", context), false);
});

function createFakeIdb() {
  const data = new Map();
  const pending = [];
  const schedule = (fn) => pending.push(fn);
  const makeRequest = (getResult) => {
    const request = {};
    schedule(() => {
      request.result = getResult();
      request.onsuccess?.();
    });
    return request;
  };
  const store = {
    transaction: null,
    get: (key) => makeRequest(() => data.get(key)),
    put: (value, key) => makeRequest(() => data.set(key, value)),
    delete: (key) => makeRequest(() => data.delete(key)),
    getAllKeys: () => makeRequest(() => [...data.keys()]),
  };
  const db = {
    transaction: () => {
      const tx = {
        objectStore: () => store,
        oncomplete: null,
        onerror: null,
        onabort: null,
      };
      store.transaction = tx;
      schedule(() => tx.oncomplete?.());
      return tx;
    },
  };
  return {
    _data: data,
    open: () => {
      const request = {};
      queueMicrotask(() => {
        request.result = db;
        request.onsuccess?.();
      });
      return request;
    },
    flush: () => {
      while (pending.length) pending.shift()();
    },
  };
}

test("toolpath cache persists parsed results in indexeddb", async () => {
  const { context } = createPanelClient();
  const idb = createFakeIdb();
  context.indexedDB = idb;
  const entry = {
    segments: [{ a: [0, 0, 0], b: [1, 1, 1], fraction: 1 }],
    boundsNormalized: { minX: 0, maxX: 1, minY: 0, maxY: 1, minZ: 0, maxZ: 1 },
    layerStats: [{ z: 0.2, seconds: 3 }],
    simSeconds: 42,
  };
  const putPromise = context.toolpathCachePut("entry|cube.gcode|100", entry);
  for (let i = 0; i < 10; i++) {
    idb.flush();
    await Promise.resolve();
  }
  await putPromise;
  assert.equal(idb._data.size, 1);

  for (let i = 0; i < 6; i++) {
    const value = context.toolpathCachePut(`key-${i}`, { segments: [] });
    for (let j = 0; j < 6; j++) {
      idb.flush();
      await Promise.resolve();
    }
    await value;
  }
  assert.ok(idb._data.size <= 5);

  // the oldest entries are evicted once the cache exceeds its cap
  assert.equal(idb._data.has("entry|cube.gcode|100"), false);
  const getPromise = context.toolpathCacheGet("key-5");
  for (let i = 0; i < 6; i++) {
    idb.flush();
    await Promise.resolve();
  }
  const hit = await getPromise;
  assert.deepEqual(hit.segments, []);

  const missPromise = context.toolpathCacheGet("missing");
  for (let i = 0; i < 6; i++) {
    idb.flush();
    await Promise.resolve();
  }
  assert.equal(await missPromise, null);
});

test("toolpath parses through a worker and falls back inline on failure", async () => {
  const { context } = createPanelClient();
  context.AbortController = AbortController;
  context.TextDecoder = TextDecoder;
  class FakeWorker {
    constructor(url) {
      this.url = url;
      this.messages = [];
      this.terminated = false;
      FakeWorker.last = this;
    }
    postMessage(message) {
      this.messages.push(message);
    }
    terminate() {
      this.terminated = true;
    }
    respond(data) {
      this.onmessage?.({ data });
    }
  }
  context.Worker = FakeWorker;
  const gcode = "G21\nG90\nM82\nG1 X10 Y10 E1 F1200\nG1 X20 E2\n";
  const response = {
    ok: true,
    body: {},
    text: async () => gcode,
  };
  const progress = [];
  const options = {
    rangeStart: 0,
    rangeEnd: Infinity,
    stride: 1,
    signal: new AbortController().signal,
    onProgress: (count) => progress.push(count),
  };

  const promise = context.parseToolpathStream(response, options);
  await Promise.resolve();
  const worker = FakeWorker.last;
  assert.equal(worker.messages[0].type, "start");
  worker.respond({ type: "ready" });
  await Promise.resolve();
  await Promise.resolve();
  worker.respond({ type: "progress", segments: 2 });
  worker.respond({
    type: "done",
    segments: [{ a: [0, 0, 0], b: [1, 1, 1], fraction: 0.5 }],
    bounds: { minX: 0, maxX: 1, minY: 0, maxY: 1, minZ: 0, maxZ: 0.2 },
    layerStats: [{ z: 0.2, seconds: 1 }],
    simSeconds: 4,
  });
  const result = await promise;
  assert.equal(result.segments.length, 1);
  assert.equal(result.simSeconds, 4);
  assert.deepEqual(progress, [2]);
  assert.equal(worker.terminated, true);

  // Worker failure before streaming falls back to the inline parser.
  class FailingWorker extends FakeWorker {
    postMessage(message) {
      super.postMessage(message);
      if (message.type === "start") this.onerror?.({ message: "boom" });
    }
  }
  context.Worker = FailingWorker;
  const fallback = await context.parseToolpathStream(
    { ok: true, body: {}, text: async () => gcode },
    {
      rangeStart: 0,
      rangeEnd: Infinity,
      stride: 1,
      signal: new AbortController().signal,
    },
  );
  assert.ok(fallback.segments.length > 0);
  assert.ok(fallback.simSeconds > 0);
});

test("loadToolpath serves cached results without refetching", async () => {
  const { context, window } = createPanelClient();
  context.AbortController = AbortController;
  const idb = createFakeIdb();
  context.indexedDB = idb;
  const key = "entry-1|cube.gcode|1000";
  const put = context.toolpathCachePut(key, {
    segments: [{ a: [0, 0, 0], b: [1, 1, 1], fraction: 1, extrusionIndex: 1 }],
    boundsNormalized: {
      minX: 0,
      maxX: 1,
      minY: 0,
      maxY: 1,
      minZ: 0,
      maxZ: 0.2,
    },
    layerStats: [{ z: 0.2, seconds: 1 }],
    simSeconds: 7,
  });
  for (let i = 0; i < 10; i++) {
    idb.flush();
    await Promise.resolve();
  }
  await put;

  let fetched = false;
  window.hass = {
    callApi: async () => ({}),
    fetchWithAuth: async () => {
      fetched = true;
      return { ok: false, status: 500, json: async () => ({}) };
    },
  };
  vm.runInContext('toolpathKey = "k-cache"', context);
  const loadPromise = context.loadToolpath(
    {
      entry_id: "entry-1",
      meta: {},
      status: { virtual_sdcard: { file_size: 1000 } },
    },
    "cube.gcode",
    "k-cache",
    new AbortController().signal,
  );
  for (let i = 0; i < 10; i++) {
    idb.flush();
    await Promise.resolve();
  }
  await loadPromise;
  assert.equal(fetched, false);
  assert.equal(vm.runInContext("toolpathSegments.length", context), 1);
  assert.equal(vm.runInContext("toolpathReady", context), true);
});

test("toolpath auto-loads files up to the 128MB cap and rejects larger", async () => {
  const { context, window } = createPanelClient();
  context.AbortController = AbortController;
  window.hass = {
    callApi: async () => ({}),
    fetchWithAuth: async () => ({
      ok: false,
      status: 502,
      json: async () => ({ error: "upstream" }),
    }),
  };
  vm.runInContext('printer = "p";', context);

  await vm.runInContext(
    `updateToolpath({ entry_id: "p", status: { print_stats: { filename: "big.gcode" }, virtual_sdcard: { file_size: 78710369, progress: 0 } } })`,
    context,
  );
  assert.equal(vm.runInContext("toolpathRequested", context), true);
  assert.equal(vm.runInContext("toolpathKey", context), "p:big.gcode");
  await new Promise((resolve) => setTimeout(resolve, 0));

  await vm.runInContext(
    `updateToolpath({ entry_id: "p", status: { print_stats: { filename: "huge.gcode" }, virtual_sdcard: { file_size: 140 * 1024 * 1024, progress: 0 } } })`,
    context,
  );
  assert.equal(vm.runInContext("toolpathRequested", context), false);
});

test("refresh dedupes in-flight polls, drops stale responses, and stops on cleanup", async () => {
  const { context, window } = createPanelClient();
  let calls = 0;
  const pending = [];
  window.hass = {
    callApi: () => {
      calls += 1;
      return new Promise((resolve) => pending.push(resolve));
    },
    fetchWithAuth: async () => ({}),
  };
  vm.runInContext('printer = "p1";', context);

  const first = context.refresh();
  context.refresh();
  assert.equal(calls, 1);

  // A printer switch mid-request drops the stale payload and re-polls.
  vm.runInContext('printer = "p2";', context);
  pending.shift()({});
  await first;
  assert.equal(calls, 2);
  pending.shift()({ status: {}, printer_info: {} });
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  context.cleanupPanel();
  assert.equal(vm.runInContext("panelStopped", context), true);
  await context.refresh();
  assert.equal(calls, 2);
});

test("parser accumulates simulated time per layer including dwells", () => {
  const { context } = createPanelClient();
  const state = {
    xyzAbsolute: true,
    eAbsolute: true,
    unit: 1,
    position: { x: 0, y: 0, z: 0, e: 0 },
    extrusions: 0,
    sampleStride: 1,
    feedrate: 0,
    simSeconds: 0,
    layerTimes: new Map(),
  };
  // 14.14 mm move at F1500 (25 mm/s) ≈ 0.57 s; a pure retract takes time too.
  context.parseGcodeLine("G1 X10 Y10 E0.5 F1500", state, 0, 1);
  const afterMove = state.simSeconds;
  assert.ok(afterMove > 0.4 && afterMove < 1);
  assert.ok(state.layerTimes.get(0) > 0);
  context.parseGcodeLine("G1 E-2 F1800", state, 0, 1); // retraction, no segment but still timed
  assert.ok(state.simSeconds > afterMove);
  context.parseGcodeLine("G4 P2000", state, 0, 1);
  assert.ok(
    Math.abs(
      state.simSeconds - (afterMove + 2 + (state.simSeconds - afterMove - 2)),
    ) >= 0,
  );
  assert.ok(state.simSeconds > afterMove + 1.9);
  context.parseGcodeLine("G1 Z0.2", state, 0, 1);
  context.parseGcodeLine("G1 X5 Y5 E0.2", state, 0, 1);
  assert.ok(state.layerTimes.get(0.2) > 0);
});

test("layer spark shows current layer time and remaining simulated ETA", () => {
  const { context, document } = createPanelClient();
  vm.runInContext(
    `toolpathLayerStats = [
      { z: 0.2, seconds: 60 }, { z: 0.4, seconds: 60 }, { z: 0.6, seconds: 60 }
    ];
    toolpathSimSeconds = 180;
    latestData = { status: { print_stats: { state: "standby" } } };`,
    context,
  );
  context.drawLayerSpark();
  assert.ok(document.getElementById("simEta").textContent.includes("3m"));

  vm.runInContext(
    `latestData = { status: { print_stats: { state: "printing" },
    toolhead: { position: [0, 0, 0.35, 0] } } };`,
    context,
  );
  context.drawLayerSpark();
  assert.ok(document.getElementById("layerEta").textContent.includes("1m"));
  assert.ok(document.getElementById("simEta").textContent.includes("2m"));
});

test("toolpath scrubber syncs the timelapse frame to the scrubbed layer", () => {
  const { context, document } = createPanelClient();
  vm.runInContext(
    `timelapseFrames = [
      { layer: 2, z: 0.4, shots: { Front: { url: "blob:a", size: 10 } }, size: 10 },
      { layer: 8, z: 1.6, shots: { Front: { url: "blob:b", size: 10 } }, size: 10 },
      { layer: 20, z: 4.0, shots: { Front: { url: "blob:c", size: 10 } }, size: 10 }
    ];
    scrubZ = 1.55;`,
    context,
  );
  context.syncTimelapseToScrub();
  const scrub = document.getElementById("tlScrub");
  assert.equal(Number(scrub.value), 1);
  assert.equal(document.getElementById("tlFrame").src, "blob:b");
});

test("timelapse captures every assigned camera and replays per camera or grid", async () => {
  const { context, document, window } = createPanelClient();
  let objectUrlIndex = 0;
  context.AbortController = AbortController;
  context.URL = {
    createObjectURL: () => `blob:shot-${++objectUrlIndex}`,
    revokeObjectURL: () => {},
  };
  const requests = [];
  window.hass = {
    callApi: async () => ({}),
    fetchWithAuth: async (url) => {
      requests.push(url);
      return {
        ok: true,
        headers: { get: () => null },
        blob: async () => ({ size: 1024 }),
      };
    },
  };
  vm.runInContext(
    `printer = "p";
    availableWebcams = [
      { name: "Front", snapshot_url: "/front" },
      { name: "Side", snapshot_url: "/side" },
      { name: "Unused", snapshot_url: "/unused" }
    ];
    dashboardCameraAssignments = ["Front", "Side"];
    liveLayer = 3;`,
    context,
  );
  await context.captureTimelapseFrame();
  assert.equal(requests.length, 2);
  assert.ok(requests.some((url) => url.includes("Front")));
  assert.ok(requests.some((url) => url.includes("Side")));
  assert.equal(vm.runInContext("timelapseFrames.length", context), 1);
  assert.equal(
    vm.runInContext("Object.keys(timelapseFrames[0].shots).length", context),
    2,
  );

  const cameraSelect = document.getElementById("tlCamera");
  assert.equal(cameraSelect.hidden, false);
  assert.deepEqual(
    cameraSelect.options.map((option) => option.value),
    ["Front", "Side", "*"],
  );

  vm.runInContext('timelapseViewCamera = "Side"', context);
  context.renderTimelapseFrame();
  assert.equal(document.getElementById("tlFrame").src, "blob:shot-2");

  vm.runInContext('timelapseViewCamera = "*"', context);
  context.renderTimelapseStatus();
  const grid = document.getElementById("tlGrid");
  assert.equal(grid.hidden, false);
  assert.equal(grid.children.length, 2);
  assert.equal(document.getElementById("tlFrame").hidden, true);

  context.clearTimelapse();
  assert.equal(vm.runInContext("timelapseFrames.length", context), 0);
  assert.equal(vm.runInContext('timelapseViewCamera === ""', context), true);
});

test("completion card shows estimate delta, live photo, and gated reprint", async () => {
  const { context, document, window } = createPanelClient();
  context.AbortController = AbortController;
  let urls = 0;
  context.URL = {
    createObjectURL: () => `blob:photo-${++urls}`,
    revokeObjectURL: () => {},
  };
  window.hass = {
    callApi: async () => ({}),
    fetchWithAuth: async () => ({
      ok: true,
      blob: async () => ({ size: 100 }),
    }),
  };
  document.getElementById("jobDonePhoto").decode = async () => {};
  document.getElementById("jobDoneThumb").decode = async () => {};
  vm.runInContext(
    `printer = "p";
    availableWebcams = [{ name: "Front", snapshot_url: "/snap" }];
    dashboardCameraAssignments = ["Front"];`,
    context,
  );
  context.bindInteractions();

  context.showJobDoneCard({
    entry_id: "p",
    status: {
      print_stats: {
        filename: "job.gcode",
        print_duration: 660,
        filament_used: 1200,
        info: { current_layer: 10, total_layer: 10 },
      },
    },
    meta: {
      estimated_time: 600,
      thumbnails_path: "sub/.thumbs/job.png",
      layer_count: 10,
    },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  const card = document.getElementById("jobDoneCard");
  assert.equal(card.hidden, false);
  assert.ok(
    document.getElementById("jobDoneDelta").textContent.includes("10%"),
  );
  assert.equal(document.getElementById("jobDonePhoto").hidden, false);
  assert.ok(
    document.getElementById("jobDonePhoto").src.startsWith("blob:photo-"),
  );
  const reprint = document.getElementById("jobDoneReprint");
  assert.equal(reprint.disabled, true);
  assert.equal(reprint.dataset.value, "job.gcode");
  const cleared = document.getElementById("bedCleared");
  cleared.id = "bedCleared";
  cleared.checked = true;
  document.listeners.change({ target: cleared });
  assert.equal(reprint.disabled, false);
});

test("start_queue is held during quiet hours until pressed again", async () => {
  const { context, document, window } = createPanelClient();
  let posts = 0;
  window.hass = {
    callApi: async (method) => {
      if (method === "POST") posts += 1;
      return { ok: true };
    },
    fetchWithAuth: async () => ({}),
  };
  vm.runInContext(
    `printer = "p";
    alertPrefs.quietStart = "00:00"; alertPrefs.quietEnd = "23:59";
    latestData = { status: { print_stats: { state: "standby" } }, settings: {} };
    lastDataAt = Date.now();`,
    context,
  );

  const button = document.createElement("button");
  button.dataset.action = "start_queue";
  context.dispatchAction(button);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(posts, 0);
  assert.ok(document.getElementById("toast").textContent.includes("QUIET"));

  context.dispatchAction(button);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(posts, 1);
});

test("fleet strip renders per-printer tiles and switches printers on click", () => {
  const { context, document } = createPanelClient();
  const payload = {
    entry_id: "a",
    fleet: [
      {
        id: "a",
        name: "Voron",
        state: "printing",
        progress: 0.4,
        hotend: 210,
        bed: 60,
        available: true,
      },
      {
        id: "b",
        name: "Ender",
        state: "standby",
        progress: null,
        hotend: null,
        bed: null,
        available: false,
      },
    ],
  };
  vm.runInContext(`renderFleet(${JSON.stringify(payload)})`, context);
  const strip = document.getElementById("fleetStrip");
  assert.equal(strip.hidden, false);
  const tiles = strip.querySelectorAll(".fleet-tile");
  assert.equal(tiles.length, 2);
  assert.match(deepText(tiles[0]), /Voron/);
  assert.match(deepText(tiles[0]), /PRINTING 40%/);
  assert.match(deepText(tiles[0]), /E 210° \/ B 60°/);
  assert.match(deepText(tiles[1]), /OFFLINE/);
  assert.ok(tiles[0].className.includes("active"));
  assert.ok(tiles[1].className.includes("bad"));

  // Clicking the second tile re-points the printer select and refreshes.
  tiles[1].listeners.click();
  assert.equal(document.getElementById("printerSel").value, "b");
  assert.equal(vm.runInContext("printer", context), "b");

  // Single-printer payloads hide the strip entirely.
  vm.runInContext(
    `renderFleet({ entry_id: "a", fleet: [${JSON.stringify(
      payload.fleet[0],
    )}] })`,
    context,
  );
  assert.equal(strip.hidden, true);
  assert.equal(strip.children.length, 0);
});

test("printer health decodes mcu retransmits and console fault signatures", () => {
  const { context, document } = createPanelClient();
  const data = {
    status: { mcu: { last_stats: { bytes_retransmit: 12, bytes_invalid: 0 } } },
    gcode_responses: [
      "// normal line",
      "!! MCU 'mcu' shutdown: Timer too close",
      "Move out of range: 10 400 5",
    ],
  };
  const findings = vm.runInContext(
    `analyzePrinterHealth(${JSON.stringify(data)})`,
    context,
  );
  const mcu = findings.find((f) => f.label === "MCU RETRANSMIT");
  assert.equal(mcu.severity, "warn");
  assert.match(mcu.detail, /12 B/);
  assert.ok(
    findings.some(
      (f) => f.label === "MCU SHUTDOWN LOGGED" && f.severity === "bad",
    ),
  );
  assert.ok(findings.some((f) => f.label === "TIMER TOO CLOSE"));
  assert.ok(findings.some((f) => f.label === "MOVE OUT OF RANGE"));

  vm.runInContext(`renderHealth(${JSON.stringify(data)})`, context);
  const chips = document
    .getElementById("healthChips")
    .querySelectorAll(".health-chip");
  assert.ok(chips.length >= 4);
  assert.equal(
    document.getElementById("healthSummary").textContent,
    "FAULTS LOGGED",
  );

  // Clean stream reports CLEAN with a healthy chip.
  const clean = {
    status: { mcu: { last_stats: {} } },
    gcode_responses: ["ok"],
  };
  vm.runInContext(`renderHealth(${JSON.stringify(clean)})`, context);
  assert.equal(document.getElementById("healthSummary").textContent, "CLEAN");
});

test("maintenance ledger counts down hours and filament and resets per item", () => {
  const { context, document } = createPanelClient();
  const totals = {
    job_totals: { total_print_time: 50 * 3600, total_filament_used: 600000 },
  };
  vm.runInContext(
    `printer = "p1"; renderMaintenance({ history: ${JSON.stringify(totals)} })`,
    context,
  );
  const list = document.getElementById("maintenanceList");
  assert.equal(list.children.length, 5);
  // Fresh ledger seeds the baseline at current totals — full limits remain.
  assert.match(deepText(list.children[0]), /500 H LEFT/);
  assert.match(deepText(list.children[4]), /5000 M LEFT/);
  assert.equal(document.getElementById("maintSummary").textContent, "ALL OK");

  // 100 more print hours consumes the nozzle budget.
  const later = {
    job_totals: { total_print_time: 150 * 3600, total_filament_used: 600000 },
  };
  vm.runInContext(
    `renderMaintenance({ history: ${JSON.stringify(later)} })`,
    context,
  );
  assert.match(deepText(list.children[0]), /400 H LEFT/);

  // Reset re-baselines that item only.
  list.children[0].children[3].listeners.click();
  vm.runInContext(
    `renderMaintenance({ history: ${JSON.stringify(later)} })`,
    context,
  );
  assert.match(deepText(list.children[0]), /500 H LEFT/);
  assert.match(deepText(list.children[1]), /200 H LEFT/);

  // Exceeding a limit flags the row due and the summary.
  const overdue = {
    job_totals: {
      total_print_time: 150 * 3600 + 400 * 3600,
      total_filament_used: 600000,
    },
  };
  vm.runInContext(
    `renderMaintenance({ history: ${JSON.stringify(overdue)} })`,
    context,
  );
  assert.match(deepText(list.children[1]), /0 H LEFT/);
  assert.ok(list.children[1].className.includes("due"));
  assert.match(document.getElementById("maintSummary").textContent, /SERVICE/);
});

test("file analysis renders GO/NO-GO verdicts from spool, bounds, and quiet hours", () => {
  const { context, document } = createPanelClient();
  vm.runInContext(
    `latestData = {
      spool_details: { remaining_weight: 100, filament: { name: "PLA Pro", material: "PLA", vendor: "VendorCo" } },
      bed_bounds: { x: { min: 0, max: 235 }, y: { min: 0, max: 235 }, z: { min: 0, max: 250 } },
      status: { toolhead: { axis_maximum: [235, 235, 250] } },
    };`,
    context,
  );
  const base = {
    estimated_time: 3600,
    filament_total: 2000,
    filament_weight_total: 5,
    filament_type: "PLA",
    layer_count: 10,
    object_height: 20,
    x_min: 0,
    x_max: 210,
    y_min: 0,
    y_max: 210,
    size: 1000,
    has_thumbnail: false,
    slicer: "OrcaSlicer",
  };

  vm.runInContext(`renderFileAnalysis(${JSON.stringify(base)})`, context);
  const verdict = document.getElementById("analysisVerdict");
  assert.equal(verdict.hidden, false);
  assert.equal(verdict.textContent, "CAUTION"); // missing thumbnail is a warning
  assert.match(deepText(document.getElementById("analysisStats")), /PLA Pro/);

  // Material mismatch blocks the job.
  vm.runInContext(
    `renderFileAnalysis(${JSON.stringify({ ...base, filament_type: "PETG" })})`,
    context,
  );
  assert.equal(verdict.textContent, "NO-GO");
  assert.match(
    deepText(document.getElementById("analysisWarnings")),
    /MATERIAL MISMATCH/,
  );

  // Insufficient filament and over-tall object both block.
  vm.runInContext(
    `renderFileAnalysis(${JSON.stringify({
      ...base,
      filament_weight_total: 500,
      object_height: 300,
    })})`,
    context,
  );
  assert.equal(verdict.textContent, "NO-GO");
  assert.match(
    deepText(document.getElementById("analysisWarnings")),
    /NEEDS 500 G/,
  );
  assert.match(
    deepText(document.getElementById("analysisWarnings")),
    /EXCEEDS Z HEIGHT/,
  );

  // Quiet-hours finish shows up as a warning.
  vm.runInContext(
    `alertPrefs = { engine: "off", players: [], events: {}, quietStart: "00:00", quietEnd: "23:59", quietBypass: true };
     renderFileAnalysis(${JSON.stringify(base)})`,
    context,
  );
  assert.match(
    deepText(document.getElementById("analysisWarnings")),
    /QUIET HOURS/,
  );
});

test("bed mesh decay baselines, detects drift, and re-baselines", () => {
  const { context, document, window } = createPanelClient();
  vm.runInContext('printer = "printer-a";', context);
  const matrix = [
    [0.1, 0.0],
    [0.0, -0.1],
  ];

  // First analysis stores a zero-drift baseline.
  const first = JSON.parse(
    vm.runInContext(
      `JSON.stringify(analyzeMeshDecay({ bed_mesh: { mesh_matrix: [[0.1, 0.0], [0.0, -0.1]] } }))`,
      context,
    ),
  );
  assert.equal(first.rmsDrift, 0);
  assert.equal(first.maxDrift, 0);
  assert.ok(
    window.localStorage.getItem("nexusMeshV1.printer-a").includes("baseline"),
  );

  // A shifted surface reports RMS and per-cell drift.
  const shifted = JSON.parse(
    vm.runInContext(
      `JSON.stringify(analyzeMeshDecay({ bed_mesh: { mesh_matrix: [[0.3, 0.0], [0.0, -0.3]] } }))`,
      context,
    ),
  );
  assert.ok(shifted.rmsDrift > 0.14, `rms ${shifted.rmsDrift}`);
  assert.ok(Math.abs(shifted.maxDrift - 0.2) < 1e-9);

  // Rendering flags the drift and paints the heatmap.
  vm.runInContext(
    `renderMeshDecay({ bed_mesh: { mesh_matrix: [[0.3, 0.0], [0.0, -0.3]] } })`,
    context,
  );
  assert.equal(
    document.getElementById("meshDriftSummary").textContent,
    "RE-LEVEL SUGGESTED",
  );
  assert.equal(document.getElementById("meshDriftMap").children.length, 4);
  assert.match(
    document.getElementById("meshDriftMap").children[0].style.background,
    /0, 239, 145/,
  );
  assert.match(
    document.getElementById("meshDriftMap").children[3].style.background,
    /255, 83, 107/,
  );

  // Re-baseline resets drift to zero.
  vm.runInContext(
    "latestData = { status: { bed_mesh: { mesh_matrix: [[0.3, 0.0], [0.0, -0.3]] } } }; resetMeshBaseline();",
    context,
  );
  const after = JSON.parse(
    vm.runInContext(
      `JSON.stringify(analyzeMeshDecay({ bed_mesh: { mesh_matrix: [[0.3, 0.0], [0.0, -0.3]] } }))`,
      context,
    ),
  );
  assert.equal(after.rmsDrift, 0);

  // Missing or malformed mesh degrades cleanly.
  assert.equal(vm.runInContext("analyzeMeshDecay({})", context), null);
  assert.equal(
    vm.runInContext(
      'analyzeMeshDecay({ bed_mesh: { mesh_matrix: "x" } })',
      context,
    ),
    null,
  );
  vm.runInContext("renderMeshDecay({})", context);
  assert.equal(
    document.getElementById("meshDriftSummary").textContent,
    "NO MESH DATA",
  );
  vm.runInContext("latestData = { status: {} }; resetMeshBaseline();", context);
});

test("thermal sentinel flags saturated heaters and PID oscillation", () => {
  const { context } = createPanelClient();

  // Duty pinned at 100% while temperature falls = failing heater cartridge.
  vm.runInContext(
    `thermalSamples = { EXTRUDER: Array.from({ length: 30 }, (_, i) => ({ at: ${Date.now()} - (30 - i) * 1000, t: 210 - i * 0.5, p: 1 })) };`,
    context,
  );
  const saturated = JSON.parse(
    vm.runInContext(
      `JSON.stringify(analyzeThermalHealth({ extruder: { temperature: 194, power: 1, target: 220 } }))`,
      context,
    ),
  );
  assert.equal(saturated[0].severity, "bad");
  assert.match(saturated[0].label, /SATURATED/);

  // Sustained ±4°C oscillation around target = badly tuned PID.
  vm.runInContext(
    `thermalSamples = { BED: Array.from({ length: 80 }, (_, i) => ({ at: ${Date.now()} - (80 - i) * 1000, t: 60 + Math.sin(i / 2) * 4, p: 0.5 })) };`,
    context,
  );
  const oscillating = JSON.parse(
    vm.runInContext(
      `JSON.stringify(analyzeThermalHealth({ heater_bed: { temperature: 60, power: 0.5, target: 60 } }))`,
      context,
    ),
  );
  assert.ok(
    oscillating.some(
      (finding) =>
        finding.severity === "warn" && /OSCILLATION/.test(finding.label),
    ),
  );

  // Cold idle heaters and short histories stay quiet.
  const quiet = JSON.parse(
    vm.runInContext(
      `thermalSamples = {}; JSON.stringify(analyzeThermalHealth({ extruder: { temperature: 24, power: 0, target: 0 } }))`,
      context,
    ),
  );
  assert.equal(quiet.length, 0);
  const short = JSON.parse(
    vm.runInContext(
      `thermalSamples = {}; JSON.stringify(analyzeThermalHealth({ "heater_generic chamber": { temperature: 40, power: 0.3, target: 45 } }))`,
      context,
    ),
  );
  assert.equal(short.length, 0);
});

test("volumetric flow headroom reports melt-limit saturation", () => {
  const { context, document } = createPanelClient();
  vm.runInContext('printer = "printer-a"; maxFlowMm3 = 15;', context);

  // 12 mm/s * 2.405 mm² ≈ 28.9 mm³/s — well above the 15 mm³/s rating.
  vm.runInContext(
    `renderFlowHeadroom({ motion_report: { live_extruder_velocity: 12 } })`,
    context,
  );
  assert.match(
    document.getElementById("flowVolumetric").textContent,
    /28\.9 mm³\/s/,
  );
  assert.equal(document.getElementById("flowHeadroom").textContent, "0%");
  assert.equal(
    document.getElementById("flowHeadroomPill").textContent,
    "AT MELT LIMIT",
  );
  assert.equal(document.getElementById("flowHeadroomBar").style.width, "100%");

  // Sustained saturation produces a health finding after 5 seconds.
  vm.runInContext("flowSaturatedSince = Date.now() - 10000;", context);
  const finding = JSON.parse(
    vm.runInContext(
      `JSON.stringify(renderFlowHeadroom({ motion_report: { live_extruder_velocity: 12 } }))`,
      context,
    ),
  );
  assert.equal(finding.severity, "warn");
  assert.match(finding.label, /FLOW SATURATED/);

  // Comfortable flow reads as headroom; idle reports IDLE and clears the timer.
  vm.runInContext(
    `renderFlowHeadroom({ motion_report: { live_extruder_velocity: 2 } })`,
    context,
  );
  assert.equal(
    document.getElementById("flowHeadroomPill").textContent,
    "HEADROOM OK",
  );
  assert.match(document.getElementById("flowHeadroom").textContent, /68%/);
  vm.runInContext("renderFlowHeadroom({})", context);
  assert.equal(document.getElementById("flowHeadroomPill").textContent, "IDLE");
  assert.equal(vm.runInContext("flowSaturatedSince", context), null);
});

test("energy accounting integrates watts into kWh and cost", () => {
  const { context, document, window } = createPanelClient();
  vm.runInContext('printer = "printer-a";', context);
  window.localStorage.setItem(
    "nexusEnergy.printer-a",
    JSON.stringify({ sensor: "sensor.printer_power", rate: 0.3 }),
  );
  window.hass = {
    states: {
      "sensor.printer_power": {
        state: "240",
        attributes: {
          unit_of_measurement: "W",
          friendly_name: "Printer",
          device_class: "power",
        },
      },
      "sensor.printer_kw": {
        state: "1.5",
        attributes: { unit_of_measurement: "kW" },
      },
      "sensor.other_temp": {
        state: "21",
        attributes: { unit_of_measurement: "°C" },
      },
    },
  };
  vm.runInContext("loadEnergyPrefs(); populateEnergyEntities();", context);

  // The picker only lists power-class sensors.
  const select = document.getElementById("energySensor");
  assert.equal(select.children.length, 2);
  assert.equal(select.value, "sensor.printer_power");

  const data = {
    status: { print_stats: { state: "printing", filename: "part.gcode" } },
  };
  vm.runInContext(`updateEnergy(${JSON.stringify(data)})`, context);
  assert.equal(document.getElementById("energyNow").textContent, "240 W");
  assert.equal(document.getElementById("energyStatus").textContent, "TRACKING");

  // Simulate a 10-minute gap between samples: 240 W * (1/6 h) ≈ 40 Wh.
  vm.runInContext("energySession.lastAt = Date.now() - 600000;", context);
  vm.runInContext(`updateEnergy(${JSON.stringify(data)})`, context);
  assert.match(document.getElementById("energyPrint").textContent, /40 Wh/);
  assert.match(document.getElementById("energyCost").textContent, /\$0\.01/);

  // kW units are converted; a new filename resets the session.
  vm.runInContext('energyPrefs.sensor = "sensor.printer_kw";', context);
  vm.runInContext(
    `updateEnergy(${JSON.stringify({
      status: { print_stats: { state: "printing", filename: "other.gcode" } },
    })})`,
    context,
  );
  assert.equal(document.getElementById("energyNow").textContent, "1500 W");

  // Missing sensor state degrades to NO SENSOR.
  vm.runInContext(
    'energyPrefs.sensor = "sensor.missing"; updateEnergy({})',
    context,
  );
  assert.equal(document.getElementById("energyNow").textContent, "NO SENSOR");
  assert.equal(
    document.getElementById("energyStatus").textContent,
    "NO SENSOR",
  );
});

function loadTranslations(context) {
  const source = fs.readFileSync(
    path.join(__dirname, "../custom_components/moonraker/panel_i18n.js"),
    "utf8",
  );
  vm.runInContext(source, context, { filename: "panel_i18n.js" });
}

test("translation tables cover the same keys in every language and all screen titles", () => {
  const { context } = createPanelClient();
  loadTranslations(context);
  const tables = JSON.parse(
    vm.runInContext("JSON.stringify(window.NEXUS_I18N)", context),
  );
  const titles = JSON.parse(
    vm.runInContext("JSON.stringify(SCREEN_TITLES)", context),
  );
  assert.deepEqual(Object.keys(tables).sort(), ["es", "fr"]);
  assert.deepEqual(
    Object.keys(tables.es).sort(),
    Object.keys(tables.fr).sort(),
  );
  for (const [lang, table] of Object.entries(tables)) {
    for (const [source, translated] of Object.entries(table)) {
      assert.equal(typeof translated, "string", `${lang}:${source}`);
      assert.ok(translated.trim().length, `${lang}:${source} is empty`);
      assert.equal(
        source,
        source.replace(/\s+/g, " ").trim(),
        `${lang}:${source} has unnormalized whitespace`,
      );
    }
    for (const [kicker, title] of Object.values(titles)) {
      assert.ok(table[kicker], `${lang} missing screen kicker ${kicker}`);
      assert.ok(table[title], `${lang} missing screen title ${title}`);
    }
  }
});

test("panel language resolves from HA, translates static and dynamic text, and restores English", () => {
  const { context, document, window } = createPanelClient();
  loadTranslations(context);
  document.documentElement = new FakeElement("html");

  window.hass = { locale: { language: "fr-CA" } };
  assert.equal(vm.runInContext('resolvePanelLanguage("auto")', context), "fr");
  window.hass = { language: "de" };
  assert.equal(vm.runInContext('resolvePanelLanguage("auto")', context), "en");
  assert.equal(vm.runInContext('resolvePanelLanguage("es")', context), "es");

  const root = new FakeElement("div");
  const title = root.appendChild(new FakeElement("h2"));
  title.className = "panel-title";
  title.textContent = "Dashboard Layout";
  const micro = root.appendChild(new FakeElement("p"));
  micro.className = "micro";
  micro.textContent =
    "\n  Dashboard streams start only while this screen is visible.\n  Select NO CAMERA to leave a tile unused.\n";
  const dynamic = root.appendChild(new FakeElement("span"));
  dynamic.className = "micro";
  dynamic.id = "meshBounds";
  dynamic.textContent = "Dashboard Layout";
  const input = root.appendChild(new FakeElement("input"));
  input.setAttribute("placeholder", "FILTER G-CODE FILES");
  const unknown = root.appendChild(new FakeElement("button"));
  unknown.textContent = "PRINT_START_MACRO";
  document.querySelectorAll = (selector) => root.querySelectorAll(selector);

  assert.equal(vm.runInContext('applyPanelLanguage("fr")', context), true);
  assert.equal(vm.runInContext('applyPanelLanguage("fr")', context), false);
  assert.equal(document.documentElement.lang, "fr");
  assert.equal(title.textContent, "Disposition du tableau de bord");
  assert.match(micro.textContent, /^\n\s+Les flux ne démarrent/);
  assert.equal(dynamic.textContent, "Dashboard Layout");
  assert.equal(
    input.getAttribute("placeholder"),
    "FILTRER LES FICHIERS G-CODE",
  );
  assert.equal(unknown.textContent, "PRINT_START_MACRO");
  assert.equal(
    document.getElementById("screenTitle").textContent,
    "Tableau de bord",
  );
  assert.equal(
    document.getElementById("pageKicker").textContent,
    "APPAREIL / VUE EN DIRECT",
  );

  vm.runInContext(
    'setText("flowHeadroomPill", "IDLE"); setText("energyNow", "123 W"); toast("MESH BASELINE RESET");',
    context,
  );
  assert.equal(
    document.getElementById("flowHeadroomPill").textContent,
    "INACTIF",
  );
  assert.equal(document.getElementById("energyNow").textContent, "123 W");
  assert.equal(
    document.getElementById("toast").textContent,
    "RÉFÉRENCE DU MAILLAGE RÉINITIALISÉE",
  );

  vm.runInContext('applyPanelLanguage("en")', context);
  assert.equal(title.textContent, "Dashboard Layout");
  assert.match(micro.textContent, /Dashboard streams start/);
  assert.equal(input.getAttribute("placeholder"), "FILTER G-CODE FILES");
  assert.equal(document.getElementById("screenTitle").textContent, "Dashboard");
  assert.equal(vm.runInContext("t(42)", context), 42);
});

function fireDisplayChange(document, id) {
  const element = document.getElementById(id);
  element.id = id;
  document.listeners.change({ target: element });
}

test("display preferences apply theme, text size, colour-safe palette, and persist per printer", () => {
  const { context, document, window } = createPanelClient();
  const root = (document.documentElement = new FakeElement("html"));
  vm.runInContext(
    'printer = "printer-a"; loadDisplayPrefs(); bindInteractions();',
    context,
  );
  assert.equal(root.dataset.theme, undefined);
  assert.equal(vm.runInContext('statusRgb("ok")', context), "0, 239, 145");

  document.getElementById("displayTheme").value = "contrast";
  document.getElementById("displayTextSize").value = "large";
  document.getElementById("displayColorSafe").checked = true;
  fireDisplayChange(document, "displayTheme");
  assert.equal(root.dataset.theme, "contrast");
  assert.equal(root.dataset.textSize, "large");
  assert.equal(root.dataset.colorSafe, "1");
  assert.equal(vm.runInContext('statusRgb("ok")', context), "86, 180, 233");
  assert.equal(vm.runInContext('statusRgb("bad")', context), "255, 122, 61");
  const saved = JSON.parse(
    window.localStorage.getItem("nexus-display:printer-a"),
  );
  assert.equal(saved.theme, "contrast");
  assert.equal(saved.colorSafe, true);

  // Unknown values fall back to defaults rather than producing broken CSS hooks.
  document.getElementById("displayTheme").value = "neon";
  document.getElementById("displayTextSize").value = "huge";
  document.getElementById("displayColorSafe").checked = false;
  fireDisplayChange(document, "displayTextSize");
  assert.equal(root.dataset.theme, undefined);
  assert.equal(root.dataset.textSize, undefined);
  assert.equal(root.dataset.colorSafe, undefined);

  // Follow-HA tracks the HA dark-mode flag, then the OS colour scheme.
  document.getElementById("displayTheme").value = "auto";
  window.hass = { themes: { darkMode: false } };
  fireDisplayChange(document, "displayTheme");
  assert.equal(root.dataset.theme, "daylight");
  window.hass = { themes: { darkMode: true } };
  vm.runInContext("loadDisplayPrefs()", context);
  assert.equal(root.dataset.theme, undefined);
  window.hass = {};
  window.matchMedia = (query) => ({ matches: query.includes("light") });
  vm.runInContext("loadDisplayPrefs()", context);
  assert.equal(root.dataset.theme, "daylight");

  // A different printer gets its own defaults.
  vm.runInContext('printer = "printer-b"; loadDisplayPrefs();', context);
  assert.equal(root.dataset.theme, undefined);
});

test("colour-safe mode recolours the bed mesh map without green/red hues", () => {
  const { context, document } = createPanelClient();
  vm.runInContext(
    "displayPrefs.colorSafe = true; renderBedMesh({ bed_mesh: { mesh_matrix: [[-0.2, 0.0, 0.2]] } });",
    context,
  );
  const cells = document.getElementById("bedMeshMap").children;
  assert.match(cells[0].style.background, /^hsl\(210 /);
  assert.match(cells[2].style.background, /^hsl\(24 /);
  vm.runInContext(
    "displayPrefs.colorSafe = false; renderBedMesh({ bed_mesh: { mesh_matrix: [[-0.2, 0.0, 0.2]] } });",
    context,
  );
  assert.match(
    document.getElementById("bedMeshMap").children[2].style.background,
    /^hsl\(0 72%/,
  );
});

test("navigation exposes aria-current, arrow-key focus, and Escape closes the details drawer", () => {
  const { context, document } = createPanelClient();
  const navItems = ["dashboard", "print", "movement"].map((name) => {
    const item = new FakeElement("button");
    item.className = "nav-item";
    item.dataset.screenTarget = name;
    item.focus = () => {
      context.focused = name;
    };
    item.scrollIntoView = (options) => {
      context.scrolled = { name, options };
    };
    return item;
  });
  document.querySelectorAll = (selector) =>
    selector === ".nav-item" ? navItems : [];

  vm.runInContext('setScreen("print")', context);
  assert.equal(navItems[1].getAttribute("aria-current"), "page");
  assert.equal(navItems[0].hasAttribute("aria-current"), false);
  assert.equal(context.scrolled.name, "print");
  assert.equal(context.scrolled.options.inline, "center");

  vm.runInContext("bindInteractions()", context);
  const keydown = document.listeners.keydown;
  let prevented = 0;
  const press = (key, target) =>
    keydown({ key, target, preventDefault: () => (prevented += 1) });
  press("ArrowDown", navItems[1]);
  assert.equal(context.focused, "movement");
  press("ArrowRight", navItems[2]);
  assert.equal(context.focused, "dashboard");
  press("ArrowUp", navItems[0]);
  assert.equal(context.focused, "movement");
  press("Home", navItems[2]);
  assert.equal(context.focused, "dashboard");
  press("End", navItems[0]);
  assert.equal(context.focused, "movement");
  assert.equal(prevented, 5);
  press("a", navItems[0]);
  press("ArrowDown", new FakeElement("div"));
  assert.equal(prevented, 5);

  vm.runInContext("detailsOpen = true;", context);
  document.getElementById("pageDetails").hidden = false;
  press("Escape", new FakeElement("div"));
  assert.equal(vm.runInContext("detailsOpen", context), false);
  assert.equal(document.getElementById("pageDetails").hidden, true);
  assert.equal(
    document.getElementById("pageDetails").getAttribute("aria-hidden"),
    "true",
  );
});

test("accessibility enhancement labels canvases, jog buttons, and the toast live region", () => {
  const { context, document } = createPanelClient();
  const jogX = new FakeElement("button");
  jogX.dataset.axis = "X";
  jogX.dataset.dir = "-1";
  const jogZ = new FakeElement("button");
  jogZ.dataset.axis = "Z";
  jogZ.dataset.dir = "1";
  const labelled = new FakeElement("button");
  labelled.setAttribute("aria-label", "Custom");
  document.querySelectorAll = (selector) =>
    selector === '[data-action="jog"]' ? [jogX, jogZ, labelled] : [];
  document
    .getElementById("toolpathCanvas")
    .setAttribute("aria-label", "Existing");

  vm.runInContext("enhanceAccessibility()", context);
  assert.equal(
    document.getElementById("layerSpark").getAttribute("role"),
    "img",
  );
  assert.equal(
    document.getElementById("tempGraph").getAttribute("aria-label"),
    "Hotend and bed temperature graph",
  );
  assert.equal(
    document.getElementById("toolpathCanvas").getAttribute("aria-label"),
    "Existing",
  );
  assert.equal(
    document.getElementById("toast").getAttribute("aria-live"),
    "polite",
  );
  assert.equal(jogX.getAttribute("aria-label"), "Jog X minus");
  assert.equal(jogZ.getAttribute("aria-label"), "Jog Z plus");
  assert.equal(labelled.getAttribute("aria-label"), "Custom");

  // Re-running keeps existing labels intact.
  vm.runInContext("enhanceAccessibility()", context);
  assert.equal(document.getElementById("toast").getAttribute("role"), "status");
});

test("panel markup ships theme, language, skip link, and mobile layout hooks", () => {
  const html = fs.readFileSync(
    path.join(__dirname, "../custom_components/moonraker/panel.html"),
    "utf8",
  );
  for (const id of [
    "displayTheme",
    "displayTextSize",
    "displayColorSafe",
    "displayLanguage",
    "mainContent",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(html, /class="skip-link"\s+href="#mainContent"/);
  assert.match(html, /role="status"\s+aria-live="polite"/);
  assert.match(html, /viewport-fit=cover/);
  assert.match(html, /html\[data-theme="daylight"\]/);
  assert.match(html, /html\[data-color-safe="1"\]/);
  assert.match(html, /@media \(max-width: 600px\)/);
  assert.ok(html.indexOf("panel_i18n.js") < html.indexOf("panel_client.js"));
});

const VALID_THEME = {
  name: "Test Theme",
  vars: {
    "--bg": "#101010",
    "--panel": "#181818",
    "--panel-hi": "#202020",
    "--line": "#303030",
    "--line-hi": "#505050",
    "--green": "#4ade80",
    "--green-soft": "#a7f3c9",
    "--cyan": "#4fc3ff",
    "--red": "#ff5d73",
    "--amber": "#f5b94e",
    "--text": "#e0e0e0",
    "--muted": "#808080",
  },
};

test("built-in themes apply their CSS variable maps and clear cleanly", () => {
  const { context, document } = createPanelClient();
  const root = (document.documentElement = new FakeElement("html"));
  vm.runInContext(
    'printer = "printer-a"; loadCustomThemes(); populateThemeSelect(); displayPrefs.theme = "midnight"; applyTheme();',
    context,
  );
  assert.equal(root.dataset.theme, "midnight");
  assert.equal(root.style["--bg"], "#050b16");
  assert.equal(root.style["--cyan"], "#4fc3ff");

  vm.runInContext('displayPrefs.theme = "nexus"; applyTheme();', context);
  assert.equal(root.dataset.theme, undefined);
  assert.equal(root.style["--bg"], undefined);

  vm.runInContext('displayPrefs.theme = "arctic"; applyTheme();', context);
  assert.equal(root.style["--text"], "#20344a");
});

test("theme select is populated with builtins, structural themes, and auto", () => {
  const { context, document } = createPanelClient();
  document.documentElement = new FakeElement("html");
  vm.runInContext('printer = "p"; populateThemeSelect();', context);
  const select = document.getElementById("displayTheme");
  const values = select.options.map((option) => option.value);
  for (const theme of [
    "nexus",
    "midnight",
    "ember",
    "carbon",
    "solarized",
    "solarized_light",
    "violet",
    "arctic",
    "stealth",
    "clinical",
    "daylight",
    "contrast",
    "auto",
  ])
    assert.ok(values.includes(theme), `missing theme ${theme}`);
});

test("validateTheme accepts a valid file and reports every defect", () => {
  const { context } = createPanelClient();
  const validate = (data) =>
    vm.runInContext(`validateTheme(${JSON.stringify(data)})`, context);

  assert.equal(validate(VALID_THEME).ok, true);

  const missing = { ...VALID_THEME, vars: { ...VALID_THEME.vars } };
  delete missing.vars["--red"];
  assert.match(
    validate(missing).errors.join(";"),
    /missing required variable "--red"/,
  );

  const badColor = {
    ...VALID_THEME,
    vars: { ...VALID_THEME.vars, "--cyan": "notacolor" },
  };
  assert.match(validate(badColor).errors.join(";"), /"--cyan" has an invalid/);

  const unknown = {
    ...VALID_THEME,
    vars: { ...VALID_THEME.vars, "--bogus": "#fff" },
  };
  assert.match(
    validate(unknown).errors.join(";"),
    /unknown variable "--bogus"/,
  );

  const longName = { ...VALID_THEME, name: "x".repeat(60) };
  assert.match(validate(longName).errors.join(";"), /"name"/);
  assert.equal(validate("not-an-object").ok, false);
  assert.equal(validate({ name: "x" }).ok, false);

  // Optional glow/grid/fonts are allowed when valid.
  const optional = {
    ...VALID_THEME,
    vars: {
      ...VALID_THEME.vars,
      "--glow": "rgba(1, 2, 3, 0.5)",
      "--sans": "Inter, sans-serif",
    },
  };
  assert.equal(validate(optional).ok, true);
});

test("uploaded custom theme is stored, listed, and applied", () => {
  const { context, document, window } = createPanelClient();
  const root = (document.documentElement = new FakeElement("html"));
  // Stub FileReader to deliver the JSON synchronously.
  context.FileReader = class {
    readAsText() {
      this.result = JSON.stringify(VALID_THEME);
      this.onload();
    }
  };
  vm.runInContext(
    'printer = "printer-a"; handleThemeUpload({ name: "t.json" });',
    context,
  );
  const stored = JSON.parse(window.localStorage.getItem("nexus-custom-themes"));
  assert.ok(stored["custom:test-theme"]);
  assert.equal(root.dataset.theme, "custom:test-theme");
  assert.equal(root.style["--bg"], "#101010");

  const select = document.getElementById("displayTheme");
  const values = select.options.map((option) => option.value);
  assert.ok(values.includes("custom:test-theme"));
  assert.match(
    document.getElementById("themeUploadStatus").textContent,
    /installed/,
  );
});

test("invalid theme upload is rejected with a readable message", () => {
  const { context, document } = createPanelClient();
  document.documentElement = new FakeElement("html");
  context.FileReader = class {
    readAsText() {
      this.result = "{bad json";
      this.onload();
    }
  };
  vm.runInContext(
    'printer = "p"; handleThemeUpload({ name: "t.json" });',
    context,
  );
  assert.match(
    document.getElementById("themeUploadStatus").textContent,
    /not valid JSON/,
  );

  context.FileReader = class {
    readAsText() {
      this.result = JSON.stringify({ name: "X", vars: {} });
      this.onload();
    }
  };
  vm.runInContext('handleThemeUpload({ name: "t.json" });', context);
  assert.match(
    document.getElementById("themeUploadStatus").textContent,
    /missing required variable/,
  );
});

test("mesh surface view shows corner offsets and last-vs-current delta grid", () => {
  const { context, document } = createPanelClient();
  const zeros = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ];
  const shifted = [
    [0, 0, 0],
    [0, 0.1, 0],
    [0, 0, 0],
  ];
  vm.runInContext(
    `latestData = { analysis: {
      metrics: {
        mesh_corner_offsets: [0.0, 0.12, 0.0, 0.08],
        mesh_tilt_delta: 0.03,
        mesh_surface_delta_rms: 0.04,
      },
      mesh_history: [
        { residuals: ${JSON.stringify(zeros)} },
        { residuals: ${JSON.stringify(shifted)} },
      ],
    } }; renderMeshSurface();`,
    context,
  );
  assert.equal(
    document.getElementById("meshCorners").textContent,
    "FL +0.00 · FR +0.12 · BL +0.00 · BR +0.08",
  );
  assert.equal(document.getElementById("meshTiltDelta").textContent, "30 µm");
  assert.equal(
    document.getElementById("meshSurfaceDelta").textContent,
    "40 µm",
  );
  assert.equal(document.getElementById("meshSnapshots").textContent, "2");
  assert.equal(document.getElementById("meshSurfaceMap").children.length, 9);

  vm.runInContext(
    "latestData = { analysis: { mesh_history: [] } }; renderMeshSurface();",
    context,
  );
  assert.equal(document.getElementById("meshCorners").textContent, "—");
  assert.equal(document.getElementById("meshSurfaceMap").children.length, 0);
});
