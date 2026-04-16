"""Configuration management backed by SQLite."""
import sqlite3
import threading

DEFAULTS = {
    "interval_minutes": "60",
    "timezone": "Europe/Paris",
    "server_id": "",
    "mqtt_broker": "",
    "mqtt_port": "1883",
    "mqtt_user": "",
    "mqtt_pass": "",
    "mqtt_topic_prefix": "speed_monitor",
    "mqtt_ha_discovery_prefix": "homeassistant",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "webhook_url": "",
    "notify_on_complete": "false",
    "notify_on_threshold": "false",
    "threshold_download_mbps": "0",
    "threshold_upload_mbps": "0",
    "retention_days": "0",
    "theme": "auto",
    "admin_password": "",
    "gauge_max_mbps": "0",
}

_lock = threading.Lock()


def get_db_path():
    import os
    return os.environ.get("SPEEDGAUGE_DB", "/data/speedgauge.db")


def get_config(db_path: str | None = None) -> dict:
    path = db_path or get_db_path()
    config = dict(DEFAULTS)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        rows = conn.execute("SELECT key, value FROM config").fetchall()
        for k, v in rows:
            config[k] = v
    return config


def set_config(updates: dict, db_path: str | None = None) -> dict:
    path = db_path or get_db_path()
    with _lock:
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            for k, v in updates.items():
                if k in DEFAULTS:
                    conn.execute(
                        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                        (k, str(v)),
                    )
            conn.commit()
    return get_config(path)
