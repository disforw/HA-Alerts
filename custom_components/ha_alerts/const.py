"""Constants for the HA Alerts integration."""

DOMAIN = "ha_alerts"
ALERT_ENTITY_DOMAIN = "binary_sensor"
ALERT_OBJECT_ID_PREFIX = "ha_alerts_"
STORAGE_KEY = f"{DOMAIN}.storage"
STORAGE_VERSION = 1

# Alert config keys
CONF_ALERTS = "alerts"
CONF_NAME = "name"
CONF_CONDITION = "condition"
CONF_REPEAT = "repeat"  # minutes; 0 = no repeat
CONF_CATEGORY_ID = "category_id"
CONF_DESCRIPTION = "description"
CONF_ENABLED = "enabled"

# Entity attributes
ATTR_CONDITION = "condition"
ATTR_ACK = "ack"
ATTR_DESCRIPTION = "description"
ATTR_ENABLED = "enabled"

# Service names
SERVICE_ADD = "add"
SERVICE_REMOVE = "remove"
SERVICE_UPDATE = "update"
SERVICE_ENABLE = "enable"
SERVICE_DISABLE = "disable"

# Default category
DEFAULT_CATEGORY_ID = "default"
DEFAULT_CATEGORY_NAME = "Uncategorized"

# Notification defaults
NOTIF_DEFAULT_TITLE = "HA Alerts: {{ name }}"
NOTIF_DEFAULT_MESSAGE = "Alert '{{ name }}' triggered"
NOTIF_DEFAULT_RESOLVE_MESSAGE = "Alert '{{ name }}' - condition cleared"

INTEGRATION_VERSION = "2.0.0"
