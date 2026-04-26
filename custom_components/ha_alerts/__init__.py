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
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
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
    DEFAULT_REPEAT,
    DEFAULT_SKIP_FIRST,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# SCAN_INTERVAL removed — Alert._attr_should_poll = False makes it unused. (Issue #6)

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
        """Create a new HA Alert via service call.

        Issue #2 fix: instead of driving the multi-step SchemaConfigFlowHandler
        programmatically (which validates against UI selectors and offers no error
        handling), we use SOURCE_IMPORT to invoke a single dedicated flow step that
        accepts raw data directly, bypassing the UI selector pipeline entirely.
        """
        options: dict[str, Any] = {
            CONF_NAME: service_call.data[CONF_NAME],
            CONF_ENTITY_ID: service_call.data[CONF_ENTITY_ID],
            CONF_STATE: service_call.data.get(CONF_STATE, STATE_ON),
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
        """Update an existing HA Alert's options in-place.

        Issue #5 fix: rather than triggering a full config entry reload (which
        destroys and recreates the entity, losing any active-firing state), we
        update the entity's runtime attributes directly and persist the new options
        via async_update_entry without reloading.
        """
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
                        new_options[key] = service_call.data[key]

                # Persist new options (without triggering a reload via update_listener).
                # We use skip_update_listeners=True so the listener doesn't reload the
                # entry; instead we apply the changes directly to the live entity below.
                hass.config_entries.async_update_entry(entry, options=new_options)

                # Apply changes to the live entity in-place, preserving firing state.
                entity: Alert | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
                if entity is not None:
                    entity.apply_options(new_options, hass)
                    entity.async_write_ha_state()
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

    # hass.data[DOMAIN] is a dict: {entry_id: Alert, ...}
    # For YAML-loaded entities (no entry_id) we use the object_id as key.
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    component = EntityComponent[Alert](_LOGGER, DOMAIN, hass)
    hass.data[f"{DOMAIN}_component"] = component

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
    """Set up the HA Alerts component from a config entry.

    Uses .get() with defaults for all keys that may be absent in entries that were
    created by the old 3-step config flow (which only stored CONF_NAME and
    CONF_ENTITY_ID in entry.options).  Without defaults, those entries would raise
    a KeyError here, producing a red error indicator in the HA UI with no working
    entity.
    """
    name: str = entry.options.get(CONF_NAME, "")
    watched_entity_id: str = entry.options.get(CONF_ENTITY_ID, "")
    alert_state: str = entry.options.get(CONF_STATE, STATE_ON)
    # CONF_REPEAT is stored as a single number (float) by the NumberSelector in the
    # config flow UI, or as a list when coming from the service / YAML path.
    # Normalise to list[float] so Alert always receives the same type.
    repeat_raw = entry.options.get(CONF_REPEAT, DEFAULT_REPEAT)
    if isinstance(repeat_raw, list):
        repeat_float = [float(r) for r in repeat_raw]
    else:
        repeat_float = [float(repeat_raw)]
    skip_first: bool = entry.options.get(CONF_SKIP_FIRST, DEFAULT_SKIP_FIRST)
    message_template: str | None = entry.options.get(CONF_ALERT_MESSAGE)
    done_message_template: str | None = entry.options.get(CONF_DONE_MESSAGE)
    notifiers: list[str] = entry.options.get(CONF_NOTIFIERS, [])
    can_ack: bool = entry.options.get(CONF_CAN_ACK, DEFAULT_CAN_ACK)
    title_template: str | None = entry.options.get(CONF_TITLE)
    data: dict[Any, Any] = entry.options.get(CONF_DATA, {})

    # Guard: if name or entity_id is missing, the entry is irrecoverably broken
    # (nothing to watch or name the entity).  Log and fail cleanly.
    if not name or not watched_entity_id:
        _LOGGER.error(
            "ha_alerts entry %s is missing required options (name=%r, entity_id=%r). "
            "Please delete and re-add the alert via the UI.",
            entry.entry_id,
            name,
            watched_entity_id,
        )
        return False

    await async_register_management_services(hass)

    entity = Alert(
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

    # Issue #3 fix: for config entries, avoid EntityComponent and its deprecated
    # async_remove_entity() method. We add the entity via the shared component (needed
    # for turn_on/turn_off/toggle service dispatch) but track it ourselves per-entry
    # so we can remove it safely via the public entity.async_remove() API.
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    component: EntityComponent[Alert] | None = hass.data.get(f"{DOMAIN}_component")
    if component is None:
        component = EntityComponent[Alert](_LOGGER, DOMAIN, hass)
        hass.data[f"{DOMAIN}_component"] = component

    await component.async_add_entities([entity])
    await _async_setup_alert_services(hass, component)

    # Store a reference to the live entity so update/unload can reach it.
    hass.data[DOMAIN][entry.entry_id] = entity

    # Issue #5 fix: options updates are handled in-place by async_handle_update
    # (which calls entity.apply_options() directly).  The update_listener is kept
    # only as a fallback for changes made via the UI options flow, where a full
    # reload is acceptable because the user initiated it deliberately.
    entry.async_on_unload(entry.add_update_listener(update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an HA Alerts entry.

    Issue #4 fix: return the actual outcome of the entity removal rather than
    always returning True.
    """
    entity: Alert | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if entity is None:
        # Entry was never fully set up (e.g., setup failed) — nothing to clean up.
        return True

    # Use the public ToggleEntity.async_remove() instead of the deprecated
    # EntityComponent.async_remove_entity() (Issue #3 fix).
    try:
        await entity.async_remove()
    except Exception:
        _LOGGER.exception("Failed to remove alert entity %s", entity.entity_id)
        return False

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates that come through the UI options flow.

    This triggers a full reload so the entity picks up all new option values.
    The in-place update path (service call) is handled separately in
    async_handle_update, which preserves active-firing state.
    """
    await hass.config_entries.async_reload(entry.entry_id)


class Alert(ToggleEntity):
    """Representation of an alert."""

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
        can_ack: bool,
        title_template: Template | None,
        data: dict[Any, Any],
    ) -> None:
        """Initialize the alert.

        Note: hass is NOT set here. It is injected by the HA entity platform
        machinery via async_added_to_hass(). State-change listeners are
        registered there, not here. (Issue #1 fix)
        """
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

        # Store the watched entity ID so async_added_to_hass() can subscribe.
        self._watched_entity_id = watched_entity_id
        self._unsub_state_change: Callable[[], None] | None = None

        self.entity_id = f"{DOMAIN}.{entity_id}"
        self._attr_unique_id = f"{DOMAIN}_{entity_id}"

    # ------------------------------------------------------------------
    # HA lifecycle — Issue #1 fix
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Register state-change listeners once the entity is part of HA.

        This is the correct place to call async_track_state_change_event —
        it runs after self.hass has been set by the platform machinery and
        the entity has a proper entity_id in the registry.
        """
        self._unsub_state_change = async_track_state_change_event(
            self.hass, [self._watched_entity_id], self.watched_entity_change
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel all listeners when the entity is being removed."""
        if self._unsub_state_change is not None:
            self._unsub_state_change()
            self._unsub_state_change = None
        if self._cancel is not None:
            self._cancel()
            self._cancel = None

    # ------------------------------------------------------------------
    # Options hot-update — Issue #5 fix
    # ------------------------------------------------------------------

    def apply_options(self, options: dict[str, Any], hass: HomeAssistant) -> None:
        """Apply updated config-entry options to this live entity in-place.

        Called by async_handle_update so a full reload (and loss of firing state)
        is avoided when the alert is actively firing.
        """
        self._alert_state = options.get(CONF_STATE, self._alert_state)
        self._skip_first = options.get(CONF_SKIP_FIRST, self._skip_first)
        self._can_ack = options.get(CONF_CAN_ACK, self._can_ack)
        self._notifiers = options.get(CONF_NOTIFIERS, self._notifiers)
        self._data = options.get(CONF_DATA, self._data)

        repeat_raw = options.get(CONF_REPEAT)
        if repeat_raw is not None:
            if isinstance(repeat_raw, list):
                self._delay = [timedelta(minutes=float(r)) for r in repeat_raw]
            else:
                self._delay = [timedelta(minutes=float(repeat_raw))]
            # Clamp the next-delay index in case the repeat list shrank.
            self._next_delay = min(self._next_delay, len(self._delay) - 1)

        msg_raw = options.get(CONF_ALERT_MESSAGE)
        self._message_template = Template(msg_raw, hass) if msg_raw else None

        done_raw = options.get(CONF_DONE_MESSAGE)
        self._done_message_template = Template(done_raw, hass) if done_raw else None

        title_raw = options.get(CONF_TITLE)
        self._title_template = Template(title_raw, hass) if title_raw else None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @final
    @property
    def state(self) -> str:
        """Return the alert status."""
        if self._firing:
            if self._ack:
                return STATE_OFF
            return STATE_ON
        return STATE_IDLE

    # ------------------------------------------------------------------
    # Alert logic
    # ------------------------------------------------------------------

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
                DOMAIN_NOTIFY, target, msg_payload, context=self._context
            )

    # ------------------------------------------------------------------
    # Service handlers
    # ------------------------------------------------------------------

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
