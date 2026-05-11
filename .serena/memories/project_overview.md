# Project: HA Alerts v2

Home Assistant custom integration. Store-backed JSON storage, binary_sensor entities per alert, LitElement sidebar panel (uncompiled JS), WebSocket API, AI-agent-first service surface.

Repo: disforw/HA-Alerts, main branch. v1.3 frozen in v1.3-stable branch.

## Stack
- Python 3.12 (HA integration)
- Vanilla JS / LitElement (no build step)
- HA Store for persistence (.storage/ha_alerts)

## Style
- Type hints throughout Python
- Docstrings on classes and public methods
- snake_case Python, camelCase JS
- Compact: no unnecessary abstraction
