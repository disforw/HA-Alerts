"""Support for repeating alerts when conditions are met."""
from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any, final

import voluptuous as vol

from homeassistant.components.notify import (
    ATTR_DATA,
    ATTR_MESSAGE,
    ATTR_TITLE,
    DOMAIN as DOMAIN_NOTIFY,
)
import homeassistant.config_entries as config_entries_module
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_REPEAT,
    CONF_STATE,
    SERVICE_TOGGLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_IDLE,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers import service
from homeassistant.helpers.entity import ToggleEntity
from homeassistant.helpers.entity_component import EntityComponent
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
    CONF_CAN_ACK,
    CONF_DATA,
    CONF_DONE_MESSAGE,
    CONF_NOTIFIERS,
    CONF_SKIP_FIRST,
    CONF_TITLE,
    DEFAULT_CAN_ACK,
    DEFAULT_SKIP_FIRST,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=0)

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
        vol.Required(CONF_CAN_ACK, default=DEFAULT_CAN_ACK): cv.boolean,
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

ALERT_SERVICE_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids})

CREATE_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_STATE, default=STATE_ON): cv.string,
        vol.Required(CONF_REPEAT): vol.All(cv.ensure_list, [vol.Coerce(str)]),
        vol.Optional(CONF_SKIP_FIRST, default=DEFAULT_SKIP_FIRST): cv.boolean,
        vol.Optional(CONF_CAN_ACK, default=DEFAULT_CAN_ACK): cv.boolean,
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
        vol.Optional(CONF_REPEAT): vol.All(cv.ensure_list, [vol.Coerce(str)]),
        vol.Optional(CONF_SKIP_FIRST): cv.boolean,
        vol.Optional(CONF_CAN_ACK): cv.boolean,
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
    """Return if the alert is firing and not acknowledged."""
    return hass.states.is_state(entity_id, STATE_ON)


def _build_entity_id_from_entry(entry: ConfigEntry) -> str:
    """Build the expected entity_id for a config entry."""
    return f"{DOMAIN}.{slugify(entry.options.get(CONF_NAME, ''))}"


