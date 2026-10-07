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
      add: name => this._setClass(name, true),
      remove: name => this._setClass(name, false),
      contains: name => this.className.split(/\s+/).includes(name),
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
    const enabled = force === undefined ? !this.classList.contains(name) : Boolean(force);
    this._setClass(name, enabled);
    return enabled;
  }

  append(...nodes) {
    nodes.forEach(node => this.appendChild(node));
  }

  appendChild(node) {
    this.children.push(node);
    return node;
  }

  replaceChildren(...nodes) {
    this.children = [];
    this.append(...nodes);
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

  removeAttribute(name) {
    delete this.attributes[name];
    if (name === "src") this.src = "";
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  querySelectorAll(selector) {
    const found = [];
    const visit = node => {
      node.children.forEach(child => {
        if (matches(child, selector)) found.push(child);
        visit(child);
      });
    };
    visit(this);
    return found;
  }
}

function matches(element, selector) {
  if (selector.startsWith(".")) return element.className.split(/\s+/).includes(selector.slice(1));
  if (selector === "img") return element.tagName === "IMG";
  const attribute = selector.match(/^\[data-([\w-]+)\]$/);
  if (attribute) {
    const key = attribute[1].replace(/-([a-z])/g, (_match, letter) => letter.toUpperCase());
    return Object.hasOwn(element.dataset, key);
  }
  return false;
}

class FakeDocument {
  constructor(ids = []) {
    this.elements = new Map(ids.map(id => [id, new FakeElement()]));
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
    "cameraLayout", "cameraGrid", "webcam", "webcamCard", "cameraEmpty",
    "cameraName", "cameraGridStatus", "networkCameras", "commandHistory",
    "commandHistoryCount", "detailsTitle", "detailsSummary", "detailsRows",
    "pageDetails", "detailsScrim", "detailsToggle", "console", "toast",
    "sysPrinterState", "sysKlippy", "sysKlipperVersion", "sysMoonrakerVersion",
    "sysCpu", "sysHostTemp", "systemPrinterState", "systemKlippy",
    "systemKlipperVersion", "systemMoonrakerVersion", "systemCpu", "systemHostTemp",
    "systemLive", "dashboardSystemLive",
  ];
  const document = new FakeDocument(ids);
  document.getElementById("cameraLayout").value = "1x1";
  const window = { addEventListener() {}, removeEventListener() {} };
  const context = vm.createContext({
    document,
    window,
    console,
    requestAnimationFrame: callback => callback(),
  });
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
    { name: "Front", stream_url: "http://camera/front", snapshot_url: "http://camera/front.jpg" },
    { name: "Side", stream_url: "http://camera/side", snapshot_url: null },
  ];

  for (const [layout, expectedTiles] of [["1x1", 1], ["1x2", 2], ["2x2", 4]]) {
    document.getElementById("cameraLayout").value = layout;
    vm.runInContext(
      `activeScreen = "camera"; cameraLayout = ${JSON.stringify(layout)}; cameraGridSignature = ""; renderCamera(webcams);`,
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
  const tiles = document.getElementById("cameraGrid").querySelectorAll(".camera-tile");
  assert.ok(tiles.every(tile => tile.querySelector("img").src === ""));
  assert.equal(document.getElementById("webcam").src, "");
});

test("camera selectors can assign a source to a tile", () => {
  const { context, document } = createPanelClient();
  context.webcams = [
    { name: "Front", stream_url: "http://camera/front" },
    { name: "Side", stream_url: "http://camera/side" },
  ];
  document.getElementById("cameraLayout").value = "1x2";
  vm.runInContext('activeScreen = "camera"; cameraLayout = "1x2"; cameraGridSignature = ""; renderCamera(webcams);', context);
  const tiles = document.getElementById("cameraGrid").querySelectorAll(".camera-tile");
  const secondSelector = tiles[1].querySelector("[data-camera-slot]");
  secondSelector.value = "Front";
  vm.runInContext('cameraAssignments[1] = "Front"; renderCamera(webcams);', context);
  assert.equal(tiles[1].querySelector("img").src, "http://camera/front");
});

test("command history is bounded, per-printer, session-only, and only records successful sends", async () => {
  const { context, document, window } = createPanelClient();
  context.toast = () => {};
  context.refresh = () => {};
  vm.runInContext('printer = "printer-a";', context);
  for (let index = 0; index < 105; index++) context.recordSentCommand(`G1 X${index}`);
  assert.equal(document.getElementById("commandHistory").querySelectorAll(".command-entry").length, 100);
  assert.equal(document.getElementById("commandHistoryCount").textContent, "100 COMMANDS");

  window.hass = {
    callApi: async () => ({ ok: true }),
    fetchWithAuth: async () => null,
  };
  await context.act("run_gcode", null, null, { script: "M105" });
  assert.equal(document.getElementById("commandHistoryCount").textContent, "100 COMMANDS");
  assert.match(deepText(document.getElementById("commandHistory")), /M105/);

  window.hass.callApi = async () => ({ ok: false, error: "rejected" });
  await context.act("run_gcode", null, null, { script: "G1 X999" });
  assert.doesNotMatch(deepText(document.getElementById("commandHistory")), /G1 X999/);

  vm.runInContext('printer = "printer-b"; renderSentCommandHistory();', context);
  assert.equal(document.getElementById("commandHistoryCount").textContent, "0 COMMANDS");
});

test("system status binds printer, firmware, server, CPU, and host temperature values", () => {
  const { context, document } = createPanelClient();
  const data = {
    available: true,
    printer_info: { state: "ready", klippy_state: "ready", software_version: "klipper-v0.12" },
    machine_update: { version_info: {} },
    server_info: { moonraker_version: "moonraker-v0.9" },
    system_info: { cpu_info: { model: "Test SBC" } },
  };
  context.renderSystem(data, { "temperature_host host_temp": { temperature: 42.5 } }, "PRINTING");

  assert.equal(document.getElementById("systemPrinterState").textContent, "ready");
  assert.equal(document.getElementById("systemKlippy").textContent, "ready");
  assert.equal(document.getElementById("systemKlipperVersion").textContent, "klipper-v0.12");
  assert.equal(document.getElementById("systemMoonrakerVersion").textContent, "moonraker-v0.9");
  assert.equal(document.getElementById("systemCpu").textContent, "Test SBC");
  assert.equal(document.getElementById("systemHostTemp").textContent, "42.5°C");
  assert.equal(document.getElementById("sysPrinterState").textContent, "ready");

  context.renderSystem(data, {}, "PRINTING");
  assert.equal(document.getElementById("systemHostTemp").textContent, "NOT REPORTED");
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
    webcams: [{ name: "Front", stream_url: "http://camera/front", snapshot_url: null }],
    macros: ["PRINT_START"],
    gcode_responses: ["ok"],
    power_devices: [{ device: "psu", status: "on", locked_while_printing: false }],
    machine_update: {},
    queue: {},
    spoolman: {},
    meta: { estimated_time: 60, filament_total: 1000, layer_count: 10 },
    status: {
      print_stats: { state: "printing", filename: "part.gcode", print_duration: 10, filament_used: 50, info: { current_layer: 2, total_layer: 10 } },
      virtual_sdcard: { file_path: "part.gcode", file_position: 10, file_size: 100 },
      toolhead: { position: [1, 2, 3, 4], homed_axes: "xyz", max_velocity: 300, max_accel: 5000 },
      gcode_move: { speed: 5, speed_factor: 1, extrude_factor: 1, absolute_coordinates: true },
      extruder: { temperature: 200, target: 210 },
      heater_bed: { temperature: 60, target: 60 },
      fan: { speed: 0.5 },
      bed_mesh: { profile_name: "default", mesh_matrix: [[0.1, -0.1], [0, 0.2]] },
      probe: { last_query: 0 },
      input_shaper: { shaper_type_x: "mzv" },
      "temperature_sensor chamber": { temperature: 35, target: 0, power: 0 },
      "filament_switch_sensor runout": { filament_detected: true },
      "gcode_macro PRINT_START": { state: "ready" },
    },
  };

  const screens = ["dashboard", "print", "movement", "thermal", "extruder", "bedmesh", "tuning", "macros", "files", "history", "camera", "console", "hardware", "system", "network", "settings", "components"];
  for (const screen of screens) {
    vm.runInContext(`activeScreen = ${JSON.stringify(screen)}; renderPageDetails(testData);`, context);
    assert.ok(document.getElementById("detailsRows").children.length > 0, `${screen} should render details`);
  }
  vm.runInContext('activeScreen = "network"; renderPageDetails(testData);', context);
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
  vm.runInContext('latestData = testData; bindInteractions();', context);
  const click = document.listeners.click;
  click({ target: { closest: selector => selector === "[data-details-toggle]" ? {} : null } });
  assert.equal(document.getElementById("pageDetails").hidden, false);
  assert.equal(document.getElementById("detailsScrim").hidden, false);
  click({ target: { closest: selector => selector === "[data-details-close]" ? {} : null } });
  assert.equal(document.getElementById("pageDetails").hidden, true);
  assert.equal(document.getElementById("detailsScrim").hidden, true);
});

