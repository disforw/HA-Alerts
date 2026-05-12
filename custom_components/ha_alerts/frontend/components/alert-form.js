import { testNotification, suggestEntityId, checkEntityId } from "../api/ws.js";
import { bindTemplateStatus } from "../api/templates.js";
import { renderCategoryOptions } from "./category-select.js";

export function renderAlertForm(panel) {
  const a = panel._editingAlert;
  const isEdit = !!a._isEdit;
  const t = panel._t.bind(panel);
  const esc = panel._esc.bind(panel);

  const title = isEdit ? t("form_title_edit", { name: a.name }) : t("form_title_new");
  const nc = a.notification || {};

  const fullEntityId = (a.entity_id || '').trim();
  const objectId = fullEntityId.startsWith('binary_sensor.ha_alerts_')
    ? fullEntityId.slice('binary_sensor.ha_alerts_'.length)
    : (fullEntityId.split('.')[1] || '').replace(/^ha_alerts_/, '');

  const catOptions = renderCategoryOptions({
    categories: panel._categories,
    selectedId: a.category_id || "default",
    esc,
  });

  return `
    <div class="toolbar">
      <h1>${esc(title)}</h1>
      <button id="btn-back" class="secondary-btn">${esc(t("btn_back"))}</button>
    </div>

    <div class="form-container">

      <div class="form-field">
        <label>${esc(t("field_name"))}</label>
        <input type="text" id="f-name" value="${esc(a.name || "")}" placeholder="${esc(t("ph_name"))}" />
      </div>

      <div class="form-field">
        <label>${esc(t("field_entity_id"))}</label>
        <div class="id-input-wrap">
          <span class="id-prefix">binary_sensor.ha_alerts_</span>
          <input type="text" id="f-entity-id" value="${esc(objectId || "")}" placeholder="${esc(panel._entityIdPlaceholderObj || "")}" />
          <span class="id-error" id="id-error"></span>
        </div>
      </div>

      <div class="form-field">
        <label>${esc(t("field_description"))}</label>
        <textarea id="f-description" rows="2" maxlength="255" placeholder="${esc(t("ph_description"))}">${esc(a.description || "")}</textarea>
        <div class="hint" id="desc-char-count" style="text-align:right">${(a.description || "").length}/255</div>
      </div>

      <div class="form-field">
        <label>${esc(t("field_condition"))}</label>
        <textarea id="f-condition" rows="3" placeholder="${esc(t("ph_condition"))}">${esc(a.condition || "")}</textarea>
        <div class="tpl-status" id="condition-preview"></div>
      </div>

      <div class="form-field">
        <label>${esc(t("field_category"))}</label>
        <div class="cat-row">
          <select id="f-category">
            ${catOptions}
            <option value="__new__">${esc(t("btn_create_category"))}</option>
          </select>
          <input type="text" id="f-newcat" placeholder="${esc(t("ph_new_category"))}" style="display:none" />
        </div>
      </div>

      <div class="form-field">
        <label class="checkbox-label notif-toggle">
          <input type="checkbox" id="f-notif-enabled" ${nc.enabled ? "checked" : ""} />
          <ha-icon icon="mdi:bell-outline" style="--mdc-icon-size:20px;"></ha-icon>
          ${esc(t("field_notif_enabled"))}
        </label>
      </div>

      <div id="notif-config" class="notif-section" style="display:${nc.enabled ? "block" : "none"}">
        <div class="form-field">
          <label>${esc(t("field_targets"))}</label>
          <div class="target-row">
            <select id="f-notif-target-select">
              <option value="">${esc(t("ph_select_target"))}</option>
              ${(panel._notifyServices || []).map((s) => `<option value="${s}">${s}</option>`).join("")}
            </select>
            <button type="button" id="btn-add-target" class="secondary-btn small">${esc(t("btn_add_target"))}</button>
          </div>
          <div id="notif-target-chips" class="chip-list">${(nc.targets || [])
            .map((tt) => `<span class="chip" data-target="${esc(tt)}">${esc(tt)} <button class="chip-x" data-rm="${esc(tt)}">×</button></span>`)
            .join("")}</div>
          <div id="notif-target-error" class="error-msg" style="display:${panel._notifyError ? "block" : "none"}; margin:6px 0 0 0">${esc(panel._notifyError || "")}</div>
        </div>

        <div class="form-field">
          <label>${esc(t("field_title"))}</label>
          <input type="text" id="f-notif-title" value="${esc(nc.title || "")}" placeholder="${esc(t("ph_title_optional"))}" />
          <div class="hint">${esc(t("hint_title_blank"))}</div>
          <div class="tpl-status" id="tpl-status-title"></div>
        </div>

        <div class="form-field">
          <label>${esc(t("field_message"))}</label>
          <textarea id="f-notif-message" rows="2" placeholder="${esc(panel._notifDefaults.message)}">${esc(nc.message || "")}</textarea>
          <div class="tpl-status" id="tpl-status-message"></div>
        </div>

        <div class="form-field">
          <label>${esc(t("field_resolve_message"))}</label>
          <textarea id="f-notif-resolve-msg" rows="2" placeholder="${esc(panel._notifDefaults.resolve_message)}">${esc(nc.resolve_message || "")}</textarea>
          <div class="hint">${esc(t("hint_resolve_message"))}</div>
          <div class="tpl-status" id="tpl-status-resolve-message"></div>
        </div>

        <div class="form-field">
          <label>${esc(t("field_data"))}</label>
          <textarea id="f-notif-data" rows="5" placeholder='${esc(t("ph_data_json"))}'>${nc.data ? JSON.stringify(nc.data, null, 2) : ""}</textarea>
          <div class="hint">${esc(t("hint_data_shared"))}</div>
        </div>

        <div class="form-field">
          <label>${esc(t("field_repeat"))}</label>
          <input type="number" id="f-notif-repeat" min="0" class="narrow" value="${nc.repeat !== undefined ? nc.repeat : 0}" />
          <div class="hint">${esc(t("hint_repeat_zero"))}</div>
        </div>

        <div class="form-field" id="skip-first-field" style="display:${nc.repeat > 0 ? 'block' : 'none'}">
          <label class="checkbox-label">
            <input type="checkbox" id="f-notif-skip-first" ${nc.skip_first ? "checked" : ""} />
            ${esc(t("field_skip_first"))}
          </label>
          <div class="hint">${esc(t("hint_skip_first"))}</div>
        </div>

        <div class="test-btn-row">
          <button type="button" id="btn-test-notif" class="secondary-btn">
            <ha-icon icon="mdi:send" style="--mdc-icon-size:16px;"></ha-icon> ${esc(t("btn_test_alert"))}
          </button>
          <span id="test-notif-status" class="hint"></span>
        </div>
      </div>

      <div class="form-actions">
        <button id="btn-save" class="primary-btn">${isEdit ? esc(t("btn_update")) : esc(t("btn_create"))}</button>
        <button id="btn-cancel" class="secondary-btn">${esc(t("btn_cancel"))}</button>
      </div>

      <div id="form-error" class="error-msg" style="display:none"></div>
    </div>
  `;
}

