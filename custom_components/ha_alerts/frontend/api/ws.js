// Centralized WebSocket calls for HA Alerts panel.
// Keep all hass.callWS payloads here, so UI code stays clean.

function assertHass(hass) {
  if (!hass || typeof hass.callWS !== "function") {
    throw new Error("HA Alerts: hass.callWS is not available");
  }
}

export async function listAlerts(hass) {
  assertHass(hass);
  return hass.callWS({ type: "ha_alerts/alert/list" });
}

export async function createAlert(hass, payload) {
  assertHass(hass);
  return hass.callWS({ type: "ha_alerts/alert/create", ...payload });
}

export async function updateAlert(hass, payload) {
  assertHass(hass);
  return hass.callWS({ type: "ha_alerts/alert/update", ...payload });
}

export async function deleteAlert(hass, alert_uid) {
  assertHass(hass);
  return hass.callWS({ type: "ha_alerts/alert/delete", alert_uid });
}

export async function listCategories(hass) {
  assertHass(hass);
  return hass.callWS({ type: "ha_alerts/category/list" });
}

export async function notifyServices(hass) {
  assertHass(hass);
  return hass.callWS({ type: "ha_alerts/notify_services" });
}

export async function testNotification(hass, payload) {
  assertHass(hass);
  return hass.callWS({ type: "ha_alerts/test_notification", ...payload });
}

export async function getTranslations(hass, language) {
  assertHass(hass);
  return hass.callWS({ type: "ha_alerts/get_translations", language });
}


export async function suggestEntityId(hass, name, alert_uid) {
  assertHass(hass);
  const payload = { type: "ha_alerts/entity_id/suggest", name };
  if (alert_uid) payload.alert_uid = alert_uid;
  return hass.callWS(payload);
}

export async function checkEntityId(hass, entity_id, alert_uid) {
  assertHass(hass);
  const payload = { type: "ha_alerts/entity_id/check", entity_id };
  if (alert_uid) payload.alert_uid = alert_uid;
  return hass.callWS(payload);
}
