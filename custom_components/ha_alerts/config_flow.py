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
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
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


async def get_user_schema(
    handler: SchemaCommonFlowHandler,
) -> vol.Schema:
    """Build schema for step 1: name, entity_id, state, repeat, can_ack, skip_first.

    Tries to offer a dropdown of real state values for the watched entity.
    Falls back to a free-text field when the entity is unknown.
    """
    hass = handler.parent_handler.hass

    entity_id: str | None = handler.options.get(CONF_ENTITY_ID)
    state_options: list[selector.SelectOptionDict] = []

    if entity_id:
        try:
            entity_state = hass.states.get(entity_id)
            if entity_state is not None:
                seen: set[str] = set()
                for s in [entity_state.state, "on", "off", "home", "not_home", "idle"]:
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
        state_selector = selector.TextSelector()

    return vol.Schema(
        {
            vol.Required(CONF_NAME): selector.TextSelector(),
            vol.Required(CONF_ENTITY_ID): selector.EntitySelector(),
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


async def get_options_schema(
    handler: SchemaCommonFlowHandler,
) -> vol.Schema:
    """Get schema for alert options (used in OPTIONS_FLOW init step).

    Tries to offer a dropdown of real state values for the watched entity.
    Falls back to a free-text field when the entity is unknown.
    """
    hass = handler.parent_handler.hass

    entity_id: str | None = handler.options.get(CONF_ENTITY_ID)
    state_options: list[selector.SelectOptionDict] = []

    if entity_id:
        try:
            entity_state = hass.states.get(entity_id)
            if entity_state is not None:
                seen: set[str] = set()
                for s in [entity_state.state, "on", "off", "home", "not_home", "idle"]:
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
    handler: SchemaCommonFlowHandler,
) -> vol.Schema:
    """Build schema listing all available notify services."""
    hass = handler.parent_handler.hass
    notify_services = hass.services.async_services_for_domain("notify")
    notify_options = [
        selector.SelectOptionDict(value=key, label=key.replace("_", " ").title())
        for key in sorted(notify_services.keys())
    ]

    return vol.Schema(
        {
            vol.Required(CONF_NOTIFIERS): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_options,
                    multiple=True,
                    custom_value=True,
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
        get_user_schema,
        next_step="notifier",
    ),
    "notifier": SchemaFlowFormStep(
        get_notifier_schema,
    ),
}

OPTIONS_FLOW: dict[str, SchemaFlowFormStep | SchemaFlowMenuStep] = {
    "init": SchemaFlowFormStep(
        get_options_schema,
        next_step="notifier",
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
        return cast(str, options[CONF_NAME]) if CONF_NAME in options else ""

    async def async_step_import(self, import_data: dict[str, Any]) -> Any:
        """Handle import from ha_alerts.create service call."""
        # Normalise CONF_REPEAT to a single float so it matches what the
        # NumberSelector UI stores and what async_setup_entry expects.
        repeat_raw = import_data.get(CONF_REPEAT, [1])
        if isinstance(repeat_raw, list):
            import_data[CONF_REPEAT] = float(repeat_raw[0])
        else:
            import_data[CONF_REPEAT] = float(repeat_raw)

        return self.async_create_entry(data=import_data)
