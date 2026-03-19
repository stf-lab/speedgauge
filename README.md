<p align="center">
  <img src="static/logo-dark.svg" alt="SpeedGauge" height="60">
</p>

A self-hosted internet speed monitoring tool with a real-time dashboard and Home Assistant integration. Track your connection performance over time with automatic Ookla speed tests, beautiful charts, and instant notifications when speeds drop below your thresholds.

## Features

- **Scheduled speed tests** using the official Ookla Speedtest CLI
- **Real-time gauge** with animated download/upload needles during testing
- **Dashboard** with latest results, server info, and speed history charts (24h / 7d / 30d)
- **History page** with all test results, pagination, and Ookla result links
- **MQTT auto-discovery** for Home Assistant (sensors + run-test button)
- **Notifications** via Telegram and webhooks, with configurable speed thresholds
- **Admin password protection** for the settings page
- **Light and dark themes** (dark by default)
- **Mobile-friendly** responsive design
- **CSV and JSON export** of all test data
- **Auto-scaling gauge** based on your recent average speeds
- **SQLite database** with WAL mode — no external database required
- **Single Docker container** (~200MB)

## Demo

Live demo: [speedgauge](https://speedgauge.tovu.net/)

## Quick Start

### Prerequisites

- Docker and Docker Compose

### Deploy

Create a `docker-compose.yml` file:

```yaml
services:
  speedgauge:
    image: stflab/speedgauge:latest
    container_name: speedgauge
    ports:
      - "8083:8083"
    volumes:
      - ./data:/data
    environment:
      - TZ=Europe/Paris
    security_opt:
      - apparmor=unconfined
    restart: unless-stopped
```

- **Port**: change `8083:8083` to use a different port
- **Timezone**: change `TZ=Europe/Paris` to your timezone
- **Demo mode**: add `SPEEDGAUGE_DEMO=true` to disable admin password changes (useful for public demos)

Then start:
```bash
docker compose up -d
```

SpeedGauge is available at `http://<your-server-ip>:8083`.

### Build from Source

If you prefer to build the image yourself:

```bash
git clone https://github.com/stf-lab/speedgauge.git
cd speedgauge
docker compose up -d --build
```

## Configuration

All configuration is managed through the **Settings** page in the web UI — no config files or environment variables to edit.

| Setting | Description |
|---------|-------------|
| **Test Interval** | How often to run automatic speed tests (10-1440 minutes) |
| **Speedtest Server** | Auto-selects the nearest server, or choose one manually |
| **Data Retention** | Automatically delete results older than N days (0 = keep forever) |
| **Admin Password** | Protect the Settings page with a password |
| **MQTT** | Broker address, port, credentials, topic prefix, HA discovery prefix |
| **Telegram** | Bot token and chat ID for notifications |
| **Webhook** | URL to POST results to on each test |
| **Thresholds** | Get notified when download or upload drops below a value |

## Home Assistant Integration

### MQTT Auto-Discovery

SpeedGauge publishes Home Assistant MQTT discovery messages automatically. When you configure your MQTT broker in Settings:

1. Enter your MQTT broker address, port, and credentials
2. Save settings
3. In Home Assistant, go to **Settings > Devices & Services > MQTT**
4. A **SpeedGauge** device appears automatically with these entities:

| Entity | Type | Unit |
|--------|------|------|
| `sensor.speed_monitor_download` | Sensor | Mbps |
| `sensor.speed_monitor_upload` | Sensor | Mbps |
| `sensor.speed_monitor_ping` | Sensor | ms |
| `sensor.speed_monitor_jitter` | Sensor | ms |
| `sensor.speed_monitor_isp` | Sensor | — |
| `sensor.speed_monitor_external_ip` | Sensor | — |
| `binary_sensor.speed_monitor_test_running` | Binary Sensor | — |
| `button.speed_monitor_run_test` | Button | — |

The button entity lets you trigger a speed test directly from Home Assistant dashboards or automations.

### ApexCharts Dashboard Card

Install [apexcharts-card](https://github.com/RomRider/apexcharts-card) from HACS, then add this card to your dashboard:

```yaml
type: custom:stack-in-card
mode: vertical
cards:
  - type: custom:button-card
    entity: binary_sensor.speed_monitor_test_running
    name: Internet Speed
    icon: mdi:speedometer
    show_state: false
    tap_action:
      action: call-service
      service: button.press
      target:
        entity_id: button.speed_monitor_run_speed_test
      haptic: medium
    styles:
      grid:
        - grid-template-areas: "\"i n\""
        - grid-template-columns: min-content auto
        - align-items: center
      card:
        - padding: 6px 12px
        - border-radius: 0
        - box-shadow: none
        - min-height: 36px
      icon:
        - width: 18px
        - height: 18px
        - margin-right: 8px
      name:
        - font-size: 16px
        - font-weight: 500
        - justify-self: start
        - align-self: center
    state:
      - value: "on"
        name: Running speed test...
        styles:
          icon:
            - color: limegreen
            - animation: rotating 2s linear infinite
      - value: "off"
        name: >
          [[[
            var dl = parseFloat(states['sensor.speed_monitor_download'].state);
            var ul = parseFloat(states['sensor.speed_monitor_upload'].state);
            if (dl >= 1000) dl = (dl/1000).toFixed(1) + ' Gb';                                                                                                                                                
            else dl = dl.toFixed(0) + ' Mb';
            if (ul >= 1000) ul = (ul/1000).toFixed(1) + ' Gb';                                                                                                                                                
            else ul = ul.toFixed(0) + ' Mb';                                                                                                                                                               
            return 'Internet Speed  ↓' + dl + ' ↑' + ul;
          ]]]                                                                                                                                                                                                 
        styles:
          icon:
            - color: var(--primary-color)
    extra_styles: |
      @keyframes rotating {    
        0% { transform: rotate(0deg); }                                                                                                                                                                       
        100% { transform: rotate(360deg); }
      }
  - type: custom:apexcharts-card
    graph_span: 24h
    header:
      show: false
    yaxis:
      - id: speed
        min: 0
        max: 10000
        apex_config:
          title:
            text: Mbps
          decimalsInFloat: 0
      - id: ping
        opposite: true
        min: 0
        max: 10
        apex_config:
          title:
            text: ms
          decimalsInFloat: 0
    series:
      - entity: sensor.speed_monitor_download
        name: Down
        type: area
        color: LightSeaGreen
        stroke_width: 2
        yaxis_id: speed
        show:
          legend_value: true
      - entity: sensor.speed_monitor_upload
        name: Up
        type: area
        color: MediumPurple
        stroke_width: 2
        yaxis_id: speed
        show:
          legend_value: true
      - entity: sensor.speed_monitor_ping
        name: Ping
        type: line
        color: SandyBrown
        stroke_width: 2
        yaxis_id: ping
        show:
          legend_value: true
        group_by:
          func: avg
          duration: 1h
    apex_config:
      chart:
        type: area
      stroke:
        curve: smooth
      xaxis:
        type: datetime
        labels:
          datetimeFormatter:
            hour: HH:mm
      fill:
        type: gradient
        gradient:
          shadeIntensity: 0.2
          opacityFrom: 0.7
          opacityTo: 0.8


```

Change `graph_span` to `7d` or `30d` for longer time ranges.

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/results` | List results (`limit`, `offset`, `from`, `to` query params) |
| `GET` | `/api/results/latest` | Latest test result |
| `GET` | `/api/results/{id}` | Single result by ID |
| `DELETE` | `/api/results/{id}` | Delete a result (admin) |
| `GET` | `/api/stats?period=24h` | Aggregated stats (`24h`, `7d`, `30d`, `all`) |
| `POST` | `/api/speedtest/run` | Trigger a speed test |
| `GET` | `/api/speedtest/status` | Current test status and progress |
| `GET` | `/api/servers` | List nearby Ookla servers |
| `GET` | `/api/config` | Get configuration (admin) |
| `PUT` | `/api/config` | Update configuration (admin) |
| `GET` | `/api/export?format=csv` | Export results as CSV or JSON |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/version` | App version |

## Roadmap

- [ ] Connection quality grading (A-F)
- [ ] ISP/IP change detection and notifications
- [x] Published Docker Hub image
- [ ] Test schedule jitter/randomization
- [ ] Multi-server comparison
- [ ] PDF weekly/monthly reports
- [ ] Internet outage tracking
- [ ] REST API key authentication

## Contributing

Contributions are welcome! Feel free to open an issue or submit a pull request. Whether it is a bug fix, new feature, or documentation improvement, all contributions are appreciated.

## License

This project is licensed under the [MIT License](LICENSE).

