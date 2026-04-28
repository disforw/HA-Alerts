# HA Alerts

A HACS custom integration for Home Assistant that replaces the built-in alerting system with a clean, UI-driven alternative powered by Jinja2 templates.

## Features

- **Template-based triggering** — any Jinja2 expression that evaluates to `true` fires the alert. Watch a single entity, multiple entities, an entire device class, or any complex condition.
- **UI config flow** — add and manage alerts via **Settings → Helpers → Add Helper → HA Alerts**
- **Single unified row** per alert in the Helpers screen — toggle, history, reconfigure, and delete all in one place
- **Arm / Disarm** — the toggle arms or disarms the alert
  - **Armed** (`on`): template is evaluated, notifications fire when it becomes true
  - **Disarmed** (`off`): template not evaluated, completely silent. Disarming mid-fire is a hard stop.
- **Repeating notifications** — fires at a configurable interval (minutes) while the condition remains true
- **Skip-first** — skip the immediate notification and wait for the first repeat interval instead
- **Done message** — sends a notification when the alert condition clears
- **Custom Jinja2 templates** — for message, done message, and title
- **Multiple notifiers** — send to one or more notify services simultaneously
- **Extra data payload** — pass arbitrary data to the notify service
- **Dynamic icons** — `mdi:bell-off` (disarmed), `mdi:bell` (armed), `mdi:bell-alert` (firing)
- **State attributes** — `firing` (bool) and `last_triggered` (ISO timestamp) for automations
- **Management services** — `ha_alerts.create`, `ha_alerts.update`, `ha_alerts.delete`

## Installation

Install via [HACS](https://hacs.xyz) by adding this repository as a custom repository, or copy `custom_components/ha_alerts` into your HA config directory.

## Usage

### Adding an alert via UI

1. **Settings → Helpers → Add Helper → HA Alerts**
2. **Step 1 — Alert:**
   - **Name** — friendly name (e.g. `Den Light On`)
   - **Trigger Template** — Jinja2 expression that evaluates to `true` when alert should fire
   - **Repeat Interval** — how often to re-notify while condition persists (minutes)
   - **Skip First** — skip the immediate notification, wait for first repeat
3. **Step 2 — Notifications:**
   - **Notification Services** — one or more notify services
   - **Message / Done Message / Title** — optional Jinja2 templates
   - **Extra Data** — optional payload

### Trigger template examples

**Single entity state:**
```jinja2
{{ is_state('light.den', 'on') }}
```

**Any moisture sensor wet:**
```jinja2
{{ states.sensor | selectattr('attributes.device_class', 'eq', 'moisture') | selectattr('state', 'eq', 'wet') | list | count > 0 }}
```

**Any door open while away:**
```jinja2
{{ is_state('person.ben', 'not_home') and states.binary_sensor | selectattr('attributes.device_class', 'eq', 'door') | selectattr('state', 'eq', 'on') | list | count > 0 }}
```

**Temperature threshold:**
```jinja2
{{ states('sensor.outdoor_temperature') | float > 95 }}
```

### Arm / Disarm

Each alert entity is a switch. Toggle it to arm or disarm the alert:
- **Armed** — alert watches the template and fires notifications
- **Disarmed** — completely silent, template not evaluated

### Auto-entities card

To show all HA Alerts in a Lovelace card using [auto-entities](https://github.com/thomasloven/lovelace-auto-entities):

```yaml
type: custom:auto-entities
card:
  type: entities
filter:
  include:
    - attributes:
        ha_alerts: true
```

### Management services

**Create an alert:**
```yaml
service: ha_alerts.create
data:
  name: Den Light Alert
  trigger_template: "{{ is_state('light.den', 'on') }}"
  repeat: 5
  notifiers:
    - mobile_app_my_phone
  message: "Den light has been on for a while!"
  done_message: "Den light is now off."
```

**Update an alert:**
```yaml
service: ha_alerts.update
data:
  entity_id: switch.den_light_alert
  repeat: 10
  notifiers:
    - mobile_app_my_phone
    - notify_telegram
```

**Delete an alert:**
```yaml
service: ha_alerts.delete
data:
  entity_id: switch.den_light_alert
```

## Changelog

### v1.1
- **Template-based triggering** replaces `entity_id` + `state` fields
- Any Jinja2 expression supported — single entity, device class, multi-condition, threshold
- `ha_alerts.create` and `ha_alerts.update` services updated to use `trigger_template`

### v1.0.2
- Added `ha_alerts: true` state attribute for auto-entities filtering

### v1.0.1
- Fixed `repeat` schema to accept bare number in service calls

### v1.0.0
- Initial release
