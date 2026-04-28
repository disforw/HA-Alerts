"""Constants for HA Alerts integration."""
from __future__ import annotations

DOMAIN = "ha_alerts"

CONF_TRIGGER_TEMPLATE = "trigger_template"
CONF_NOTIFIERS = "notifiers"
CONF_SKIP_FIRST = "skip_first"
CONF_ALERT_MESSAGE = "message"
CONF_DONE_MESSAGE = "done_message"
CONF_TITLE = "title"
CONF_DATA = "data"

DEFAULT_SKIP_FIRST = False
DEFAULT_REPEAT = 30
