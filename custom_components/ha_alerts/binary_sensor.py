"""Binary sensor platform for HA Alerts – alert entities."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import AlertEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HA Alerts alert entities from a config entry."""
    manager = hass.data[DOMAIN]["manager"]
    store = manager.store

    manager.set_add_entities_callback(async_add_entities)

    alert_entities = []
    for alert_uid, alert_def in store.alerts.items():
        try:
            await manager.async_create_registry_entry(
                alert_uid, name=alert_def.get("name", "Alert")
            )
        except Exception as exc:
            _LOGGER.warning(
                "Failed to ensure registry entry for %s: %s", alert_uid, exc
            )
        entity = AlertEntity(
            hass=hass,
            uid=alert_uid,
            name=alert_def["name"],
            condition_config=alert_def["condition"],
            manager=manager,
            notification_config=alert_def.get("notification"),
            description=alert_def.get("description", ""),
            enabled=alert_def.get("enabled", True),
        )
        alert_entities.append(entity)

    if alert_entities:
        async_add_entities(alert_entities)
