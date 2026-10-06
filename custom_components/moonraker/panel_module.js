class MoonrakerControlPanel extends HTMLElement {
  constructor() {
    super();
    this._root = this.attachShadow({ mode: "open" });
    this._frame = document.createElement("iframe");
    this._frame.title = "Moonraker printer control deck";
    this._frame.setAttribute("loading", "eager");
    this._frame.style.cssText = "display:block;width:100%;height:100%;border:0";
    this._frame.addEventListener("load", () => this._syncHass());
    this._root.append(this._frame);
  }

  set hass(hass) {
    this._hass = hass;
    this._syncHass();
  }

  set panel(panel) {
    this._panel = panel;
    const frameUrl = panel?.config?.frame_url || "/api/moonraker/panel_embed";
    if (this._frame.src !== new URL(frameUrl, location.href).href) {
      this._frame.src = frameUrl;
    }
    this._syncHass();
  }

  connectedCallback() {
    this.style.display = "block";
    this.style.width = "100%";
    this.style.height = "100%";
    if (!this._frame.src) {
      this._frame.src = "/api/moonraker/panel_embed";
    }
    this._syncHass();
  }

  _syncHass() {
    if (!this._hass || !this._frame.contentWindow) {
      return;
    }
    const frameWindow = this._frame.contentWindow;
    frameWindow.hass = this._hass;
    if (!frameWindow.moonrakerHassReady) {
      frameWindow.moonrakerHassReady = true;
      frameWindow.dispatchEvent(new frameWindow.Event("moonraker-hass-ready"));
    }
  }
}

customElements.define("moonraker-control-panel", MoonrakerControlPanel);
