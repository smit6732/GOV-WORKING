import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import SessionLocal
from .seed import run_seed
from .routers import auth, cameras, stats, health, coverage, audit, stations
from .routers import feeds, anpr_search, tags
from . import anpr_client, es_client
from .auth import decode_access_token
from . import models
from .workers import consumer_a
from .ws_manager import manager as ws_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(
    title="Gujarat CCTV GIS Registry",
    description=(
        "Centralised CCTV Registry & GIS Mapping API — metadata and asset visibility "
        "layer only. Not a live surveillance system: no RTSP streaming, video storage, "
        "or facial recognition is implemented."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cameras.router)
app.include_router(stats.router)
app.include_router(health.router)
app.include_router(coverage.router)
app.include_router(audit.router)
app.include_router(stations.router)
app.include_router(feeds.router)
app.include_router(anpr_search.router)
app.include_router(tags.router)


@app.on_event("startup")
async def on_startup():
    run_seed()
    es_client.ensure_index()
    consumer_a.start()

    db = SessionLocal()
    try:
        await anpr_client.start_all_streams(db)
    except Exception as e:
        logger.warning("Could not auto-start ANPR streams at boot (service may not be up yet): %s", e)
    finally:
        db.close()


@app.on_event("shutdown")
def on_shutdown():
    consumer_a.stop()


@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket, token: str = ""):
    db = SessionLocal()
    try:
        payload = decode_access_token(token)
        user = db.query(models.User).filter(models.User.id == int(payload.get("sub"))).first()
        if user is None or not user.is_active:
            await websocket.close(code=4401)
            return
        department = user.department if user.role == models.UserRole.department_admin else None
    except Exception:
        await websocket.close(code=4401)
        return
    finally:
        db.close()

    await ws_manager.connect(websocket, department)
    try:
        while True:
            await websocket.receive_text()  # keep the connection open; client doesn't need to send anything
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


@app.get("/")
def root():
    return {"status": "ok", "service": "Gujarat CCTV GIS Registry API"}


@app.get("/healthz")
def healthz():
    return {"status": "healthy"}