async def async_register_management_services(hass: HomeAssistant) -> None:
    """Register create/update/delete services (once only)."""
    if hass.services.has_service(DOMAIN, "create"):
        return

    async def async_handle_create(service_call: ServiceCall) -> None:
        """Create a new HA Alert via service call."""
        options: dict[str, Any] = {
            CONF_NAME: service_call.data[CONF_NAME],
            CONF_ENTITY_ID: service_call.data[CONF_ENTITY_ID],
            CONF_STATE: service_call.data.get(CONF_STATE, STATE_ON),
            # Keep as list for internal use; will be converted to single float when
            # passed to the flow step (NumberSelector expects a single number).
            CONF_REPEAT: service_call.data[CONF_REPEAT],
            CONF_SKIP_FIRST: service_call.data.get(CONF_SKIP_FIRST, DEFAULT_SKIP_FIRST),
            CONF_CAN_ACK: service_call.data.get(CONF_CAN_ACK, DEFAULT_CAN_ACK),
            CONF_NOTIFIERS: service_call.data[CONF_NOTIFIERS],
        }
        for key in (CONF_ALERT_MESSAGE, CONF_DONE_MESSAGE, CONF_TITLE, CONF_DATA):
            if key in service_call.data:
                options[key] = service_call.data[key]

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries_module.SOURCE_USER},
        )
        flow_id = result["flow_id"]

        # Step 1: user — name + entity_id
        await hass.config_entries.flow.async_configure(
            flow_id,
            user_input={
                CONF_NAME: options[CONF_NAME],
                CONF_ENTITY_ID: options[CONF_ENTITY_ID],
            },
        )

        # Step 2: options — state, repeat, can_acknowledge, skip_first
        # CONF_REPEAT must be a single number to match the NumberSelector schema.
        # The service call receives it as a list; take the first element.
        repeat_val = options[CONF_REPEAT]
        if isinstance(repeat_val, list):
            repeat_val = float(repeat_val[0])
        else:
            repeat_val = float(repeat_val)
        await hass.config_entries.flow.async_configure(
            flow_id,
            user_input={
                CONF_STATE: options[CONF_STATE],
                CONF_REPEAT: repeat_val,
                CONF_CAN_ACK: options[CONF_CAN_ACK],
                CONF_SKIP_FIRST: options[CONF_SKIP_FIRST],
            },
        )

        # Step 3: notifier — notifiers + optional message fields
        notifier_input: dict[str, Any] = {CONF_NOTIFIERS: options[CONF_NOTIFIERS]}
        for key in (CONF_ALERT_MESSAGE, CONF_DONE_MESSAGE, CONF_TITLE, CONF_DATA):
            if key in options:
                notifier_input[key] = options[key]
        await hass.config_entries.flow.async_configure(
            flow_id,
            user_input=notifier_input,
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
        """Update an existing HA Alert's options."""
        target_entity_id = service_call.data[CONF_ENTITY_ID]
        for entry in hass.config_entries.async_entries(DOMAIN):
            if _build_entity_id_from_entry(entry) == target_entity_id:
                new_options = dict(entry.options)
                for key in (
                    CONF_STATE,
                    CONF_REPEAT,
                    CONF_SKIP_FIRST,
                    CONF_CAN_ACK,
                    CONF_NOTIFIERS,
                    CONF_ALERT_MESSAGE,
                    CONF_DONE_MESSAGE,
                    CONF_TITLE,
                    CONF_DATA,
                ):
                    if key in service_call.data:
                        val = service_call.data[key]
                        if key == CONF_REPEAT:
                            # CONF_REPEAT is stored as a single float (matching what
                            # the NumberSelector UI produces). Convert list→first item.
                            repeat_list = val if isinstance(val, list) else [val]
                            val = float(repeat_list[0])
                        new_options[key] = val
                hass.config_entries.async_update_entry(entry, options=new_options)
                await hass.config_entries.async_reload(entry.entry_id)
                return
        _LOGGER.warning("ha_alerts.update: entity %s not found", target_entity_id)

    hass.services.async_register(
        DOMAIN,
        "create",
        async_handle_create,
        schema=CREATE_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "update",
        async_handle_update,
        schema=UPDATE_SERVICE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "delete",
        async_handle_delete,
        schema=DELETE_SERVICE_SCHEMA,
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the HA Alerts component."""
    # Always register management services at setup time so they are available
    # even before any config entries exist.
    await async_register_management_services(hass)

    component = EntityComponent[Alert](_LOGGER, DOMAIN, hass)
    hass.data[DOMAIN] = component

    if DOMAIN not in config:
        return True

    entities: list[Alert] = []

    for object_id, cfg in config[DOMAIN].items():
        if not cfg:
            cfg = {}

        name = cfg[CONF_NAME]
        watched_entity_id = cfg[CONF_ENTITY_ID]
        alert_state = cfg[CONF_STATE]
        repeat = cfg[CONF_REPEAT]
        skip_first = cfg[CONF_SKIP_FIRST]
        message_template = cfg.get(CONF_ALERT_MESSAGE)
        done_message_template = cfg.get(CONF_DONE_MESSAGE)
        notifiers = cfg[CONF_NOTIFIERS]
        can_ack = cfg[CONF_CAN_ACK]
        title_template = cfg.get(CONF_TITLE)
        data = cfg.get(CONF_DATA)

        entities.append(
            Alert(
                hass,
                object_id,
                name,
                watched_entity_id,
                alert_state,
                repeat,
                skip_first,
                message_template,
                done_message_template,
                notifiers,
                can_ack,
                title_template,
                data,
            )
        )

    if entities:
        await component.async_add_entities(entities)
        await _async_setup_alert_services(hass, component)

    return True


async def _async_setup_alert_services(
    hass: HomeAssistant, component: EntityComponent[Alert]
) -> None:
    """Set up turn_on/turn_off/toggle services for alert entities."""

    async def async_handle_alert_service(service_call: ServiceCall) -> None:
        """Handle calls to alert services."""
        alert_ids = await service.async_extract_entity_ids(hass, service_call)

        for alert in component.entities:
            if alert.entity_id not in alert_ids:
                continue
            alert.async_set_context(service_call.context)
            if service_call.service == SERVICE_TURN_ON:
                await alert.async_turn_on()
            elif service_call.service == SERVICE_TOGGLE:
                await alert.async_toggle()
            else:
                await alert.async_turn_off()

    if not hass.services.has_service(DOMAIN, SERVICE_TURN_OFF):
        hass.services.async_register(
            DOMAIN,
            SERVICE_TURN_OFF,
            async_handle_alert_service,
            schema=ALERT_SERVICE_SCHEMA,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_TURN_ON,
            async_handle_alert_service,
            schema=ALERT_SERVICE_SCHEMA,
        )
        hass.services.async_register(
            DOMAIN,
            SERVICE_TOGGLE,
            async_handle_alert_service,
            schema=ALERT_SERVICE_SCHEMA,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the HA Alerts component from a config entry."""
    name: str = entry.options[CONF_NAME]
    watched_entity_id: str = entry.options[CONF_ENTITY_ID]
    alert_state: str = entry.options[CONF_STATE]
    # CONF_REPEAT is stored as a single number (float) by the NumberSelector in the
    # config flow UI. Wrap it in a list so Alert receives list[float] as expected.
    repeat_raw = entry.options[CONF_REPEAT]
    if isinstance(repeat_raw, list):
        repeat_float = [float(r) for r in repeat_raw]
    else:
        repeat_float = [float(repeat_raw)]
    skip_first: bool = entry.options[CONF_SKIP_FIRST]
    message_template: str | None = entry.options.get(CONF_ALERT_MESSAGE)
    done_message_template: str | None = entry.options.get(CONF_DONE_MESSAGE)
    notifiers: list[str] = entry.options[CONF_NOTIFIERS]
    can_ack: bool = entry.options[CONF_CAN_ACK]
    title_template: str | None = entry.options.get(CONF_TITLE)
    data: dict[Any, Any] = entry.options.get(CONF_DATA, {})

    entity = Alert(
        hass,
        slugify(name),
        name,
        watched_entity_id,
        alert_state,
        repeat_float,
        skip_first,
        Template(message_template, hass) if message_template else None,
        Template(done_message_template, hass) if done_message_template else None,
        notifiers,
        can_ack,
        Template(title_template, hass) if title_template else None,
        data,
    )

    # Add the entity to the component so it appears in the entity registry.
    component: EntityComponent[Alert] = hass.data.get(DOMAIN)
    if component is None:
        # Fallback: create component if async_setup wasn't called (e.g., during tests).
        component = EntityComponent[Alert](_LOGGER, DOMAIN, hass)
        hass.data[DOMAIN] = component

    await component.async_add_entities([entity])
    await _async_setup_alert_services(hass, component)

    entry.async_on_unload(entry.add_update_listener(update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an HA Alerts entry."""
    component: EntityComponent[Alert] | None = hass.data.get(DOMAIN)
    if component is None:
        return True

    # Remove the entity for this entry from the component.
    entity_id = f"{DOMAIN}.{slugify(entry.options.get(CONF_NAME, ''))}"
    for entity in list(component.entities):
        if entity.entity_id == entity_id:
            await component.async_remove_entity(entity_id)
            break

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


class Alert(ToggleEntity):
    """Representation of an alert."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        entity_id: str,
        name: str,
        watched_entity_id: str,
        state: str,
        repeat: list[float],
        skip_first: bool,
        message_template: Template | None,
        done_message_template: Template | None,
        notifiers: list[str],
        can_ack: bool,
        title_template: Template | None,
        data: dict[Any, Any],
    ) -> None:
        """Initialize the alert."""
        self.hass = hass
        self._attr_name = name
        self._alert_state = state
        self._skip_first = skip_first
        self._data = data

        self._message_template = message_template
        self._done_message_template = done_message_template
        self._title_template = title_template

        self._notifiers = notifiers
        self._can_ack = can_ack

        self._delay = [timedelta(minutes=val) for val in repeat]
        self._next_delay = 0

        self._firing = False
        self._ack = False
        self._cancel: Callable[[], None] | None = None
        self._send_done_message = False
        self._context = None
        self.entity_id = f"{DOMAIN}.{entity_id}"
        self._attr_unique_id = f"{DOMAIN}_{entity_id}"

        async_track_state_change_event(
            hass, [watched_entity_id], self.watched_entity_change
        )

    @final
    @property
    def state(self) -> str:
        """Return the alert status."""
        if self._firing:
            if self._ack:
                return STATE_OFF
            return STATE_ON
        return STATE_IDLE

    async def watched_entity_change(self, event: Event) -> None:
        """Determine if the alert should start or stop."""
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
        self._ack = False
        self._firing = True
        self._next_delay = 0

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

        self._ack = False
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
        if not self._firing:
            return

        if not self._ack:
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
        _LOGGER.info("Alerting: %s", self._done_message_template)
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
                DOMAIN_NOTIFY, target, msg_payload, context=self._context
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Async Unacknowledge alert."""
        _LOGGER.debug("Reset Alert: %s", self._attr_name)
        self._ack = False
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Async Acknowledge alert."""
        _LOGGER.debug("Acknowledged Alert: %s", self._attr_name)
        self._ack = True
        self.async_write_ha_state()

    async def async_toggle(self, **kwargs: Any) -> None:
        """Async toggle alert."""
        if self._ack:
            return await self.async_turn_on()
        return await self.async_turn_off()
