"""Ookla Speedtest CLI wrapper with progress streaming."""
import json
import subprocess
import threading
from datetime import datetime, timezone

# Global test state
_state = {
    "running": False,
    "phase": "idle",      # idle, ping, download, upload, complete, error
    "progress": 0.0,      # 0-100
    "download_mbps": 0.0,
    "upload_mbps": 0.0,
    "ping_ms": 0.0,
}
_state_lock = threading.Lock()


def get_status() -> dict:
    with _state_lock:
        return dict(_state)


def _update_state(**kwargs):
    with _state_lock:
        _state.update(kwargs)


def list_servers() -> list[dict]:
    """List nearby Ookla servers."""
    try:
        proc = subprocess.run(
            ["speedtest", "--accept-license", "--accept-gdpr", "--servers", "--format=json"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return []
        data = json.loads(proc.stdout)
        servers = data.get("servers", [])
        return [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "host": s.get("host"),
                "location": s.get("location"),
                "country": s.get("country"),
            }
            for s in servers
        ]
    except Exception:
        return []


def run_speedtest(server_id: str | None = None) -> dict:
    """Run a speedtest and return parsed results. Updates global state for progress."""
    with _state_lock:
        if _state["running"]:
            raise RuntimeError("Test already running")
        _state.update(running=True, phase="starting", progress=0,
                      download_mbps=0, upload_mbps=0, ping_ms=0)

    try:
        ts_start = datetime.now(timezone.utc).isoformat()
        cmd = ["speedtest", "--accept-license", "--accept-gdpr",
               "--format=json", "--progress=yes"]
        if server_id:
            cmd.extend(["--server-id", str(server_id)])

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        # With --progress=yes, ALL output (progress + result) goes to stdout
        # as newline-delimited JSON. Read line by line.
        result_data = None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                ptype = obj.get("type", "")
                if ptype == "download":
                    bps = obj.get("download", {}).get("bandwidth", 0)
                    _update_state(
                        phase="download",
                        progress=obj.get("download", {}).get("progress", 0) * 100,
                        download_mbps=round(bps * 8 / 1_000_000, 2),
                    )
                elif ptype == "upload":
                    bps = obj.get("upload", {}).get("bandwidth", 0)
                    _update_state(
                        phase="upload",
                        progress=obj.get("upload", {}).get("progress", 0) * 100,
                        upload_mbps=round(bps * 8 / 1_000_000, 2),
                    )
                elif ptype == "ping":
                    latency = obj.get("ping", {}).get("latency", 0)
                    _update_state(phase="ping", progress=50, ping_ms=round(latency, 1))
                elif ptype == "result":
                    result_data = obj
            except (json.JSONDecodeError, KeyError):
                pass

        proc.wait(timeout=120)

        if proc.returncode != 0:
            stderr_out = proc.stderr.read()
            raise RuntimeError(f"Speedtest failed (exit {proc.returncode}): {stderr_out}")

        if not result_data:
            raise RuntimeError("No result data received from speedtest")

        data = result_data
        ts = ts_start

        download_bps = data.get("download", {}).get("bandwidth", 0)
        upload_bps = data.get("upload", {}).get("bandwidth", 0)

        result = {
            "timestamp": ts,
            "download_mbps": round(download_bps * 8 / 1_000_000, 2),
            "upload_mbps": round(upload_bps * 8 / 1_000_000, 2),
            "ping_ms": round(data.get("ping", {}).get("latency", 0), 2),
            "jitter_ms": round(data.get("ping", {}).get("jitter", 0), 2),
            "packet_loss": data.get("packetLoss", None),
            "server_id": data.get("server", {}).get("id"),
            "server_name": data.get("server", {}).get("name"),
            "server_host": data.get("server", {}).get("host"),
            "isp": data.get("isp"),
            "external_ip": data.get("interface", {}).get("externalIp"),
            "result_url": data.get("result", {}).get("url"),
            "raw_json": json.dumps(data),
        }

        _update_state(
            phase="complete",
            progress=100,
            download_mbps=result["download_mbps"],
            upload_mbps=result["upload_mbps"],
        )

        return result

    except Exception as e:
        _update_state(phase="error", progress=0)
        raise
    finally:
        _update_state(running=False)
