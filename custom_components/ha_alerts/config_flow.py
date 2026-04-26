"""Config flow for HA Alerts integration."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import voluptuous as vol

from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_REPEAT,
    CONF_STATE,
    STATE_ON,
)
from homeassistant.core import async_get_hass
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaConfigFlowHandler,
    SchemaFlowFormStep,
    SchemaFlowMenuStep,
)

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

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        vol.Required(CONF_ENTITY_ID): selector.EntitySelector(),
    }
)


async def _next_step_options(_: dict) -> str:
    """Return next step: options."""
    return "options"


async def _next_step_notifier(_: dict) -> str:
    """Return next step: notifier."""
    return "notifier"


async def get_options_schema(
    flow_handler: SchemaConfigFlowHandler,
    user_input: dict[str, Any] | None = None,
) -> vol.Schema:
    """Get schema for additional options."""
    # Try to get the entity_id from prior step options so we can offer
    # real state values as a dropdown.  Fall back gracefully if unavailable.
    entity_id: str | None = None
    state_options: list[selector.SelectOptionDict] = []

    try:
        entity_id = flow_handler.options.get(CONF_ENTITY_ID)
    except AttributeError:
        pass

    if entity_id:
        try:
            hass = async_get_hass()
            entity_state = hass.states.get(entity_id)
            if entity_state is not None:
                current_state = entity_state.state
                # Build option list: current state first, then common extras
                seen: set[str] = set()
                for s in [current_state, "on", "off", "home", "not_home", "idle"]:
                    if s and s not in seen:
                        state_options.append(
                            selector.SelectOptionDict(value=s, label=s)
                        )
                        seen.add(s)
        except Exception:  # noqa: BLE001
            state_options = []

    if state_options:
        state_selector: selector.Selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=state_options,
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
    else:
        # Fallback: free text (e.g. during initial config before entity is known)
        state_selector = selector.TextSelector()

    return vol.Schema(
        {
            vol.Required(CONF_STATE, default=STATE_ON): state_selector,
            vol.Required(
                CONF_REPEAT, default=DEFAULT_REPEAT
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=9999,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="minutes",
                )
            ),
            vol.Required(
                CONF_CAN_ACK, default=DEFAULT_CAN_ACK
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_SKIP_FIRST, default=DEFAULT_SKIP_FIRST
            ): selector.BooleanSelector(),
        }
    )


async def get_notifier_schema(
    flow_handler: SchemaConfigFlowHandler,
    user_input: dict[str, Any] | None = None,
) -> vol.Schema:
    """Update list with notify services."""
    hass = async_get_hass()
    all_services = hass.services.async_services()
    notify_services = all_services.get("notify", {})
    notify_keys = list(notify_services.keys())

    notify_options = [
        selector.SelectOptionDict(value=key, label=key.replace("_", " ").title())
        for key in notify_keys
    ]

    return vol.Schema(
        {
            vol.Required(CONF_NOTIFIERS): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_options,
                    multiple=True,
                )
            ),
            vol.Optional(CONF_ALERT_MESSAGE): selector.TemplateSelector(),
            vol.Optional(CONF_DONE_MESSAGE): selector.TemplateSelector(),
            vol.Optional(CONF_TITLE): selector.TemplateSelector(),
            vol.Optional(CONF_DATA): selector.ObjectSelector(),
        }
    )


CONFIG_FLOW: dict[str, SchemaFlowFormStep | SchemaFlowMenuStep] = {
    "user": SchemaFlowFormStep(
        CONFIG_SCHEMA,
        next_step=_next_step_options,
    ),
    "options": SchemaFlowFormStep(
        get_options_schema,
        next_step=_next_step_notifier,
    ),
    "notifier": SchemaFlowFormStep(
        get_notifier_schema,
    ),
}

OPTIONS_FLOW: dict[str, SchemaFlowFormStep | SchemaFlowMenuStep] = {
    "init": SchemaFlowFormStep(
        get_options_schema,
        next_step=_next_step_notifier,
    ),
    "notifier": SchemaFlowFormStep(
        get_notifier_schema,
    ),
}


class ConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Handle a config or options flow for HA Alerts."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return config entry title."""
        return cast(str, options["name"]) if "name" in options else ""
