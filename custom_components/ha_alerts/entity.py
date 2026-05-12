"""Entity classes for the HA Alerts integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    TrackTemplate,
    async_track_state_change_event,
    async_track_template_result,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.template import Template, result_as_boolean, is_template_string
from homeassistant.util import dt as dt_util

from .const import (
    ALERT_ENTITY_DOMAIN,
    ATTR_ACK,
    ATTR_CONDITION,
    ATTR_DESCRIPTION,
    DOMAIN,
    NOTIF_DEFAULT_TITLE,
    NOTIF_DEFAULT_MESSAGE,
    NOTIF_DEFAULT_RESOLVE_MESSAGE,
)

if TYPE_CHECKING:
    from .store import HaAlertsManager

_LOGGER = logging.getLogger(__name__)


class AlertEntity(BinarySensorEntity, RestoreEntity):
    """Represents a single alert in the ha_alerts domain."""

    _attr_should_poll = False
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(
        self,
        hass: HomeAssistant,
        uid: str,
        name: str,
        condition_config: str,
        manager: HaAlertsManager,
        notification_config: dict | None = None,
        description: str = "",
        enabled: bool = True,
    ) -> None:
        self.hass = hass
        self._uid = uid
        self._attr_name = name
        self._condition_config = condition_config
        self._manager = manager
        self._description = description or ""

        # State
        self._active = False
        self._condition_met = False
        self._ack = False
        self._enabled = enabled

        # Condition tracking
        self._is_template = is_template_string(condition_config)
        self._template: Template | None = None
        self._tracked_entity_id: str | None = None
        self._track_template_info = None
        self._unsub_entity_tracker = None
        self._last_template_error: str | None = None

        if self._is_template:
            self._template = Template(condition_config, hass)
        else:
            self._tracked_entity_id = condition_config

        # Notification
        self._notification_config = notification_config or {}
        self._notif_timer_unsub = None
        self._triggered_at = None

    @property
    def unique_id(self) -> str:
        return self._uid

    @property
    def is_on(self) -> bool:
        return self._active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            ATTR_CONDITION: self._condition_met,
            ATTR_ACK: self._ack,
            ATTR_DESCRIPTION: self._description,
            ATTR_ENABLED: self._enabled,
        }

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def condition_met(self) -> bool:
        return self._condition_met

    @property
    def is_acked(self) -> bool:
        return self._ack

    async def async_added_to_hass(self) -> None:
        """Start tracking condition when entity is added."""
        self._manager.register_alert_entity(self._uid, self)

        restored_ack = False
        last_state = await self.async_get_last_state()
        if last_state is not None:
            restored_ack = last_state.attributes.get(ATTR_ACK, False)

        if self._is_template:
            self._setup_template_tracking()
        else:
            self._setup_entity_tracking()

        if self._active and restored_ack:
            self._ack = True
            self.async_write_ha_state()

    def _setup_template_tracking(self) -> None:
        """Track a template condition."""
        track = TrackTemplate(self._template, None, None, parse_result=False)

        def _noop_log_fn(_level: int, _message: str) -> None:
            return

        @callback
        def _template_result_changed(event, updates):
            track_result = updates.pop()
            result = track_result.result
            if isinstance(result, Exception):
                err = str(result)
                if err != self._last_template_error:
                    _LOGGER.debug("Template error for %s: %s", self.entity_id, err)
                    self._last_template_error = err
                return
            if self._last_template_error is not None:
                self._last_template_error = None
            try:
                new_condition = result_as_boolean(result)
            except ValueError:
                _LOGGER.error(
                    "Template result for %s is not boolean: %s", self.entity_id, result
                )
                return
            self._update_condition(new_condition)

        self._track_template_info = async_track_template_result(
            self.hass, [track], _template_result_changed, log_fn=_noop_log_fn
        )
        self._track_template_info.async_refresh()

    def _setup_entity_tracking(self) -> None:
        """Track a boolean entity condition."""
        current_state = self.hass.states.get(self._tracked_entity_id)
        if current_state and current_state.state not in (STATE_UNKNOWN, "unavailable"):
            self._update_condition(
                current_state.state.lower() in ("on", "true", "1")
            )

        @callback
        def _entity_state_changed(event):
            new_state = event.data.get("new_state")
            if new_state is None:
                return
            self._update_condition(new_state.state.lower() in ("on", "true", "1"))

        self._unsub_entity_tracker = async_track_state_change_event(
            self.hass, [self._tracked_entity_id], _entity_state_changed
        )

    @callback
    def _update_condition(self, new_condition: bool) -> None:
        """Handle condition state change and apply lifecycle rules."""
        if not self._enabled:
            return
        old_condition = self._condition_met
        self._condition_met = new_condition

        if new_condition and not self._active:
            # Fresh activation
            self._active = True
            self._ack = False
            self._triggered_at = dt_util.utcnow()
            self.async_write_ha_state()
            self._start_notification_cycle()

        elif not new_condition and old_condition and self._active:
            # Condition cleared — always auto-quit
            self._stop_notification_timer()
            self._send_resolve_if_needed()
            self._active = False
            self._ack = False
            self._triggered_at = None
            self.async_write_ha_state()

        elif new_condition and not old_condition and self._active:
            # Condition re-triggered while alert still active
            self._triggered_at = dt_util.utcnow()
            self._start_notification_cycle()
            self.async_write_ha_state()

        elif new_condition != old_condition:
            self.async_write_ha_state()

    def quit(self) -> bool:
        """Manually quit (reset) the alert. Only works when condition is not active."""
        if not self._active or self._condition_met:
            return False
        self._stop_notification_timer()
        self._active = False
        self._ack = False
        self._triggered_at = None
        self.async_write_ha_state()
        return True

    def enable(self) -> None:
        """Enable (arm) the alert. Evaluates condition immediately."""
        self._enabled = True
        self.async_write_ha_state()
        # Evaluate current condition immediately — if already true, fire now
        if self._condition_met and not self._active:
            self._update_condition(True)

    def disable(self) -> None:
        """Disable (disarm) the alert."""
        self._enabled = False
        self._stop_notification_timer()
        self._active = False
        self._ack = False
        self.async_write_ha_state()

    def ack(self) -> bool:
        """Acknowledge the alert."""
        if not self._active:
            return False
        self._ack = True
        self._stop_notification_timer()
        self.async_write_ha_state()
        return True

    def unack(self) -> bool:
        """Remove acknowledgement."""
        if not self._active:
            return False
        self._ack = False
        if self._condition_met:
            self._continue_notification_cycle()
        self.async_write_ha_state()
        return True

    def ack_toggle(self) -> bool:
        """Toggle acknowledgement state."""
        if not self._active:
            return False
        return self.unack() if self._ack else self.ack()

    # ------------------------------------------------------------------
    # Notification engine
    # ------------------------------------------------------------------

    @callback
    def _start_notification_cycle(self) -> None:
        """Start a fresh notification cycle: send first notification, then start repeat timer."""
        nc = self._notification_config
        if not nc.get("enabled") or not nc.get("targets"):
            return

        self._stop_notification_timer()
        self.hass.async_create_task(self._async_send_notification())

        repeat = nc.get("repeat", 0)  # minutes
        if repeat > 0:
            self._notif_timer_unsub = async_track_time_interval(
                self.hass,
                self._notif_timer_tick,
                timedelta(minutes=repeat),
            )

    @callback
    def _continue_notification_cycle(self) -> None:
        """Resume notification cycle after unack."""
        nc = self._notification_config
        if not nc.get("enabled") or not nc.get("targets"):
            return

        self._stop_notification_timer()
        self.hass.async_create_task(self._async_send_notification())

        repeat = nc.get("repeat", 0)
        if repeat > 0:
            self._notif_timer_unsub = async_track_time_interval(
                self.hass,
                self._notif_timer_tick,
                timedelta(minutes=repeat),
            )

    @callback
    def _stop_notification_timer(self) -> None:
        """Cancel the repeat timer."""
        if self._notif_timer_unsub:
            self._notif_timer_unsub()
            self._notif_timer_unsub = None

    @callback
    def _notif_timer_tick(self, _now) -> None:
        """Handle repeat timer tick — fires every repeat minutes."""
        nc = self._notification_config
        if not nc.get("enabled") or not self._condition_met or self._ack:
            self._stop_notification_timer()
            return
        self.hass.async_create_task(self._async_send_notification())

    async def _async_send_notification(self) -> None:
        """Send a notification to all configured targets."""
        nc = self._notification_config
        if not nc.get("enabled") or not nc.get("targets"):
            return

        title = self._render_template(nc.get("title", ""))
        message = self._render_template(nc.get("message", "")) or self._render_template(NOTIF_DEFAULT_MESSAGE)

        for target in nc["targets"]:
            service_name = target.removeprefix("notify.")
            service_data: dict = {"message": message}
            if title:
                service_data["title"] = title
            if nc.get("data"):
                service_data["data"] = nc["data"]
            if not self.hass.services.has_service("notify", service_name):
                continue
            try:
                await self.hass.services.async_call("notify", service_name, service_data)
            except Exception:
                _LOGGER.exception(
                    "Failed to send notification for %s via notify.%s",
                    self.entity_id, service_name,
                )

    async def _async_send_resolve_notification(self) -> None:
        """Send resolve notification to all configured targets."""
        nc = self._notification_config
        title = self._render_template(nc.get("title", ""))
        message = self._render_template(nc.get("resolve_message", "")) or self._render_template(NOTIF_DEFAULT_RESOLVE_MESSAGE)

        for target in nc.get("targets", []):
            service_name = target.removeprefix("notify.")
            service_data: dict = {"message": message}
            if title:
                service_data["title"] = title
            if nc.get("data"):
                service_data["data"] = nc["data"]
            try:
                await self.hass.services.async_call("notify", service_name, service_data)
            except Exception:
                _LOGGER.exception(
                    "Failed to send resolve notification for %s via notify.%s",
                    self.entity_id, service_name,
                )

    def _render_template(self, template_str: str) -> str:
        """Render a Jinja2 template with alert context variables."""
        if not template_str:
            return ""
        try:
            tpl = Template(template_str, self.hass)
            alert_id = ""
            if self.entity_id and self.entity_id.startswith(f"{ALERT_ENTITY_DOMAIN}."):
                alert_id = self.entity_id.removeprefix(f"{ALERT_ENTITY_DOMAIN}.")
            return tpl.async_render({
                "name": self._attr_name,
                "condition": self._condition_config,
                "entity_id": self.entity_id,
                "alert_id": alert_id,
                "alert_uid": self._uid,
                "triggered_at": self._triggered_at,
            }, parse_result=False)
        except Exception:
            _LOGGER.exception("Failed to render template for %s", self.entity_id)
            return template_str

    async def async_will_remove_from_hass(self) -> None:
        """Clean up trackers and unregister from manager."""
        self._stop_notification_timer()
        self._manager.unregister_alert_entity(self._uid)
        if self._track_template_info:
            self._track_template_info.async_remove()
        if self._unsub_entity_tracker:
            self._unsub_entity_tracker()
