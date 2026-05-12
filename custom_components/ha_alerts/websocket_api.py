"""WebSocket API for HA Alerts CRUD operations."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.exceptions import TemplateError
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from .const import (
    ALERT_ENTITY_DOMAIN,
    ALERT_OBJECT_ID_PREFIX,
    DOMAIN,
    NOTIF_DEFAULT_MESSAGE,
    NOTIF_DEFAULT_RESOLVE_MESSAGE,
    NOTIF_DEFAULT_TITLE,
)

_LOGGER = logging.getLogger(__name__)

NOTIFICATION_SCHEMA = {
    vol.Optional("enabled", default=False): bool,
    vol.Optional("targets", default=[]): [str],
    vol.Optional("title", default=""): str,
    vol.Optional("message", default=""): str,
    vol.Optional("data"): vol.Any(None, dict),
    # repeat: 0 = no repeat, >0 = repeat every N minutes indefinitely
    vol.Optional("repeat", default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
    vol.Optional("resolve_message", default=""): str,
}


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all HA Alerts WebSocket commands."""
    websocket_api.async_register_command(hass, ws_list_alerts)
    websocket_api.async_register_command(hass, ws_create_alert)
    websocket_api.async_register_command(hass, ws_update_alert)
    websocket_api.async_register_command(hass, ws_delete_alert)
    websocket_api.async_register_command(hass, ws_list_categories)
    websocket_api.async_register_command(hass, ws_notify_services)
    websocket_api.async_register_command(hass, ws_test_notification)
    websocket_api.async_register_command(hass, ws_validate_template)
    websocket_api.async_register_command(hass, ws_render_template_once)
    websocket_api.async_register_command(hass, ws_get_translations)
    websocket_api.async_register_command(hass, ws_entity_id_suggest)
    websocket_api.async_register_command(hass, ws_entity_id_check)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "ha_alerts/alert/list"})
@websocket_api.async_response
async def ws_list_alerts(hass, connection, msg):
    """List all alert definitions."""
    try:
        manager = hass.data[DOMAIN]["manager"]
        connection.send_result(msg["id"], {
            "alerts": manager.list_alerts(),
            "categories": manager.list_categories(),
            "notification_defaults": {
                "title": NOTIF_DEFAULT_TITLE,
                "message": NOTIF_DEFAULT_MESSAGE,
                "resolve_message": NOTIF_DEFAULT_RESOLVE_MESSAGE,
            },
        })
    except Exception:
        _LOGGER.exception("Failed to list alerts")
        connection.send_error(msg["id"], "unknown_error", "Failed to list alerts")


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "ha_alerts/alert/create",
    vol.Required("name"): str,
    vol.Optional("entity_id"): str,
    vol.Optional("description"): str,
    vol.Required("condition"): str,
    vol.Optional("category_id"): vol.Any(None, str),
    vol.Optional("category_name"): vol.Any(None, str),
    vol.Optional("notification"): vol.Schema(NOTIFICATION_SCHEMA),
})
@websocket_api.async_response
async def ws_create_alert(hass, connection, msg):
    """Create a new alert."""
    try:
        manager = hass.data[DOMAIN]["manager"]
        result = await manager.async_create_alert({
            "name": msg["name"],
            "entity_id": msg.get("entity_id"),
            "description": msg.get("description"),
            "condition": msg["condition"],
            "category_id": msg.get("category_id"),
            "category_name": msg.get("category_name"),
            "notification": msg.get("notification"),
        })
        connection.send_result(msg["id"], result)
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_input", str(exc))
    except Exception:
        _LOGGER.exception("Failed to create alert")
        connection.send_error(msg["id"], "unknown_error", "Failed to create alert")


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "ha_alerts/alert/update",
    vol.Required("alert_uid"): str,
    vol.Optional("entity_id"): str,
    vol.Optional("name"): str,
    vol.Optional("condition"): str,
    vol.Optional("category_id"): vol.Any(None, str),
    vol.Optional("category_name"): vol.Any(None, str),
    vol.Optional("description"): str,
    vol.Optional("notification"): vol.Schema(NOTIFICATION_SCHEMA),
})
@websocket_api.async_response
async def ws_update_alert(hass, connection, msg):
    """Update an existing alert."""
    try:
        manager = hass.data[DOMAIN]["manager"]
        data = {}
        for key in ("entity_id", "name", "condition", "category_id", "category_name", "description", "notification"):
            if key in msg:
                data[key] = msg[key]
        result = await manager.async_update_alert(msg["alert_uid"], data)
        connection.send_result(msg["id"], result)
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_input", str(exc))
    except Exception:
        _LOGGER.exception("Failed to update alert '%s'", msg.get("alert_uid"))
        connection.send_error(msg["id"], "unknown_error", "Failed to update alert")


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "ha_alerts/alert/delete",
    vol.Required("alert_uid"): str,
})
@websocket_api.async_response
async def ws_delete_alert(hass, connection, msg):
    """Delete an alert."""
    try:
        manager = hass.data[DOMAIN]["manager"]
        await manager.async_delete_alert(msg["alert_uid"])
        connection.send_result(msg["id"], {"success": True})
    except ValueError as exc:
        connection.send_error(msg["id"], "invalid_input", str(exc))
    except Exception:
        _LOGGER.exception("Failed to delete alert '%s'", msg.get("alert_uid"))
        connection.send_error(msg["id"], "unknown_error", "Failed to delete alert")




