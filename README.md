# HA Alerts

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A HACS-compatible custom integration for Home Assistant that brings **UI-based config flow** to the built-in `alert` integration — no more YAML required.

> Based on the work from [HA Core PR #79952](https://github.com/home-assistant/core/pull/79952), which added a UI config flow to the native Alert integration but was never merged. This standalone version makes that work available via HACS today.

---

## What It Does

HA Alerts watches an entity and sends repeating notifications when that entity enters a specified state. When the condition clears, it can optionally send a "done" message.

Each alert is:
- Configured entirely through the Home Assistant UI (no YAML needed)
- A `ToggleEntity` — you can **acknowledge** (silence) it by turning it off, and **unacknowledge** by turning it back on
- Capable of sending to any notify service registered in your HA instance

---

## Key Features

| Feature | Description |
|---|---|
| **UI Config Flow** | Add and configure alerts entirely through Settings → Devices & Services |
| **Repeat Intervals** | Define one or more intervals (in minutes) for escalating re-notifications |
| **Skip First** | Optionally skip the first notification and wait for the first repeat interval |
| **Acknowledge / Unacknowledge** | Silence an active alert by toggling the entity off; re-enable by toggling on |
| **Message Template** | Jinja2 template for the alert message body |
| **Done Message Template** | Jinja2 template for the message sent when the alert condition clears |
| **Title Template** | Jinja2 template for the notification title |
| **Extra Data** | Pass additional data payload to the notification service |
| **Multiple Notifiers** | Send to one or more `notify.*` services simultaneously |
| **YAML Compatible** | Still supports YAML config under the `ha_alerts:` key for backwards compatibility |

---

## Installation

### Via HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations**
3. Click the **⋮** menu (top right) → **Custom repositories**
4. Add `https://github.com/disforw/HA-Alerts` as an **Integration**
5. Search for **HA Alerts** and click **Download**
6. Restart Home Assistant

### Manual

1. Download or clone this repository
2. Copy the `custom_components/ha_alerts/` directory into your HA config's `custom_components/` folder
3. Restart Home Assistant

---

## Adding an Alert via the UI

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for **HA Alerts**
4. Follow the three-step setup wizard:

### Step 1 — Basic Info

| Field | Description |
|---|---|
| **Name** | A friendly name for this alert (e.g. "Garage Door Open") |
| **Entity** | The entity to watch (e.g. `binary_sensor.garage_door`) |

### Step 2 — Alert Options

| Field | Description |
|---|---|
| **Alert State** | The state that triggers alerting. Defaults to `on` |
| **Repeat Intervals** | One or more intervals in minutes. First value = initial repeat; subsequent values allow escalation. Example: `5, 15, 60` |
| **Can Acknowledge** | Whether the alert can be silenced by toggling the entity off |
| **Skip First Notification** | If enabled, no notification is sent immediately — only after the first interval elapses |

### Step 3 — Notification Services

| Field | Description |
|---|---|
| **Notification Services** | Select one or more `notify.*` services to send through |
| **Message Template** | _(Optional)_ Jinja2 template for the alert message. Falls back to the alert name |
| **Done Message Template** | _(Optional)_ Jinja2 template for the message sent when the condition clears |
| **Title Template** | _(Optional)_ Jinja2 template for the notification title |
| **Extra Data** | _(Optional)_ Additional data passed to the notify service |

---

## YAML Configuration (Legacy)

You can still configure alerts via `configuration.yaml` under the `ha_alerts:` key:

```yaml
ha_alerts:
  garage_door_alert:
    name: Garage Door Open
    entity_id: binary_sensor.garage_door
    state: "on"
    repeat:
      - 5
      - 15
      - 60
    can_acknowledge: true
    skip_first: false
    notifiers:
      - mobile_app_my_phone
    message: "The garage door has been open for {{ repeat_delay }} minutes!"
    done_message: "Garage door is now closed."
    title: "Garage Door Alert"
```

---

## Entity States

The alert entity (`ha_alerts.<name>`) reports three states:

| State | Meaning |
|---|---|
| `idle` | The watched entity is not in the alert state |
| `on` | Alert is active and firing (notifications being sent) |
| `off` | Alert is active but has been acknowledged (silenced) |

---

## Services

The integration registers these services under the `ha_alerts` domain:

| Service | Description |
|---|---|
| `ha_alerts.turn_on` | Unacknowledge (re-enable) a silenced alert |
| `ha_alerts.turn_off` | Acknowledge (silence) an active alert |
| `ha_alerts.toggle` | Toggle acknowledgement state |

---

## Requirements

- Home Assistant 2023.1.0 or newer
- At least one configured `notify` service

---

## License

MIT — see [LICENSE](LICENSE)
