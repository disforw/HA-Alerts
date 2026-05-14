"""The HA Alerts integration."""

from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv




from .const import (
    DOMAIN,
    SERVICE_ADD,
    SERVICE_REMOVE,
    SERVICE_UPDATE,
    SERVICE_ENABLE,
    SERVICE_DISABLE,
    INTEGRATION_VERSION as _INTEGRATION_VERSION,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

from .store import HaAlertsManager, HaAlertsStore
from .websocket_api import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)


PANEL_URL_ROOT = f"/{DOMAIN}_panel"
PANEL_FS_ROOT = str((Path(__file__).resolve().parent / "frontend"))

PLATFORMS = [Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the HA Alerts domain (no YAML config)."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Alerts from a config entry."""

    # --- One-time domain-level registrations (guarded, not unloadable) ---
    if not hass.data[DOMAIN].get("_ws_registered"):
        async_register_websocket_commands(hass)
        hass.data[DOMAIN]["_ws_registered"] = True

    if not hass.data[DOMAIN].get("_static_registered"):
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    url_path=PANEL_URL_ROOT,
                    path=PANEL_FS_ROOT,
                    cache_headers=False,
                )
            ]
        )
        hass.data[DOMAIN]["_static_registered"] = True

    # --- Entry-bound resources ---

    # Initialize store
    store = HaAlertsStore(hass)
    await store.async_load()

    # Initialize manager
    manager = HaAlertsManager(hass, store, config_entry=entry)
    hass.data[DOMAIN]["manager"] = manager

    # Forward platforms → binary_sensor.py creates AlertEntity
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (entry-bound – removed on unload)
    _register_services(hass, manager)

    # Load entrypoint wrapper as an extra JS module.
    # It defines <ha-panel-ha-alerts>, which the built-in panel renders.
    # Note: Do NOT include query params (e.g., ?v=...) as they break relative imports in ES modules.
    # Version is embedded as a comment in the JS files instead.
    entry_url = f"{PANEL_URL_ROOT}/entrypoint.js"
    frontend.add_extra_js_url(hass, entry_url)
    hass.data[DOMAIN]["panel_entry_url"] = entry_url

    # Register as built-in panel (HACS-style, stays mounted across WS reconnect)
    frontend.async_register_built_in_panel(
        hass,
        component_name=DOMAIN.replace("_", "-"),  # -> <ha-panel-ha-alerts>
        sidebar_title="Alert Manager",
        sidebar_icon="mdi:alert-box-outline",
        frontend_url_path=DOMAIN,  # -> /ha_alerts
        require_admin=True,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload HA Alerts config entry."""

    # Remove panel
    frontend.async_remove_panel(hass, DOMAIN)

    entry_url = hass.data.get(DOMAIN, {}).get("panel_entry_url")
    if entry_url:
        frontend.remove_extra_js_url(hass, entry_url)

    # Unload platforms (removes AlertEntity instances)
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove old services registered in async_setup_entry
    for service in (SERVICE_ADD, SERVICE_REMOVE, SERVICE_UPDATE, SERVICE_ENABLE, SERVICE_DISABLE):
        hass.services.async_remove(DOMAIN, service)

    # Keep domain-level flags (_ws_registered, _static_registered); drop entry-bound runtime.
    hass.data.get(DOMAIN, {}).pop("manager", None)
    hass.data.get(DOMAIN, {}).pop("panel_entry_url", None)
    return True


@callback
def _register_services(
    hass: HomeAssistant,
    manager: HaAlertsManager,
) -> None:
    """Register ha_alerts services."""

@callback
def _register_services(
    hass: HomeAssistant,
    manager: HaAlertsManager,
) -> None:
    """Register ha_alerts services."""

    @callback
    async def handle_add(call: ServiceCall) -> None:
        """Handle add service - create a new alert."""
        try:
            service_data = {
                "name": call.data.get("name"),
                "condition": call.data.get("condition"),
                "entity_id": call.data.get("entity_id"),
                "description": call.data.get("description"),
                "category_id": call.data.get("category_id"),
                "category_name": call.data.get("category_name"),
                "notification": call.data.get("notification"),
            }
            await manager.async_create_alert(service_data)
        except Exception:
            _LOGGER.exception("Error in handle_add service")

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD,
        handle_add,
        schema=vol.Schema({
            vol.Required("name"): str,
            vol.Required("condition"): str,
            vol.Optional("entity_id"): str,
            vol.Optional("description"): str,
            vol.Optional("category_id"): str,
            vol.Optional("category_name"): str,
            vol.Optional("notification"): dict,
        }),
    )

    @callback
    async def handle_remove(call: ServiceCall) -> None:
        """Handle remove service - delete an alert by ID."""
        try:
            alert_id = call.data.get("id")
            if alert_id:
                await manager.async_delete_alert(alert_id)
        except Exception:
            _LOGGER.exception("Error in handle_remove service")

    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE,
        handle_remove,
        schema=vol.Schema({
            vol.Required("id"): str,
        }),
    )

    @callback
    async def handle_update(call: ServiceCall) -> None:
        """Handle update service - modify an existing alert."""
        try:
            alert_id = call.data.get("id")
            if not alert_id:
                raise ValueError("Alert ID is required")

            update_data = {}
            if "name" in call.data:
                update_data["name"] = call.data["name"]
            if "condition" in call.data:
                update_data["condition"] = call.data["condition"]
            if "entity_id" in call.data:
                update_data["entity_id"] = call.data["entity_id"]
            if "description" in call.data:
                update_data["description"] = call.data["description"]
            if "category_id" in call.data:
                update_data["category_id"] = call.data["category_id"]
            if "category_name" in call.data:
                update_data["category_name"] = call.data["category_name"]
            if "notification" in call.data:
                update_data["notification"] = call.data["notification"]

            await manager.async_update_alert(alert_id, update_data)
        except Exception:
            _LOGGER.exception("Error in handle_update service")

    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE,
        handle_update,
        schema=vol.Schema({
            vol.Required("id"): str,
            vol.Optional("name"): str,
            vol.Optional("condition"): str,
            vol.Optional("entity_id"): str,
            vol.Optional("description"): str,
            vol.Optional("category_id"): str,
            vol.Optional("category_name"): str,
            vol.Optional("notification"): dict,
        }),
    )

    @callback
    async def handle_enable(call: ServiceCall) -> None:
        """Handle enable service - enable an alert by ID."""
        try:
            alert_id = call.data.get("id")
            if alert_id:
                existing = manager.store.get_alert(alert_id)
                if existing:
                    existing["enabled"] = True
                    manager.store.set_alert(alert_id, existing)
                    await manager.store.async_save()
                    entity = manager.get_alert_entity(alert_id)
                    if entity:
                        entity.enable()
        except Exception:
            _LOGGER.exception("Error in handle_enable service")

    hass.services.async_register(
        DOMAIN,
        SERVICE_ENABLE,
        handle_enable,
        schema=vol.Schema({
            vol.Required("id"): str,
        }),
    )

    @callback
    async def handle_disable(call: ServiceCall) -> None:
        """Handle disable service - disable an alert by ID."""
        try:
            alert_id = call.data.get("id")
            if alert_id:
                existing = manager.store.get_alert(alert_id)
                if existing:
                    existing["enabled"] = False
                    manager.store.set_alert(alert_id, existing)
                    await manager.store.async_save()
                    entity = manager.get_alert_entity(alert_id)
                    if entity:
                        entity.disable()
        except Exception:
            _LOGGER.exception("Error in handle_disable service")

    hass.services.async_register(
        DOMAIN,
        SERVICE_DISABLE,
        handle_disable,
        schema=vol.Schema({
            vol.Required("id"): str,
        }),
    )