export function bindAlertForm(panel) {
  const root = panel.shadowRoot;
  const t = panel._t.bind(panel);

  root.querySelector("#btn-back")?.addEventListener("click", () => panel._closeForm());
  root.querySelector("#btn-cancel")?.addEventListener("click", () => panel._closeForm());
  root.querySelector("#btn-save")?.addEventListener("click", () => panel._saveAlert());

  // Category "create new" toggle
  const catSel = root.querySelector("#f-category");
  const newCatInput = root.querySelector("#f-newcat");
  catSel?.addEventListener("change", () => {
    if (!newCatInput) return;
    newCatInput.style.display = catSel.value === "__new__" ? "" : "none";
  });

  // Notification toggle
  const notifEnabled = root.querySelector("#f-notif-enabled");
  const notifConfig = root.querySelector("#notif-config");
  notifEnabled?.addEventListener("change", () => {
    if (!notifConfig) return;
    notifConfig.style.display = notifEnabled.checked ? "block" : "none";
    panel._updateSaveBtn?.();
  });

  repeatInput?.addEventListener("blur", normalizeRepeat);
  repeatInput?.addEventListener("change", normalizeRepeat);

  // Skip first field — show only when repeat > 0
  const skipFirstField = root.querySelector("#skip-first-field");
  const updateSkipFirstVisibility = () => {
    const currentVal = parseInt(repeatInput?.value || "0", 10) || 0;
    if (skipFirstField) {
      skipFirstField.style.display = currentVal > 0 ? "block" : "none";
    }
  };
  repeatInput?.addEventListener("change", updateSkipFirstVisibility);
  repeatInput?.addEventListener("blur", updateSkipFirstVisibility);
  // Initialize visibility
  setTimeout(updateSkipFirstVisibility, 0);

  // Target chips add/remove
  const targetSelect = root.querySelector("#f-notif-target-select");
  const btnAddTarget = root.querySelector("#btn-add-target");
  const chipList = root.querySelector("#notif-target-chips");

  const addTargetChip = (target) => {
    if (!target || !chipList) return;
    if (chipList.querySelector(`[data-target="${CSS.escape(target)}"]`)) return;
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.dataset.target = target;
    chip.innerHTML = `${panel._esc(target)} <button class="chip-x" data-rm="${panel._esc(target)}">×</button>`;
    chip.querySelector(".chip-x").addEventListener("click", () => chip.remove());
    chipList.appendChild(chip);
  };

  btnAddTarget?.addEventListener("click", () => {
    addTargetChip(targetSelect?.value);
    if (targetSelect) targetSelect.value = "";
  });

  chipList?.querySelectorAll(".chip-x").forEach((btn) => {
    btn.addEventListener("click", () => btn.closest(".chip")?.remove());
  });

  // Helper: test notif context
  const getTestContext = () => {
    const name = root.querySelector("#f-name")?.value || "Test Alert";
    const condition = root.querySelector("#f-condition")?.value || "";
    const entInput = root.querySelector("#f-entity-id");
    const objectId = entInput?.value?.trim() || entInput?.placeholder?.trim() || "test";
    const entityId = objectId ? `binary_sensor.ha_alerts_${objectId}` : "binary_sensor.ha_alerts_test";
    return { context_name: name, context_condition: condition, context_entity_id: entityId };
  };

  const parseDataField = (selector) => {
    const str = root.querySelector(selector)?.value?.trim();
    if (!str) return null;
    try { return JSON.parse(str); } catch (_) { return null; }
  };

  // Test notification button
  root.querySelector("#btn-test-notif")?.addEventListener("click", async () => {
    const statusEl = root.querySelector("#test-notif-status");
    const targets = [...(chipList?.querySelectorAll(".chip") || [])].map((c) => c.dataset.target);
    if (targets.length === 0) {
      statusEl.textContent = t("status_no_targets");
      statusEl.style.color = "var(--error-color)";
      return;
    }
    const title = root.querySelector("#f-notif-title")?.value || "";
    const message = root.querySelector("#f-notif-message")?.value || "";
    const data = parseDataField("#f-notif-data");
    statusEl.textContent = t("status_sending");
    statusEl.style.color = "";
    try {
      await testNotification(panel._hass, { targets, title, message, data, is_resolve: false, ...getTestContext() });
      statusEl.textContent = t("status_sent");
      statusEl.style.color = "var(--success-color)";
    } catch (e) {
      statusEl.textContent = t("err_prefix") + (e.message || e);
      statusEl.style.color = "var(--error-color)";
    }
    setTimeout(() => { statusEl.textContent = ""; }, 5000);
  });

  // Entity ID live validation
  const entInput = root.querySelector("#f-entity-id");
  const idError = root.querySelector("#id-error");
  const a = panel._editingAlert;

  const setIdError = (msg) => { if (idError) idError.textContent = msg || ""; };

  const descEl = root.querySelector("#f-description");
  if (descEl) {
    const descCounter = root.querySelector("#desc-char-count");
    descEl.addEventListener("input", () => {
      if (descEl.value.length > 255) descEl.value = descEl.value.slice(0, 255);
      if (descCounter) descCounter.textContent = `${descEl.value.length}/255`;
    });
  }

  // Suggest entity_id placeholder from name (debounced)
  const nameInput = root.querySelector("#f-name");
  let suggestTimer = null;
  const runSuggest = async () => {
    if (!nameInput || !entInput) return;
    const name = nameInput.value.trim();
    try {
      const res = await suggestEntityId(panel._hass, name || "Alert", a?._isEdit ? a.id : undefined);
      const full = (res.entity_id || '').trim();
      const obj = full.startsWith('binary_sensor.ha_alerts_')
        ? full.slice('binary_sensor.ha_alerts_'.length)
        : (full.split('.')[1] || '').replace(/^ha_alerts_/, '');
      panel._entityIdPlaceholderObj = obj;
      if (!entInput.value.trim()) entInput.placeholder = panel._entityIdPlaceholderObj || '';
    } catch (_) {}
  };

  if (nameInput && entInput) {
    setTimeout(runSuggest, 0);
    nameInput.addEventListener("input", () => {
      if (suggestTimer) clearTimeout(suggestTimer);
      suggestTimer = setTimeout(runSuggest, 400);
    });
  }

  let checkTimer = null;
  const validateEntityId = async () => {
    if (!entInput) return;
    const v = entInput.value.trim();
    const isEdit = !!a?._isEdit;
    if (!v) {
      if (isEdit) { setIdError(t("err_id_required")); panel._idValid = false; }
      else { setIdError(""); panel._idValid = true; }
      panel._updateSaveBtn();
      return;
    }
    if (!/^[a-z0-9_]+$/.test(v)) {
      setIdError(t("err_id_invalid")); panel._idValid = false; panel._updateSaveBtn(); return;
    }
    try {
      const res = await checkEntityId(panel._hass, `binary_sensor.ha_alerts_${v}`, isEdit ? a.id : undefined);
      if (!res.valid) { setIdError(t("err_id_invalid")); panel._idValid = false; }
      else if (!res.available) { setIdError(t("err_id_exists")); panel._idValid = false; }
      else { setIdError(""); panel._idValid = true; }
    } catch (e) {
      setIdError(t("err_prefix") + (e.message || e)); panel._idValid = false;
    }
    panel._updateSaveBtn();
  };

  if (entInput) {
    panel._idValid = a?._isEdit ? false : null;
    entInput.addEventListener("input", () => {
      if (checkTimer) clearTimeout(checkTimer);
      checkTimer = setTimeout(validateEntityId, 300);
    });
    setTimeout(validateEntityId, 0);
  }

  // Condition live preview
  const condInput = root.querySelector("#f-condition");
  const condStatus = root.querySelector("#condition-preview");
  if (condInput && condStatus) {
    const cleanup = bindTemplateStatus({
      hass: panel._hass,
      inputEl: condInput,
      statusEl: condStatus,
      t,
      debounceMs: 500,
      render: true,
      requireBoolean: true,
      getVariables: () => (typeof panel._getTemplatePreviewVariables === "function" ? panel._getTemplatePreviewVariables() : null),
      onPlainValue: (val) => {
        const entityId = (val || "").trim();
        if (!entityId) return { text: "", cls: "", valid: null };
        const stateObj = panel._hass?.states?.[entityId];
        if (!stateObj) return { text: t("preview_entity_not_found", { condition: entityId }), cls: "error", valid: false };
        return { text: t("preview_entity_state", { val: stateObj.state }), cls: "ok", valid: true };
      },
      onValidityChange: (v) => { panel._conditionValid = v; panel._updateSaveBtn(); },

      maxLen: 200,
    });
    if (typeof panel._registerCleanup === "function") panel._registerCleanup(cleanup);
  }

  // Template syntax validation for notification fields
  const tplFields = [
    { input: "#f-notif-title", status: "#tpl-status-title", key: "title" },
    { input: "#f-notif-message", status: "#tpl-status-message", key: "message" },
    { input: "#f-notif-resolve-msg", status: "#tpl-status-resolve-message", key: "resolve_message" },
  ];

  for (const tf of tplFields) {
    const inputEl = root.querySelector(tf.input);
    const statusEl = root.querySelector(tf.status);
    if (inputEl && statusEl) {
      const cleanup = bindTemplateStatus({
        hass: panel._hass,
        inputEl,
        statusEl,
        t,
        debounceMs: 600,
        render: true,
        requireBoolean: false,
        getVariables: () => (typeof panel._getTemplatePreviewVariables === "function" ? panel._getTemplatePreviewVariables() : null),
        onValidityChange: (v) => {
          if (!panel._notifTplValidity) panel._notifTplValidity = {};
          panel._notifTplValidity[tf.key] = v;
          panel._updateSaveBtn();
        },
        baseClass: "tpl-status",
        okClass: "ok",
        errorClass: "error",
        maxLen: 160,
      });
      if (typeof panel._registerCleanup === "function") panel._registerCleanup(cleanup);
    }
  }
}