@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "ha_alerts/entity_id/suggest",
    vol.Required("name"): str,
    vol.Optional("alert_uid"): str,
})
@websocket_api.async_response
async def ws_entity_id_suggest(hass, connection, msg):
    """Suggest a free entity_id based on the provided name."""
    try:
        manager = hass.data[DOMAIN]["manager"]
        entity_id = await manager.async_suggest_entity_id(
            msg["name"], exclude_uid=msg.get("alert_uid")
        )
        connection.send_result(msg["id"], {"entity_id": entity_id})
    except Exception:
        _LOGGER.exception("Failed to suggest entity_id")
        connection.send_error(msg["id"], "unknown_error", "Failed to suggest entity_id")


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "ha_alerts/entity_id/check",
    vol.Required("entity_id"): str,
    vol.Optional("alert_uid"): str,
})
@websocket_api.async_response
async def ws_entity_id_check(hass, connection, msg):
    """Validate entity_id format and availability."""
    try:
        manager = hass.data[DOMAIN]["manager"]
        entity_id = (msg.get("entity_id") or "").strip().lower()
        # Official form only: binary_sensor.ha_alerts_<object_id>
        valid = bool(re.fullmatch(rf"{ALERT_ENTITY_DOMAIN}\.{ALERT_OBJECT_ID_PREFIX}[a-z0-9_]+", entity_id))
        if not valid:
            connection.send_result(msg["id"], {
                "valid": False,
                "available": False,
                "error": "Invalid entity_id format",
            })
            return

        available = await manager.async_entity_id_available(
            entity_id, exclude_uid=msg.get("alert_uid")
        )
        connection.send_result(msg["id"], {
            "valid": True,
            "available": bool(available),
            "error": "" if available else "Entity ID already exists",
        })
    except Exception:
        _LOGGER.exception("Failed to check entity_id")
        connection.send_error(msg["id"], "unknown_error", "Failed to check entity_id")


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "ha_alerts/category/list"})
@websocket_api.async_response
async def ws_list_categories(hass, connection, msg):
    """List all categories."""
    try:
        manager = hass.data[DOMAIN]["manager"]
        connection.send_result(msg["id"], {
            "categories": manager.list_categories(),
        })
    except Exception:
        _LOGGER.exception("Failed to list categories")
        connection.send_error(msg["id"], "unknown_error", "Failed to list categories")


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "ha_alerts/notify_services"})
@websocket_api.async_response
async def ws_notify_services(hass, connection, msg):
    """List available notify services."""
    try:
        services = hass.services.async_services().get("notify", {})
        result = [f"notify.{svc}" for svc in sorted(services.keys())]
        connection.send_result(msg["id"], {"services": result})
    except Exception:
        _LOGGER.exception("Failed to list notify services")
        connection.send_error(msg["id"], "unknown_error", "Failed to list notify services")


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "ha_alerts/test_notification",
    vol.Required("targets"): [str],
    vol.Optional("title", default=""): str,
    vol.Optional("message", default=""): str,
    vol.Optional("data"): vol.Any(None, dict),
    vol.Optional("is_resolve", default=False): bool,
    # Context fields for Jinja2 rendering
    vol.Optional("context_name", default="Test Alert"): str,
    vol.Optional("context_condition", default=""): str,
    vol.Optional("context_entity_id", default="binary_sensor.ha_alerts_test"): str,
})
@websocket_api.async_response
async def ws_test_notification(hass, connection, msg):
    """Send a test notification with Jinja2 template rendering."""
    try:
        variables = {
            "name": msg.get("context_name", "Test Alert"),
            "condition": msg.get("context_condition", ""),
            "entity_id": msg.get("context_entity_id", "binary_sensor.ha_alerts_test"),
            "alert_id": msg.get("context_entity_id", "binary_sensor.ha_alerts_test").replace("binary_sensor.", "", 1),
            "triggered_at": dt_util.utcnow(),
        }

        def _render(template_str):
            if not template_str:
                return ""
            try:
                tpl = Template(template_str, hass)
                return tpl.async_render(variables)
            except Exception:
                return template_str

        rendered_title = _render(msg.get("title", ""))
        if not rendered_title:
            rendered_title = _render(NOTIF_DEFAULT_TITLE)

        message_tpl = msg.get("message", "")
        if not message_tpl:
            message_tpl = NOTIF_DEFAULT_RESOLVE_MESSAGE if msg.get("is_resolve") else NOTIF_DEFAULT_MESSAGE
        rendered_message = _render(message_tpl)

        errors = []
        for target in msg["targets"]:
            service_name = target.replace("notify.", "", 1) if target.startswith("notify.") else target
            service_data = {"message": rendered_message}
            if rendered_title:
                service_data["title"] = rendered_title
            if msg.get("data"):
                service_data["data"] = msg["data"]
            try:
                await hass.services.async_call("notify", service_name, service_data)
            except Exception as exc:
                errors.append(f"{target}: {exc}")

        if errors:
            connection.send_error(msg["id"], "notification_failed", "; ".join(errors))
        else:
            connection.send_result(msg["id"], {"success": True})
    except Exception:
        _LOGGER.exception("Failed to send test notification")
        connection.send_error(msg["id"], "unknown_error", "Failed to send test notification")


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "ha_alerts/validate_template",
    vol.Required("template"): str,
})
@websocket_api.async_response
async def ws_validate_template(hass, connection, msg):
    """Validate a Jinja2 template syntax."""
    try:
        template_str = msg["template"].strip()
        if not template_str:
            connection.send_result(msg["id"], {"valid": True})
            return
        tpl = Template(template_str, hass)
        tpl.ensure_valid()
        connection.send_result(msg["id"], {"valid": True})
    except TemplateError as exc:
        connection.send_result(msg["id"], {
            "valid": False,
            "error": str(exc),
        })
    except Exception:
        _LOGGER.exception("Failed to validate template")
        connection.send_error(msg["id"], "unknown_error", "Failed to validate template")
