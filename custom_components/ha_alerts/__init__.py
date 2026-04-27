"""Support for repeating alerts when conditions are met."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any, final

import voluptuous as vol

from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_MESSAGE,
    ATTR_TITLE,
    DOMAIN as DOMAIN_NOTIFY,
)
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_REPEAT,
    CONF_STATE,
    Platform,
    STATE_ON,
)
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers.entity import ToggleEntity
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify
from homeassistant.util.dt import now

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

ALERT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Required(CONF_STATE, default=STATE_ON): cv.string,
        vol.Required(CONF_REPEAT): vol.All(
            cv.ensure_list,
            [vol.Coerce(float)],
            [vol.Range(min=0.016)],
        ),
        vol.Required(CONF_SKIP_FIRST, default=DEFAULT_SKIP_FIRST): cv.boolean,
        vol.Optional(CONF_ALERT_MESSAGE): cv.template,
        vol.Optional(CONF_DONE_MESSAGE): cv.template,
        vol.Optional(CONF_TITLE): cv.template,
        vol.Optional(CONF_DATA): dict,
        vol.Required(CONF_NOTIFIERS): vol.All(cv.ensure_list, [cv.string]),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: cv.schema_with_slug_keys(ALERT_SCHEMA)}, extra=vol.ALLOW_EXTRA
)

CREATE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_STATE, default=STATE_ON): cv.string,
        vol.Required(CONF_REPEAT): vol.Any(vol.All(cv.ensure_list, [vol.Coerce(float)]), vol.Coerce(float)),
        vol.Optional(CONF_SKIP_FIRST, default=DEFAULT_SKIP_FIRST): cv.boolean,
        vol.Required(CONF_NOTIFIERS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_ALERT_MESSAGE): cv.string,
        vol.Optional(CONF_DONE_MESSAGE): cv.string,
        vol.Optional(CONF_TITLE): cv.string,
        vol.Optional(CONF_DATA): dict,
    }
)

UPDATE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_STATE): cv.string,
        vol.Optional(CONF_REPEAT): vol.Any(vol.All(cv.ensure_list, [vol.Coerce(float)]), vol.Coerce(float)),
        vol.Optional(CONF_SKIP_FIRST): cv.boolean,
        vol.Optional(CONF_NOTIFIERS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_ALERT_MESSAGE): cv.string,
        vol.Optional(CONF_DONE_MESSAGE): cv.string,
        vol.Optional(CONF_TITLE): cv.string,
        vol.Optional(CONF_DATA): dict,
    }
)

DELETE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
    }
)


def is_on(hass: HomeAssistant, entity_id: str) -> bool:
    """Return if the alert is armed."""
    return hass.states.is_state(entity_id, STATE_ON)


def _build_entity_id_from_entry(entry: ConfigEntry) -> str:
    """Build the expected entity_id for a config entry."""
    return f"{DOMAIN}.{slugify(entry.options.get(CONF_NAME, ''))}"


async def async_register_management_services(hass: HomeAssistant) -> None:
    """Register create/update/delete services (once only)."""
    if hass.services.has_service(DOMAIN, "create"):
        return

    async def async_handle_create(service_call: ServiceCall) -> None:
        """Create a new HA Alert via service call (SOURCE_IMPORT path)."""
        options: dict[str, Any] = {
            CONF_NAME: service_call.data[CONF_NAME],
            CONF_ENTITY_ID: service_call.data[CONF_ENTITY_ID],
            CONF_STATE: service_call.data.get(CONF_STATE, STATE_ON),
            CONF_REPEAT: service_call.data[CONF_REPEAT],
            CONF_SKIP_FIRST: service_call.data.get(CONF_SKIP_FIRST, DEFAULT_SKIP_FIRST),
            CONF_NOTIFIERS: service_call.data[CONF_NOTIFIERS],
        }
        for key in (CONF_ALERT_MESSAGE, CONF_DONE_MESSAGE, CONF_TITLE, CONF_DATA):
            if key in service_call.data:
                options[key] = service_call.data[key]

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data=options,
        )
        if result.get("type") == "abort":
            _LOGGER.warning(
                "ha_alerts.create: flow aborted — reason: %s",
                result.get("reason"),
            )
        elif result.get("type") != "create_entry":
            _LOGGER.error(
                "ha_alerts.create: unexpected flow result type %s", result.get("type")
            )

    async def async_handle_delete(service_call: ServiceCall) -> None:
        """Delete an HA Alert by entity_id."""
        target_entity_id = service_call.data[CONF_ENTITY_ID]
        for entry in hass.config_entries.async_entries(DOMAIN):
            if _build_entity_id_from_entry(entry) == target_entity_id:
                await hass.config_entries.async_remove(entry.entry_id)
                return
        _LOGGER.warning("ha_alerts.delete: entity %s not found", target_entity_id)

    async def async_handle_update(service_call: ServiceCall) -> None:
        """Update an existing HA Alert's options in-place (Issue #5 fix)."""
        target_entity_id = service_call.data[CONF_ENTITY_ID]
        for entry in hass.config_entries.async_entries(DOMAIN):
            if _build_entity_id_from_entry(entry) == target_entity_id:
                new_options = dict(entry.options)
                for key in (
                    CONF_STATE,
                    CONF_REPEAT,
                    CONF_SKIP_FIRST,
                    CONF_NOTIFIERS,
                    CONF_ALERT_MESSAGE,
                    CONF_DONE_MESSAGE,
                    CONF_TITLE,
                    CONF_DATA,
                ):
                    if key in service_call.data:
                        new_options[key] = service_call.data[key]

                hass.config_entries.async_update_entry(entry, options=new_options)

                entity: Alert | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
                if entity is not None:
                    entity.apply_options(new_options, hass)
                    entity.async_write_ha_state()
                return
        _LOGGER.warning("ha_alerts.update: entity %s not found", target_entity_id)

    hass.services.async_register(
        DOMAIN, "create", async_handle_create, schema=CREATE_SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "update", async_handle_update, schema=UPDATE_SERVICE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "delete", async_handle_delete, schema=DELETE_SERVICE_SCHEMA
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the HA Alerts component (YAML path)."""
    await async_register_management_services(hass)

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Alerts from a config entry — forwards to the switch platform."""
    await async_register_management_services(hass)

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    await hass.config_entries.async_forward_entry_setups(entry, (Platform.SWITCH,))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, (Platform.SWITCH,))


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates from the UI options flow (full reload)."""
    await hass.config_entries.async_reload(entry.entry_id)


class Alert(ToggleEntity):
    """Representation of an HA Alert.

    Toggle semantics:
      on  = armed   — watching the entity, will fire and send notifications
      off = disarmed — silent, not watching, no notifications

    Disarming while firing is a hard stop (Option A): cancels all pending
    notifications and clears firing state. No done message is sent.
    """

    _attr_should_poll = False

    def __init__(
        self,
        entity_id: str,
        name: str,
        watched_entity_id: str,
        state: str,
        repeat: list[float],
        skip_first: bool,
        message_template: Template | None,
        done_message_template: Template | None,
        notifiers: list[str],
        title_template: Template | None,
        data: dict[Any, Any],
    ) -> None:
        """Initialize the alert."""
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{entity_id}"
        self.entity_id = f"{DOMAIN}.{entity_id}"

        self._alert_state = state
        self._skip_first = skip_first
        self._data = data

        self._message_template = message_template
        self._done_message_template = done_message_template
        self._title_template = title_template

        self._notifiers = notifiers

        if not isinstance(repeat, (list, tuple)):
            repeat = [repeat]
        self._delay = [timedelta(minutes=float(val)) for val in repeat if val is not None]
        self._next_delay = 0

        self._armed = True   # armed by default on creation
        self._firing = False
        self._cancel: Callable[[], None] | None = None
        self._send_done_message = False
        self._last_triggered: datetime | None = None

        self._watched_entity_id = watched_entity_id
        self._unsub_state_change: Callable[[], None] | None = None

    # ------------------------------------------------------------------
    # HA lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Register state-change listener once entity is part of HA."""
        self._start_watching()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel all listeners when the entity is being removed."""
        self._stop_watching()
        if self._cancel is not None:
            self._cancel()
            self._cancel = None

    def _start_watching(self) -> None:
        """Subscribe to state changes on the watched entity."""
        if self._unsub_state_change is not None:
            return
        self._unsub_state_change = async_track_state_change_event(
            self.hass, [self._watched_entity_id], self.watched_entity_change
        )

    def _stop_watching(self) -> None:
        """Unsubscribe from state changes."""
        if self._unsub_state_change is not None:
            self._unsub_state_change()
            self._unsub_state_change = None

    # ------------------------------------------------------------------
    # Options hot-update (Issue #5 fix)
    # ------------------------------------------------------------------

    def apply_options(self, options: dict[str, Any], hass: HomeAssistant) -> None:
        """Apply updated config-entry options to this live entity in-place."""
        self._alert_state = options.get(CONF_STATE, self._alert_state)
        self._skip_first = options.get(CONF_SKIP_FIRST, self._skip_first)
        self._notifiers = options.get(CONF_NOTIFIERS, self._notifiers)
        self._data = options.get(CONF_DATA, self._data)

        repeat_raw = options.get(CONF_REPEAT)
        if repeat_raw is not None:
            if isinstance(repeat_raw, list):
                self._delay = [timedelta(minutes=float(r)) for r in repeat_raw]
            else:
                self._delay = [timedelta(minutes=float(repeat_raw))]
            self._next_delay = min(self._next_delay, len(self._delay) - 1)

        msg_raw = options.get(CONF_ALERT_MESSAGE)
        self._message_template = Template(msg_raw, hass) if msg_raw else None

        done_raw = options.get(CONF_DONE_MESSAGE)
        self._done_message_template = Template(done_raw, hass) if done_raw else None

        title_raw = options.get(CONF_TITLE)
        self._title_template = Template(title_raw, hass) if title_raw else None

    # ------------------------------------------------------------------
    # State & attributes
    # ------------------------------------------------------------------

    @property
    def is_on(self) -> bool:
        """Return True when the alert is armed."""
        return self._armed

    @property
    def icon(self) -> str:
        """Return icon based on armed/firing state."""
        if not self._armed:
            return "mdi:bell-off"
        if self._firing:
            return "mdi:bell-alert"
        return "mdi:bell"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "ha_alerts": True,
            "firing": self._firing,
            "last_triggered": self._last_triggered.isoformat() if self._last_triggered else None,
        }

    # ------------------------------------------------------------------
    # Arm / disarm (turn_on / turn_off)
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Arm the alert — start watching and check current state."""
        if self._armed:
            return
        _LOGGER.debug("Arming alert: %s", self._attr_name)
        self._armed = True
        self._start_watching()

        # Check immediately — if condition already met, begin alerting.
        current = self.hass.states.get(self._watched_entity_id)
        if current is not None and current.state == self._alert_state and not self._firing:
            await self.begin_alerting()

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disarm the alert — hard stop, cancel everything."""
        if not self._armed:
            return
        _LOGGER.debug("Disarming alert: %s", self._attr_name)
        self._armed = False
        self._stop_watching()

        # Hard stop — cancel pending notifications, clear firing state.
        if self._cancel is not None:
            self._cancel()
            self._cancel = None
        self._firing = False
        self._send_done_message = False
        self._next_delay = 0

        self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Alert logic
    # ------------------------------------------------------------------

    async def watched_entity_change(self, event: Event) -> None:
        """Determine if the alert should start or stop."""
        if not self._armed:
            return
        if (to_state := event.data.get("new_state")) is None:
            return
        _LOGGER.debug("Watched entity (%s) has changed", event.data.get("entity_id"))
        if to_state.state == self._alert_state and not self._firing:
            await self.begin_alerting()
        if to_state.state != self._alert_state and self._firing:
            await self.end_alerting()

    async def begin_alerting(self) -> None:
        """Begin the alert procedures."""
        _LOGGER.debug("Beginning Alert: %s", self._attr_name)
        self._firing = True
        self._next_delay = 0
        self._last_triggered = now()

        if not self._skip_first:
            await self._notify()
        else:
            await self._schedule_notify()

        self.async_write_ha_state()

    async def end_alerting(self) -> None:
        """End the alert procedures."""
        _LOGGER.debug("Ending Alert: %s", self._attr_name)
        if self._cancel is not None:
            self._cancel()
            self._cancel = None

        self._firing = False
        if self._send_done_message:
            await self._notify_done_message()
        self.async_write_ha_state()

    async def _schedule_notify(self) -> None:
        """Schedule a notification."""
        delay = self._delay[self._next_delay]
        next_msg = now() + delay
        self._cancel = async_track_point_in_time(self.hass, self._notify, next_msg)
        self._next_delay = min(self._next_delay + 1, len(self._delay) - 1)

    async def _notify(self, *args: Any) -> None:
        """Send the alert notification."""
        if not self._firing or not self._armed:
            return

        _LOGGER.info("Alerting: %s", self._attr_name)
        self._send_done_message = True

        if self._message_template is not None:
            message = self._message_template.async_render(parse_result=False)
        else:
            message = self._attr_name

        await self._send_notification_message(message)
        await self._schedule_notify()

    async def _notify_done_message(self) -> None:
        """Send notification of complete alert."""
        _LOGGER.info("Sending done message for alert: %s", self._attr_name)
        self._send_done_message = False

        if self._done_message_template is None:
            return

        message = self._done_message_template.async_render(parse_result=False)
        await self._send_notification_message(message)

    async def _send_notification_message(self, message: Any) -> None:
        """Send a notification message to all configured notifiers."""
        msg_payload = {ATTR_MESSAGE: message}

        if self._title_template is not None:
            title = self._title_template.async_render(parse_result=False)
            msg_payload[ATTR_TITLE] = title
        if self._data:
            msg_payload[ATTR_DATA] = self._data

        _LOGGER.debug(msg_payload)

        for target in self._notifiers:
            await self.hass.services.async_call(
                DOMAIN_NOTIFY, target, msg_payload
            )
