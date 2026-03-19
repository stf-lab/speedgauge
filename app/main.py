"""SpeedGauge — main FastAPI application."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import router as api_router
from config import get_config
from database import init_db
from mqtt_ha import connect as mqtt_connect, disconnect as mqtt_disconnect
from scheduler import start as scheduler_start, stop as scheduler_stop, set_event_loop, run_test_now

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("speed_monitor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SpeedGauge v1.0.0 starting up...")

    init_db()
    logger.info("Database initialized")

    set_event_loop(asyncio.get_event_loop())

    config = get_config()

    # Start MQTT
    def on_mqtt_command(cmd):
        if cmd == "run_test":
            run_test_now()

    mqtt_connect(config, on_command=on_mqtt_command)

    # Start scheduler
    scheduler_start()

    yield

    logger.info("SpeedGauge shutting down...")
    scheduler_stop()
    mqtt_disconnect(config)


app = FastAPI(title="SpeedGauge", version="1.0.0", lifespan=lifespan)

app.include_router(api_router)

# SPA catch-all middleware
static_dir = Path(__file__).parent / "static"


@app.middleware("http")
async def spa_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if (
        response.status_code == 404
        and not path.startswith("/api/")
        and not path.startswith("/assets/")
    ):
        index = static_dir / "index.html"
        if index.is_file():
            return FileResponse(str(index), media_type="text/html")
    return response


if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
