"""FastAPI API routes."""
import csv
import hashlib
import io
import os
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from config import get_config, set_config
from database import (
    get_results, get_latest, get_result_by_id, delete_result,
    get_stats, get_result_count,
)
from speedtest_runner import get_status, list_servers
from scheduler import run_test_now, reschedule
from mqtt_ha import reconnect

router = APIRouter(prefix="/api")

# Session tokens: token -> expiry timestamp
_sessions: dict[str, float] = {}
SESSION_TTL = 2592000  # 30 days


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _require_admin(request: Request):
    """Dependency that checks admin auth. No-op if no password is set."""
    config = get_config()
    admin_pw = config.get("admin_password", "").strip()
    if not admin_pw:
        return  # No password set, allow all

    token = request.cookies.get("sm_session") or request.headers.get("X-Session-Token")
    if not token or token not in _sessions or _sessions[token] < time.time():
        _sessions.pop(token, None)
        raise HTTPException(401, "Authentication required")


@router.post("/auth/login")
def api_login(body: dict):
    config = get_config()
    admin_pw = config.get("admin_password", "").strip()
    if not admin_pw:
        raise HTTPException(400, "No admin password configured")

    password = body.get("password", "")
    if _hash_password(password) != _hash_password(admin_pw):
        raise HTTPException(401, "Invalid password")

    token = secrets.token_hex(32)
    _sessions[token] = time.time() + SESSION_TTL
    # Clean expired sessions
    now = time.time()
    expired = [k for k, v in _sessions.items() if v < now]
    for k in expired:
        del _sessions[k]

    return {"ok": True, "token": token}


@router.post("/auth/logout")
def api_logout(request: Request):
    token = request.cookies.get("sm_session") or request.headers.get("X-Session-Token")
    _sessions.pop(token, None)
    return {"ok": True}


@router.get("/auth/status")
def api_auth_status(request: Request):
    config = get_config()
    demo = os.environ.get("SPEEDGAUGE_DEMO", "").lower() in ("true", "1")
    admin_pw = config.get("admin_password", "").strip()
    if not admin_pw:
        return {"protected": False, "authenticated": True, "demo": demo}

    token = request.cookies.get("sm_session") or request.headers.get("X-Session-Token")
    authenticated = bool(token and token in _sessions and _sessions.get(token, 0) >= time.time())
    return {"protected": True, "authenticated": authenticated, "demo": demo}


@router.get("/results")
def api_get_results(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
    sort_by: str = Query("timestamp"),
    sort_dir: str = Query("desc"),
):
    return get_results(limit=limit, offset=offset, from_ts=from_ts, to_ts=to_ts,
                       sort_by=sort_by, sort_dir=sort_dir)


@router.get("/results/latest")
def api_get_latest():
    result = get_latest()
    if not result:
        raise HTTPException(404, "No results yet")
    return result


@router.get("/results/{result_id}")
def api_get_result(result_id: int):
    result = get_result_by_id(result_id)
    if not result:
        raise HTTPException(404, "Result not found")
    return result


@router.delete("/results/{result_id}")
def api_delete_result(result_id: int, _=Depends(_require_admin)):
    if not delete_result(result_id):
        raise HTTPException(404, "Result not found")
    return {"ok": True}


@router.get("/stats")
def api_get_stats(period: str = Query("24h")):
    return get_stats(period=period)


@router.get("/count")
def api_get_count():
    return {"count": get_result_count()}


@router.post("/speedtest/run")
def api_run_test():
    status = get_status()
    if status["running"]:
        raise HTTPException(409, "Test already running")
    run_test_now()
    return {"ok": True, "message": "Test started"}


@router.get("/speedtest/status")
def api_get_status():
    return get_status()


@router.get("/servers")
def api_get_servers():
    return list_servers()


@router.get("/config")
def api_get_config(_=Depends(_require_admin)):
    config = get_config()
    # Mask sensitive values
    safe = dict(config)
    for key in ("mqtt_pass", "telegram_bot_token", "admin_password"):
        if safe.get(key):
            safe[key] = "••••••••"
    return safe


@router.put("/config")
def api_set_config(updates: dict, _=Depends(_require_admin)):
    if os.environ.get("SPEEDGAUGE_DEMO", "").lower() in ("true", "1"):
        updates.pop("admin_password", None)
    if "interval_minutes" in updates:
        updates["interval_minutes"] = str(max(10, int(updates["interval_minutes"])))
    old_config = get_config()
    new_config = set_config(updates)

    # Reschedule if interval changed
    old_interval = int(old_config.get("interval_minutes", 60))
    new_interval = int(new_config.get("interval_minutes", 60))
    if new_interval != old_interval:
        reschedule(new_interval)

    # Reconnect MQTT if broker settings changed
    mqtt_keys = {"mqtt_broker", "mqtt_port", "mqtt_user", "mqtt_pass",
                 "mqtt_topic_prefix", "mqtt_ha_discovery_prefix"}
    if any(old_config.get(k) != new_config.get(k) for k in mqtt_keys):
        from scheduler import run_test_now as _trigger
        reconnect(new_config, on_command=lambda cmd: _trigger() if cmd == "run_test" else None)

    return new_config


@router.get("/export")
def api_export(
    format: str = Query("csv"),
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
):
    results = get_results(limit=100000, from_ts=from_ts, to_ts=to_ts)

    if format == "json":
        return results

    # CSV export
    output = io.StringIO()
    if results:
        fields = ["timestamp", "download_mbps", "upload_mbps", "ping_ms",
                  "jitter_ms", "server_name", "isp", "external_ip", "result_url"]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=speedgauge-export.csv"},
    )


@router.get("/gauge-max")
def api_gauge_max():
    """Return recommended gauge max based on average download speed."""
    stats = get_stats(period="7d")
    avg = stats.get("avg_download") or 0
    if avg >= 5000:
        return {"max": 10000}
    elif avg >= 2000:
        return {"max": 5000}
    elif avg >= 500:
        return {"max": 2000}
    elif avg >= 200:
        return {"max": 1000}
    elif avg >= 50:
        return {"max": 500}
    elif avg >= 10:
        return {"max": 100}
    else:
        return {"max": 10000}  # no data yet, default high


@router.get("/health")
def api_health():
    return {"status": "ok"}


@router.get("/version")
def api_version():
    return {"version": "1.0.0"}
