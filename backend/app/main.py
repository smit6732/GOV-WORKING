import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .seed import run_seed
from .routers import auth, cameras, stats, health, coverage, audit, stations

logging.basicConfig(level=logging.INFO)

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


@app.on_event("startup")
def on_startup():
    run_seed()


@app.get("/")
def root():
    return {"status": "ok", "service": "Gujarat CCTV GIS Registry API"}


@app.get("/healthz")
def healthz():
    return {"status": "healthy"}
