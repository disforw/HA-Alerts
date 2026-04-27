"""Switch platform for HA Alerts — one entity per config entry."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_REPEAT,
    CONF_STATE,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.template import Template
from homeassistant.util import slugify

from . import Alert, _build_entity_id_from_entry, update_listener
from .const import (
    CONF_ALERT_MESSAGE,
    CONF_DATA,
    CONF_DONE_MESSAGE,
    CONF_NOTIFIERS,
    CONF_SKIP_FIRST,
    CONF_TITLE,
    DEFAULT_REPEAT,
    DEFAULT_SKIP_FIRST,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up an HA Alert entity from a config entry."""
    name: str = entry.options.get(CONF_NAME, "")
    watched_entity_id: str = entry.options.get(CONF_ENTITY_ID, "")
    alert_state: str = entry.options.get(CONF_STATE, STATE_ON)

    repeat_raw = entry.options.get(CONF_REPEAT, DEFAULT_REPEAT)
    if isinstance(repeat_raw, list):
        repeat_float = [float(r) for r in repeat_raw]
    else:
        repeat_float = [float(repeat_raw)]

    skip_first: bool = entry.options.get(CONF_SKIP_FIRST, DEFAULT_SKIP_FIRST)
    notifiers: list[str] = entry.options.get(CONF_NOTIFIERS, [])
    data: dict[str, Any] = entry.options.get(CONF_DATA, {})

    message_raw: str | None = entry.options.get(CONF_ALERT_MESSAGE)
    done_message_raw: str | None = entry.options.get(CONF_DONE_MESSAGE)
    title_raw: str | None = entry.options.get(CONF_TITLE)

    if not name or not watched_entity_id:
        _LOGGER.error(
            "ha_alerts entry %s is missing required options (name=%r, entity_id=%r). "
            "Please delete and re-add the alert via the UI.",
            entry.entry_id,
            name,
            watched_entity_id,
        )
        return

    entity = Alert(
        slugify(name),
        name,
        watched_entity_id,
        alert_state,
        repeat_float,
        skip_first,
        Template(message_raw, hass) if message_raw else None,
        Template(done_message_raw, hass) if done_message_raw else None,
        notifiers,
        Template(title_raw, hass) if title_raw else None,
        data,
    )

    # Store reference so the update service can reach this entity by entry_id.
    hass.data[DOMAIN][entry.entry_id] = entity

    async_add_entities([entity])

    # Wire up the options-flow update listener (full reload on UI edits).
    entry.async_on_unload(entry.add_update_listener(update_listener))
