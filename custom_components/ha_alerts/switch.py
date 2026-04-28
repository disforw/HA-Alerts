"""Switch platform for HA Alerts — one entity per config entry."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_REPEAT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.template import Template
from homeassistant.util import slugify

from . import Alert, update_listener
from .const import (
    CONF_ALERT_MESSAGE,
    CONF_DATA,
    CONF_DONE_MESSAGE,
    CONF_NOTIFIERS,
    CONF_SKIP_FIRST,
    CONF_TITLE,
    CONF_TRIGGER_TEMPLATE,
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
    trigger_template_raw: str = entry.options.get(CONF_TRIGGER_TEMPLATE, "")

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

    if not name or not trigger_template_raw:
        _LOGGER.error(
            "ha_alerts entry %s is missing required options (name=%r, trigger_template=%r). "
            "Please delete and re-add the alert via the UI.",
            entry.entry_id,
            name,
            trigger_template_raw,
        )
        return

    entity = Alert(
        slugify(name),
        name,
        Template(trigger_template_raw, hass),
        repeat_float,
        skip_first,
        Template(message_raw, hass) if message_raw else None,
        Template(done_message_raw, hass) if done_message_raw else None,
        notifiers,
        Template(title_raw, hass) if title_raw else None,
        data,
    )

    hass.data[DOMAIN][entry.entry_id] = entity
    async_add_entities([entity])
    entry.async_on_unload(entry.add_update_listener(update_listener))
