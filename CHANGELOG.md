# Changelog

## 1.0.0 — 2026-03-19

Initial release. Custom-built speed monitoring app.



### Features
- Ookla Speedtest CLI integration with real-time progress
- SVG gauge speedometer with download (blue) and upload (green) needles
- Auto-scaling gauge based on 7-day average speed
- Dashboard with latest results, server info, and speed history chart (24h/7d/30d)
- History page with all test results and Ookla result links
- Settings page with admin password protection (30-day sessions)
- Configurable test interval from the UI (no restart needed)
- Automatic nearest server selection with manual override
- MQTT auto-discovery for Home Assistant:
  - Download, Upload, Ping, Jitter, ISP, External IP sensors
  - Test Running binary sensor
  - Run Test button entity
- Telegram and webhook notifications with threshold alerts
- Data retention auto-cleanup
- CSV and JSON data export
- Light/dark theme (dark default)
- Mobile-responsive design
- Custom SVG logo/favicon
- SQLite database with WAL mode
- Single Docker container (~200MB)
