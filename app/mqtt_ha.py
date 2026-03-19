"""MQTT client with Home Assistant auto-discovery."""
import json
import logging
import threading
import time

logger = logging.getLogger("speed_monitor.mqtt")

_client = None
_lock = threading.Lock()


def _get_discovery_configs(prefix: str, topic_prefix: str) -> list[tuple[str, dict]]:
    """Generate HA MQTT auto-discovery config messages."""
    device = {
        "identifiers": ["speed_monitor"],
        "name": "SpeedGauge",
        "manufacturer": "Custom",
        "model": "SpeedGauge",
        "sw_version": "1.0.0",
    }
    state_topic = f"{topic_prefix}/state"
    avail_topic = f"{topic_prefix}/availability"

    sensors = [
        ("download", "Download", "Mbps", "mdi:download-network", "download_mbps", "measurement"),
        ("upload", "Upload", "Mbps", "mdi:upload-network", "upload_mbps", "measurement"),
        ("ping", "Ping", "ms", "mdi:timer-outline", "ping_ms", "measurement"),
        ("jitter", "Jitter", "ms", "mdi:signal-variant", "jitter_ms", "measurement"),
        ("isp", "ISP", None, "mdi:web", "isp", None),
        ("external_ip", "External IP", None, "mdi:ip-network", "external_ip", None),
    ]

    configs = []
    for obj_id, name, unit, icon, value_key, state_class in sensors:
        topic = f"{prefix}/sensor/speed_monitor/{obj_id}/config"
        payload = {
            "name": name,
            "unique_id": f"speed_monitor_{obj_id}",
            "state_topic": state_topic,
            "value_template": f"{{{{ value_json.{value_key} }}}}",
            "icon": icon,
            "device": device,
            "availability_topic": avail_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        if unit:
            payload["unit_of_measurement"] = unit
        if state_class:
            payload["state_class"] = state_class
        configs.append((topic, payload))

    # Binary sensor for test running
    configs.append((
        f"{prefix}/binary_sensor/speed_monitor/test_running/config",
        {
            "name": "Test Running",
            "unique_id": "speed_monitor_test_running",
            "state_topic": f"{topic_prefix}/running",
            "payload_on": "ON",
            "payload_off": "OFF",
            "icon": "mdi:speedometer",
            "device": device,
            "availability_topic": avail_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
        },
    ))

    # Button to trigger test
    configs.append((
        f"{prefix}/button/speed_monitor/run_test/config",
        {
            "name": "Run Speed Test",
            "unique_id": "speed_monitor_run_test",
            "command_topic": f"{topic_prefix}/command",
            "payload_press": "run_test",
            "icon": "mdi:play-circle",
            "device": device,
            "availability_topic": avail_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
        },
    ))

    return configs


def connect(config: dict, on_command=None):
    """Connect to MQTT broker and publish HA discovery."""
    global _client
    broker = config.get("mqtt_broker", "").strip()
    if not broker:
        logger.info("MQTT not configured, skipping")
        return

    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        logger.warning("paho-mqtt not installed")
        return

    port = int(config.get("mqtt_port", 1883))
    user = config.get("mqtt_user", "").strip()
    password = config.get("mqtt_pass", "").strip()
    topic_prefix = config.get("mqtt_topic_prefix", "speed_monitor")
    ha_prefix = config.get("mqtt_ha_discovery_prefix", "homeassistant")

    def on_connect(client, userdata, flags, reason_code, properties=None):
        logger.info("MQTT connected to %s:%d", broker, port)
        # Publish discovery configs
        for topic, payload in _get_discovery_configs(ha_prefix, topic_prefix):
            client.publish(topic, json.dumps(payload), retain=True)
        # Publish availability
        client.publish(f"{topic_prefix}/availability", "online", retain=True)
        # Subscribe to command topic
        client.subscribe(f"{topic_prefix}/command")
        logger.info("HA MQTT discovery published")

    def on_message(client, userdata, msg):
        payload = msg.payload.decode()
        if payload == "run_test" and on_command:
            on_command("run_test")

    def on_disconnect(client, userdata, flags, reason_code, properties=None):
        logger.warning("MQTT disconnected (rc=%s), will reconnect", reason_code)

    with _lock:
        if _client:
            try:
                _client.disconnect()
            except Exception:
                pass

        _client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="speed_monitor")
        _client.on_connect = on_connect
        _client.on_message = on_message
        _client.on_disconnect = on_disconnect

        if user:
            _client.username_pw_set(user, password)

        _client.will_set(f"{topic_prefix}/availability", "offline", retain=True)

        try:
            _client.connect(broker, port, keepalive=60)
            _client.loop_start()
        except Exception as e:
            logger.error("MQTT connection failed: %s", e)
            _client = None


def publish_state(result: dict, config: dict):
    """Publish test result to MQTT state topic."""
    with _lock:
        if not _client:
            return
    topic_prefix = config.get("mqtt_topic_prefix", "speed_monitor")
    payload = {
        "download_mbps": result["download_mbps"],
        "upload_mbps": result["upload_mbps"],
        "ping_ms": result["ping_ms"],
        "jitter_ms": result.get("jitter_ms"),
        "isp": result.get("isp"),
        "external_ip": result.get("external_ip"),
        "server_name": result.get("server_name"),
        "result_url": result.get("result_url"),
        "timestamp": result["timestamp"],
    }
    _client.publish(f"{topic_prefix}/state", json.dumps(payload), retain=True)


def publish_running(running: bool, config: dict):
    """Publish test running state."""
    with _lock:
        if not _client:
            return
    topic_prefix = config.get("mqtt_topic_prefix", "speed_monitor")
    _client.publish(f"{topic_prefix}/running", "ON" if running else "OFF", retain=True)


def disconnect(config: dict):
    """Gracefully disconnect from MQTT."""
    global _client
    with _lock:
        if _client:
            topic_prefix = config.get("mqtt_topic_prefix", "speed_monitor")
            try:
                _client.publish(f"{topic_prefix}/availability", "offline", retain=True)
                _client.loop_stop()
                _client.disconnect()
            except Exception:
                pass
            _client = None


def reconnect(config: dict, on_command=None):
    """Reconnect with new config."""
    disconnect(config)
    connect(config, on_command)
