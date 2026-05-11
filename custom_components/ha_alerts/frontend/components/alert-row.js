// Render a single alert row in the list view.

export function renderAlertRow({ alert, t, esc }) {
  return `
    <div class="alert-row" data-id="${alert.id}">
      <ha-icon icon="mdi:alert-circle-outline" style="--mdc-icon-size:22px; flex-shrink:0;"></ha-icon>
      <span class="alert-name">${esc(alert.name)}</span>
      <span class="alert-condition"><code>${esc(alert.condition)}</code></span>
      <div class="alert-menu-wrap">
        <button class="icon-btn menu-btn" data-menu-id="${alert.id}" title="${esc(t("status_actions"))}">
          <ha-icon icon="mdi:dots-vertical" style="--mdc-icon-size:20px;"></ha-icon>
        </button>
        <div class="alert-menu" id="menu-${alert.id}">
          <button class="menu-item" data-action="edit" data-id="${alert.id}">
            <ha-icon icon="mdi:pencil" style="--mdc-icon-size:18px;"></ha-icon> ${esc(t("btn_edit"))}
          </button>
          <button class="menu-item danger" data-action="delete" data-id="${alert.id}">
            <ha-icon icon="mdi:delete" style="--mdc-icon-size:18px;"></ha-icon> ${esc(t("btn_delete"))}
          </button>
        </div>
      </div>
    </div>`;
}
