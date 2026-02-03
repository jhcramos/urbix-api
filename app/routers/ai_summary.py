"""Urbix API — AI Summary Router"""

import asyncio
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.qld_spatial import (
    search_addresses,
    get_parcel_by_lotplan,
    get_parcel_by_point,
    get_tenure_for_parcel,
)
from app.services.db import (
    db_available,
    search_addresses_db,
    get_parcel_by_lotplan_db,
    get_parcel_by_point_db,
)
from app.services.scc_planning import (
    get_zone,
    get_overlays_grouped,
    get_height_restriction,
    get_transport,
    build_map_urls,
)
from app.services.buildability import get_zone_rules, calculate_buildability
from app.services.infrastructure import get_infrastructure
from app.services.da_history import get_da_history
from app.services.flood import get_flood_info
from app.services.constraints import get_constraints
from app.services.ai_summary import generate_ai_summary

router = APIRouter(prefix="/v1", tags=["ai-summary"])


def _get_point(result: dict) -> tuple:
    """Extract a lat/lng from the result (address or geometry centroid)."""
    addr = result.get("address", {})
    if addr and addr.get("lat"):
        return addr["lat"], addr["lng"]
    geom = result.get("geometry")
    if geom and geom.get("type") == "Polygon":
        coords = geom["coordinates"][0]
        avg_lng = sum(c[0] for c in coords) / len(coords)
        avg_lat = sum(c[1] for c in coords) / len(coords)
        return avg_lat, avg_lng
    return None, None


@router.get("/ai-summary")
async def ai_summary(
    lot: Optional[str] = Query(None, description="Lot number"),
    plan: Optional[str] = Query(None, description="Plan number (e.g. RP901532)"),
    address: Optional[str] = Query(None, description="Street address"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lng: Optional[float] = Query(None, description="Longitude"),
):
    """
    AI-powered site analysis summary.

    Compiles data from all services into a structured analysis with:
    - Constraints score (1-100)
    - Plain-English summary
    - Strengths & risks
    - Development potential
    - Precedent analysis

    Works with address, lot/plan, or coordinates.
    """
    # Step 1: Find the parcel (same logic as site-report)
    parcel_data = None

    if lot and plan:
        if db_available():
            parcel_data = get_parcel_by_lotplan_db(lot, plan)
        if not parcel_data:
            parcel_data = await get_parcel_by_lotplan(lot, plan)
        if not parcel_data:
            raise HTTPException(404, f"No parcel found for Lot {lot} Plan {plan}")

    elif lat is not None and lng is not None:
        if db_available():
            parcel_data = get_parcel_by_point_db(lat, lng)
        if not parcel_data:
            parcel_data = await get_parcel_by_point(lat, lng)
        if not parcel_data:
            raise HTTPException(404, f"No parcel found at {lat}, {lng}")

    elif address:
        if db_available():
            addrs = search_addresses_db(address, limit=1)
        else:
            addrs = await search_addresses(address, limit=1)

        if not addrs:
            raise HTTPException(404, f"Address not found: {address}")

        addr = addrs[0]
        a_lot = addr.get("lot")
        a_plan = addr.get("plan") or addr.get("plan_number")

        if a_lot and a_plan:
            if db_available():
                parcel_data = get_parcel_by_lotplan_db(a_lot, a_plan)
            if not parcel_data:
                parcel_data = await get_parcel_by_lotplan(a_lot, a_plan)

        if not parcel_data and addr.get("lat") and addr.get("lng"):
            if db_available():
                parcel_data = get_parcel_by_point_db(addr["lat"], addr["lng"])
            if not parcel_data:
                parcel_data = await get_parcel_by_point(addr["lat"], addr["lng"])

        if parcel_data:
            parcel_data["address"] = addr
        else:
            raise HTTPException(404, f"Found address but no parcel: {address}")
    else:
        raise HTTPException(400, "Provide one of: lot+plan, address, or lat+lng")

    parcel = parcel_data.get("parcel", {})
    geometry = parcel_data.get("geometry")

    # Enrich with tenure
    if not parcel.get("tenure") and parcel.get("lot") and parcel.get("plan"):
        tenure = await get_tenure_for_parcel(parcel["lot"], parcel["plan"])
        if tenure:
            parcel["tenure"] = tenure

    # Step 2: Get centroid
    p_lat, p_lng = _get_point(parcel_data)
    if not p_lat:
        raise HTTPException(500, "Could not determine parcel location")

    # Step 3: Query all services in parallel
    lot_plan = f"{parcel.get('lot', '')}/{parcel.get('plan', '')}" if parcel.get('lot') and parcel.get('plan') else None

    zone_data, overlays, height_data, infrastructure, da_history, flood_info, constraints_data = await asyncio.gather(
        get_zone(p_lat, p_lng),
        get_overlays_grouped(p_lat, p_lng, geometry=geometry),
        get_height_restriction(p_lat, p_lng),
        get_infrastructure(p_lat, p_lng),
        get_da_history(p_lat, p_lng, geometry=geometry, lot_plan=lot_plan),
        get_flood_info(p_lat, p_lng, lot_plan=lot_plan),
        get_constraints(p_lat, p_lng, geometry=geometry),
    )

    # Step 4: Calculate buildability
    height_override = height_data.get("height_m") if height_data else None
    rules = get_zone_rules(zone_data["code"]) if zone_data else None
    buildability = calculate_buildability(
        parcel=parcel,
        zone=zone_data,
        rules=rules,
        overlays=overlays,
        height_override=height_override,
    ) if zone_data else None

    # Step 5: Build site info
    addr_data = parcel_data.get("address", {})
    site_info = {
        "address": addr_data.get("address", "") if addr_data else "",
        "lot_plan": lot_plan or "",
        "area_sqm": parcel.get("area_sqm"),
        "tenure": parcel.get("tenure", ""),
        "locality": parcel.get("locality", ""),
        "centroid": {"lat": p_lat, "lng": p_lng},
    }

    # Step 6: Generate AI summary
    summary = generate_ai_summary(
        site_info=site_info,
        zone=zone_data,
        overlays=overlays,
        buildability=buildability,
        infrastructure=infrastructure,
        da_history=da_history,
        flood_info=flood_info,
        constraints=constraints_data,
        height=height_data,
    )

    return summary