test("panel markup exposes the camera layouts, wide console, and page details control", () => {
  const html = fs.readFileSync(path.join(__dirname, "../custom_components/moonraker/panel.html"), "utf8");
  assert.match(html, /<option value="1x1">/);
  assert.match(html, /<option value="1x2">/);
  assert.match(html, /<option value="2x2">/);
  assert.match(html, /id="commandHistory"/);
  assert.match(html, /data-details-toggle/);
  assert.match(html, /id="screen-console"[\s\S]*?class="panel span-12"/);
  assert.match(html, /id="systemPrinterState"/);
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => id);
  assert.deepEqual(ids.filter((id, index) => ids.indexOf(id) !== index), []);
  assert.match(html, /\.toolpath-box\s*\{[^}]*height:\s*clamp\(280px,44vh,560px\)/);
  assert.match(html, /@media \(max-width: 720px\)[\s\S]*\.toolpath-box \{ height: clamp\(260px,52vh,420px\)/);
});

test("custom panel sizes its iframe to the available viewport and responds to resize", () => {
  const listeners = new Map();
  const viewportListeners = new Map();
  const window = {
    innerHeight: 800,
    addEventListener: (name, callback) => listeners.set(name, callback),
    removeEventListener: name => listeners.delete(name),
    visualViewport: {
      height: 800,
      addEventListener: (name, callback) => viewportListeners.set(name, callback),
      removeEventListener: name => viewportListeners.delete(name),
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
  const customElements = { define: (_name, definition) => { registeredClass = definition; } };
  const document = { createElement: tagName => new FakeElement(tagName) };
  const context = vm.createContext({
    HTMLElement: FakeHTMLElement,
    customElements,
    document,
    window,
    location: { href: "http://ha.local/" },
    requestAnimationFrame: callback => callback(),
  });
  const source = fs.readFileSync(path.join(__dirname, "../custom_components/moonraker/panel_module.js"), "utf8");
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