@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "ha_alerts/template/render_once",
    vol.Required("template"): str,
    vol.Optional("variables"): vol.Any(None, dict),
    vol.Optional("strict", default=True): bool,
})
@websocket_api.async_response
async def ws_render_template_once(hass, connection, msg):
    """Render a template once for UI preview without polluting HA logs.

    We deliberately avoid using HA's built-in `render_template` WS subscription
    because it uses template tracking helpers that log errors to the system log
    while the user is typing (partial/invalid templates).
    """
    try:
        template_str = (msg.get("template") or "").strip()
        if not template_str:
            connection.send_result(msg["id"], {"result": "", "error": ""})
            return

        variables = msg.get("variables")
        strict = bool(msg.get("strict", True))

        # Swallow template engine logs for preview rendering.
        def _noop_log_fn(_level: int, _message: str) -> None:
            return

        tpl = Template(template_str, hass)
        info = tpl.async_render_to_info(variables, strict=strict, log_fn=_noop_log_fn)
        try:
            result = info.result()
        except Exception as exc:  # TemplateError inherits Exception
            connection.send_result(msg["id"], {"result": None, "error": str(exc)})
            return

        connection.send_result(msg["id"], {"result": result, "error": ""})
    except Exception:
        _LOGGER.exception("Failed to render template once")
        connection.send_error(msg["id"], "unknown_error", "Failed to render template")

def _read_json_file(file_path: Path) -> dict:
    """Read and parse JSON file synchronously."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        _LOGGER.error("Failed to read translation file %s: %s", file_path, e)
        return {}


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "ha_alerts/get_translations",
    vol.Optional("language"): str,
})
@websocket_api.async_response
async def ws_get_translations(hass, connection, msg):
    """Return panel translations for the requested language.
    
    Custom panels should load translations directly from JSON files
    as they are not part of the standard HA translation categories.
    This is the recommended approach for custom frontend components.
    """
    try:
        language = msg.get("language") or hass.config.language
        
        # Panel translations live in frontend/translations/
        integration_dir = Path(__file__).parent
        translation_file = integration_dir / "frontend" / "translations" / f"{language}.json"
        
        # Fallback to English if language file not found
        if not translation_file.exists():
            _LOGGER.debug(
                "Panel translation file not found for '%s', falling back to English",
                language
            )
            language = "en"
            translation_file = integration_dir / "frontend" / "translations" / "en.json"
        
        # Load and parse the translation file in executor (non-blocking I/O)
        if translation_file.exists():
            panel_strings = await hass.async_add_executor_job(
                _read_json_file, translation_file
            )
            
            if not panel_strings:
                _LOGGER.warning(
                    "Panel translation file is empty for '%s'", language
                )
        else:
            _LOGGER.error("Panel translation file not found: %s", translation_file)
            panel_strings = {}
        
        _LOGGER.debug(
            "Loaded %d panel translation strings for language '%s'",
            len(panel_strings),
            language
        )
        
        connection.send_result(msg["id"], {
            "language": language,
            "translations": panel_strings
        })
    except Exception:
        _LOGGER.exception(
            "Failed to get translations for language '%s'",
            msg.get("language")
        )
        connection.send_error(msg["id"], "unknown_error", "Failed to get translations")
