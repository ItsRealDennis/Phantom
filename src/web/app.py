"""FastAPI application — web server with scheduler lifecycle."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.automation.scheduler import start_scheduler, stop_scheduler
from src.web.routes import router

STATIC_DIR = Path(__file__).parent / "static"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start scheduler on boot, stop on shutdown."""
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Phantom",
    description="Paper trading signal validation system",
    lifespan=lifespan,
)

# Serve static CSS/JS files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(router)
