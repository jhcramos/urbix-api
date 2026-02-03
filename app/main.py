"""
Urbix Cadastre & Planning API
Queensland property data — parcels, zoning, overlays, buildability.

"What can I build on this lot?"
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.routers import lookup, buildability, ai_summary

app = FastAPI(
    title="Urbix API",
    description=(
        "Queensland Cadastre & Planning API. "
        "Look up any QLD property — parcel boundaries, zoning, overlays, "
        "and buildability rules. Powered by QLD Government open data."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow all for dev, lock down later
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lookup.router)
app.include_router(buildability.router)
app.include_router(ai_summary.router)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def root():
    """Serve the map viewer UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api")
async def api_info():
    return {
        "name": "Urbix API",
        "version": "0.1.0",
        "description": "Queensland Cadastre & Planning API",
        "docs": "/docs",
        "endpoints": {
            "lookup": "/v1/lookup?address=15+Abbott+St+Camp+Hill+QLD",
            "lookup_lotplan": "/v1/lookup?lot=3&plan=RP12345",
            "lookup_coords": "/v1/lookup?lat=-27.47&lng=153.02",
            "search": "/v1/search?q=Abbott+St+Camp+Hill",
            "site_report": "/v1/site-report?address=134+Kirbys+Rd+Montville",
            "ai_summary": "/v1/ai-summary?address=134+Kirbys+Rd+Montville",
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
