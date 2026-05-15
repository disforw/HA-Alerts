// HA Alerts built-in panel entrypoint
// Version: 2.0.2
import "./ha-alerts-panel.js";

class HaPanelHaAlerts extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._panelEl = null;
    this._hass = undefined;
    this._panel = undefined;
    this._narrow = undefined;
    this._loaded = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (this._panelEl) this._panelEl.hass = hass;
  }

  set panel(panel) {
    this._panel = panel;
    if (this._panelEl) this._panelEl.panel = panel;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    if (this._panelEl) this._panelEl.narrow = narrow;
  }

  connectedCallback() {
    if (this._loaded) return;
    this._loaded = true;

    // Create the panel element immediately (module is already loaded via static import)
    this._panelEl = document.createElement("ha-alerts-panel");
    this.shadowRoot.appendChild(this._panelEl);

    // Flush any props that arrived before we were connected.
    if (this._hass !== undefined) this._panelEl.hass = this._hass;
    if (this._panel !== undefined) this._panelEl.panel = this._panel;
    if (this._narrow !== undefined) this._panelEl.narrow = this._narrow;
  }
}

if (!customElements.get("ha-panel-ha-alerts")) {
  customElements.define("ha-panel-ha-alerts", HaPanelHaAlerts);
}
