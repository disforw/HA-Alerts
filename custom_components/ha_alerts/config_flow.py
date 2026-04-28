"""Config flow for HA Alerts integration."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import voluptuous as vol

from homeassistant.const import CONF_NAME, CONF_REPEAT
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaConfigFlowHandler,
    SchemaFlowFormStep,
    SchemaFlowMenuStep,
)

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


async def get_user_schema(
    handler: SchemaCommonFlowHandler,
) -> vol.Schema:
    """Build schema for step 1: name, trigger template, repeat, skip_first."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME): selector.TextSelector(),
            vol.Required(CONF_TRIGGER_TEMPLATE): selector.TemplateSelector(),
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
                CONF_SKIP_FIRST, default=DEFAULT_SKIP_FIRST
            ): selector.BooleanSelector(),
        }
    )


async def get_options_schema(
    handler: SchemaCommonFlowHandler,
) -> vol.Schema:
    """Build schema for the options flow init step."""
    return vol.Schema(
        {
            vol.Required(CONF_TRIGGER_TEMPLATE): selector.TemplateSelector(),
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
    icon = "mdi:bell-alert"

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return config entry title."""
        return cast(str, options[CONF_NAME]) if CONF_NAME in options else ""

    async def async_step_import(self, import_data: dict[str, Any]) -> Any:
        """Handle import from ha_alerts.create service call."""
        repeat_raw = import_data.get(CONF_REPEAT, [DEFAULT_REPEAT])
        if isinstance(repeat_raw, list):
            import_data[CONF_REPEAT] = float(repeat_raw[0])
        else:
            import_data[CONF_REPEAT] = float(repeat_raw)

        return self.async_create_entry(data=import_data)
