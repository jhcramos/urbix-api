"""Urbix API — Buildability Router (now using REAL SCC zone data)"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.db import get_parcel_by_lotplan_db, get_parcel_by_point_db, db_available
from app.services.qld_spatial import get_parcel_by_lotplan, get_parcel_by_point, search_addresses
from app.services.scc_planning import get_zone, get_height_restriction, get_overlays_grouped
from app.services.buildability import (
    get_zone_rules,
    calculate_buildability,
    # Legacy fallbacks
    estimate_zone_from_land_use,
    get_planning_rules,
)
from app.services.overlays import get_all_overlays

router = APIRouter(prefix="/v1", tags=["buildability"])


@router.get("/buildability")
async def buildability(
    address: Optional[str] = Query(None, description="Street address"),
    lot: Optional[str] = Query(None, description="Lot number"),
    plan: Optional[str] = Query(None, description="Plan number"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lng: Optional[float] = Query(None, description="Longitude"),
    zone: Optional[str] = Query(None, description="Override zone (e.g. 'Rural Zone')"),
):
    """
    What can you build on this lot?
    
    NOW uses REAL zone data from SCC's ArcGIS services instead of guessing.
    Returns planning rules, buildable envelope, max dwellings,
    subdivision potential, accepted/assessable uses, and constraints.
    """
    # Step 1: Find the parcel
    parcel_data = None

    if lot and plan:
        if db_available():
            parcel_data = get_parcel_by_lotplan_db(lot, plan)
        if not parcel_data:
            parcel_data = await get_parcel_by_lotplan(lot, plan)
    elif lat is not None and lng is not None:
        if db_available():
            parcel_data = get_parcel_by_point_db(lat, lng)
        if not parcel_data:
            parcel_data = await get_parcel_by_point(lat, lng)
    elif address:
        addrs = await search_addresses(address, limit=1)
        if not addrs:
            if db_available():
                from app.services.db import search_addresses_db
                addrs = search_addresses_db(address, limit=1)
        if addrs:
            addr = addrs[0]
            a_lot = addr.get("lot")
            a_plan = addr.get("plan")
            if a_lot and a_plan and db_available():
                parcel_data = get_parcel_by_lotplan_db(a_lot, a_plan)
            if not parcel_data and a_lot and a_plan:
                parcel_data = await get_parcel_by_lotplan(a_lot, a_plan)
            if not parcel_data and addr.get("lat") and addr.get("lng"):
                if db_available():
                    parcel_data = get_parcel_by_point_db(addr["lat"], addr["lng"])
                if not parcel_data:
                    parcel_data = await get_parcel_by_point(addr["lat"], addr["lng"])
    else:
        raise HTTPException(400, "Provide one of: address, lot+plan, or lat+lng")

    if not parcel_data:
        raise HTTPException(404, "Parcel not found")

    parcel = parcel_data.get("parcel", {})

    # Step 2: Get lat/lng for overlay queries
    geom = parcel_data.get("geometry")
    p_lat, p_lng = lat, lng
    if not p_lat and geom:
        if geom.get("type") == "Polygon":
            coords = geom["coordinates"][0]
            p_lng = sum(c[0] for c in coords) / len(coords)
            p_lat = sum(c[1] for c in coords) / len(coords)

    # Step 3: Get REAL zone from SCC
    zone_data = None
    zone_source = "unknown"

    if zone:
        # User override
        zone_data = {"code": zone, "category": "User Override", "label": zone}
        zone_source = "user_override"
    elif p_lat and p_lng:
        zone_data = await get_zone(p_lat, p_lng)
        zone_source = "scc_arcgis"

    if not zone_data:
        # Fallback: try land use estimation
        overlay_data = await get_all_overlays(p_lat, p_lng) if p_lat else {}
        lu = overlay_data.get("land_use")
        if lu:
            zone_map = estimate_zone_from_land_use(lu.get("alum_code", ""))
            if zone_map:
                zone_data = {
                    "code": zone_map["likely_zone"],
                    "category": "Estimated",
                    "label": zone_map["likely_zone"],
                }
                zone_source = f"estimated from land use ({lu.get('secondary', '')})"

    if not zone_data:
        raise HTTPException(
            404,
            "Could not determine planning zone. "
            "This property may be outside Sunshine Coast Council area. "
            "Try passing ?zone=Rural+Zone to override.",
        )

    # Step 4: Get REAL height from SCC
    height_override = None
    if p_lat and p_lng:
        height_data = await get_height_restriction(p_lat, p_lng)
        if height_data and height_data.get("height_m"):
            height_override = height_data["height_m"]

    # Step 5: Get overlays from SCC
    overlays = []
    if p_lat and p_lng:
        overlays = await get_overlays_grouped(p_lat, p_lng)

    # Step 6: Get rules and calculate
    rules = get_zone_rules(zone_data["code"])
    result = calculate_buildability(
        parcel=parcel,
        zone=zone_data,
        rules=rules,
        overlays=overlays,
        height_override=height_override,
    )

    # Add metadata
    result["parcel"] = parcel
    result["zone_detection"] = {
        "zone": zone_data["code"],
        "source": zone_source,
        "confidence": 1.0 if zone_source == "scc_arcgis" else 0.6,
    }
    result["geometry"] = geom

    return result
