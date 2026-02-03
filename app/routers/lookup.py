"""Urbix API — Lookup Router (PostGIS-first, ArcGIS fallback) + Site Report"""

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
    get_overlays_at_point_db,
    get_zone_at_point_db,
)
from app.services.overlays import get_all_overlays
from app.services.scc_planning import (
    get_full_site_data,
    get_zone,
    get_overlays_grouped,
    get_height_restriction,
    get_transport,
    build_map_urls,
)
from app.services.buildability import (
    get_zone_rules,
    calculate_buildability,
)
from app.services.infrastructure import get_infrastructure
from app.services.da_history import get_da_history
from app.services.flood import get_flood_info
from app.services.constraints import get_constraints
from app.services.ai_summary import generate_ai_summary

router = APIRouter(prefix="/v1", tags=["lookup"])

# Check once at startup
_use_db = None


def use_db() -> bool:
    global _use_db
    if _use_db is None:
        _use_db = db_available()
        if _use_db:
            print("✅ PostGIS database available — using local queries")
        else:
            print("⚠️  PostGIS not available — using live ArcGIS queries")
    return _use_db


# ─── Site Report Endpoint ─────────────────────────────────────────────────────

@router.get("/site-report")
async def site_report(
    lot: Optional[str] = Query(None, description="Lot number"),
    plan: Optional[str] = Query(None, description="Plan number (e.g. RP901532)"),
    address: Optional[str] = Query(None, description="Street address"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lng: Optional[float] = Query(None, description="Longitude"),
):
    """
    Full site report — zone, overlays, buildability, maps.
    
    Queries SCC's REAL ArcGIS services for zone and overlay data.
    Returns everything needed for a professional site report.
    """
    # Step 1: Find the parcel
    parcel_data = None

    if lot and plan:
        if use_db():
            parcel_data = get_parcel_by_lotplan_db(lot, plan)
        if not parcel_data:
            parcel_data = await get_parcel_by_lotplan(lot, plan)
        if not parcel_data:
            raise HTTPException(404, f"No parcel found for Lot {lot} Plan {plan}")

    elif lat is not None and lng is not None:
        if use_db():
            parcel_data = get_parcel_by_point_db(lat, lng)
        if not parcel_data:
            parcel_data = await get_parcel_by_point(lat, lng)
        if not parcel_data:
            raise HTTPException(404, f"No parcel found at {lat}, {lng}")

    elif address:
        if use_db():
            addrs = search_addresses_db(address, limit=1)
        else:
            addrs = await search_addresses(address, limit=1)

        if not addrs:
            raise HTTPException(404, f"Address not found: {address}")

        addr = addrs[0]
        a_lot = addr.get("lot")
        a_plan = addr.get("plan") or addr.get("plan_number")

        if a_lot and a_plan:
            if use_db():
                parcel_data = get_parcel_by_lotplan_db(a_lot, a_plan)
            if not parcel_data:
                parcel_data = await get_parcel_by_lotplan(a_lot, a_plan)

        if not parcel_data and addr.get("lat") and addr.get("lng"):
            if use_db():
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

    # Enrich with tenure if missing
    if not parcel.get("tenure") and parcel.get("lot") and parcel.get("plan"):
        tenure = await get_tenure_for_parcel(parcel["lot"], parcel["plan"])
        if tenure:
            parcel["tenure"] = tenure

    # Step 2: Get centroid for queries
    p_lat, p_lng = _get_point(parcel_data)
    if not p_lat:
        raise HTTPException(500, "Could not determine parcel location")

    # Step 3: Query SCC services (zone, overlays, height, transport, infra, DA, flood, constraints in parallel)
    # Pass parcel geometry to overlays so it uses bbox (catches edge overlays)
    import asyncio
    zone_task = get_zone(p_lat, p_lng)
    overlays_task = get_overlays_grouped(p_lat, p_lng, geometry=geometry)
    height_task = get_height_restriction(p_lat, p_lng)
    transport_task = get_transport(p_lat, p_lng)
    infra_task = get_infrastructure(p_lat, p_lng)
    # Construct lot_plan for service calls
    lot_plan = f"{parcel.get('lot', '')}/{parcel.get('plan', '')}" if parcel.get('lot') and parcel.get('plan') else None
    
    da_task = get_da_history(p_lat, p_lng, geometry=geometry, lot_plan=lot_plan)
    flood_task = get_flood_info(p_lat, p_lng, lot_plan=lot_plan)
    constraints_task = get_constraints(p_lat, p_lng, geometry=geometry)

    zone_data, overlays, height_data, transport, infrastructure, da_history, flood_info, constraints = await asyncio.gather(
        zone_task, overlays_task, height_task, transport_task, infra_task, da_task, flood_task, constraints_task
    )

    # Step 4: Build site info
    addr_data = parcel_data.get("address", {})
    site_info = {
        "address": addr_data.get("address", "") if addr_data else "",
        "lot_plan": f"{parcel.get('lot', '')}/{parcel.get('plan', '')}",
        "lotplan": parcel.get("lotplan", ""),
        "area_sqm": parcel.get("area_sqm"),
        "tenure": parcel.get("tenure", ""),
        "locality": parcel.get("locality", ""),
        "shire_name": parcel.get("shire_name", ""),
        "parcel_type": parcel.get("parcel_type", ""),
        "cover_type": parcel.get("cover_type", ""),
        "centroid": {"lat": p_lat, "lng": p_lng},
    }

    # Step 5: Buildability using REAL zone data
    height_override = None
    if height_data and height_data.get("height_m"):
        height_override = height_data["height_m"]

    rules = get_zone_rules(zone_data["code"]) if zone_data else None
    buildability = calculate_buildability(
        parcel=parcel,
        zone=zone_data,
        rules=rules,
        overlays=overlays,
        height_override=height_override,
    ) if zone_data else None

    # Step 6: Build map URLs
    maps = build_map_urls(p_lat, p_lng, overlays, geometry)

    # Step 7: Generate AI summary
    ai_summary = generate_ai_summary(
        site_info=site_info,
        zone=zone_data,
        overlays=overlays,
        buildability=buildability,
        infrastructure=infrastructure,
        da_history=da_history,
        flood_info=flood_info,
        constraints=constraints,
        height=height_data,
    )

    # Step 8: Compose response
    return {
        "site_info": site_info,
        "zone": zone_data,
        "overlays": overlays,
        "height": height_data,
        "transport": transport,
        "buildability": buildability,
        "infrastructure": infrastructure,
        "da_history": da_history,
        "flood_info": flood_info,
        "constraints": constraints,
        "geometry": geometry,
        "maps": maps,
        "ai_summary": ai_summary,
        "_source": "scc_arcgis",
    }


# ─── Existing Endpoints (unchanged) ──────────────────────────────────────────

@router.get("/lookup")
async def lookup(
    address: Optional[str] = Query(None, description="Street address to look up"),
    lot: Optional[str] = Query(None, description="Lot number"),
    plan: Optional[str] = Query(None, description="Plan number (e.g. RP12345, SP123456)"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lng: Optional[float] = Query(None, description="Longitude"),
):
    """
    Look up a QLD property by address, Lot/Plan, or coordinates.
    
    Returns parcel boundary, metadata, zoning, and overlays.
    Uses local PostGIS when available (fast), falls back to live QLD ArcGIS.
    """
    result = None
    source = "postgis" if use_db() else "arcgis"

    # Option 1: Lot/Plan lookup
    if lot and plan:
        if use_db():
            result = get_parcel_by_lotplan_db(lot, plan)
        if not result:
            result = await get_parcel_by_lotplan(lot, plan)
            source = "arcgis"
        if not result:
            raise HTTPException(404, f"No parcel found for Lot {lot} Plan {plan}")

    # Option 2: Coordinate lookup
    elif lat is not None and lng is not None:
        if use_db():
            result = get_parcel_by_point_db(lat, lng)
        if not result:
            result = await get_parcel_by_point(lat, lng)
            source = "arcgis"
        if not result:
            raise HTTPException(404, f"No parcel found at {lat}, {lng}")

    # Option 3: Address lookup
    elif address:
        if use_db():
            addrs = search_addresses_db(address, limit=1)
        else:
            addrs = await search_addresses(address, limit=1)
        
        if not addrs:
            raise HTTPException(404, f"Address not found: {address}")
        
        addr = addrs[0]
        
        a_lot = addr.get("lot")
        a_plan = addr.get("plan") or addr.get("plan_number")
        
        if a_lot and a_plan:
            if use_db():
                result = get_parcel_by_lotplan_db(a_lot, a_plan)
            if not result:
                result = await get_parcel_by_lotplan(a_lot, a_plan)
                source = "arcgis"
        
        if not result and addr.get("lat") and addr.get("lng"):
            if use_db():
                result = get_parcel_by_point_db(addr["lat"], addr["lng"])
            if not result:
                result = await get_parcel_by_point(addr["lat"], addr["lng"])
                source = "arcgis"
        
        if result:
            result["address"] = addr
        else:
            raise HTTPException(404, f"Found address but no parcel: {address}")
    else:
        raise HTTPException(400, "Provide one of: address, lot+plan, or lat+lng")

    # Enrich with tenure if missing
    parcel = result.get("parcel", {})
    if not parcel.get("tenure") and parcel.get("lot") and parcel.get("plan"):
        tenure = await get_tenure_for_parcel(parcel["lot"], parcel["plan"])
        if tenure:
            result["parcel"]["tenure"] = tenure

    # Add zoning + overlays
    p_lat, p_lng = _get_point(result)
    
    if use_db():
        if p_lat and p_lng:
            zone = get_zone_at_point_db(p_lat, p_lng)
            if zone:
                result["zoning"] = zone
            
            db_overlays = get_overlays_at_point_db(p_lat, p_lng)
            if db_overlays:
                result["overlays"] = db_overlays

    # Enrich with live overlay data
    if p_lat and p_lng:
        overlay_data = await get_all_overlays(p_lat, p_lng)
        if overlay_data.get("land_use"):
            result["land_use"] = overlay_data["land_use"]
        if overlay_data.get("overlays"):
            existing = result.get("overlays", [])
            result["overlays"] = existing + overlay_data["overlays"]

    # Also add SCC zone data
    if p_lat and p_lng:
        scc_zone = await get_zone(p_lat, p_lng)
        if scc_zone:
            result["scc_zone"] = scc_zone

    result["_source"] = source
    return result


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


@router.get("/search")
async def search(
    q: str = Query(..., min_length=3, description="Search query (min 3 chars)"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
):
    """
    Address autocomplete search.
    Uses PostGIS when available (instant), falls back to live ArcGIS.
    """
    if use_db():
        results = search_addresses_db(q, limit=limit)
    else:
        results = await search_addresses(q, limit=limit)
    
    return {
        "query": q,
        "count": len(results),
        "results": results,
        "_source": "postgis" if use_db() else "arcgis",
    }


@router.get("/stats")
async def stats():
    """Database stats — shows what's synced."""
    if not use_db():
        return {"database": "not available", "source": "arcgis (live)"}
    
    from app.services.db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    
    stats = {}
    for table in ["parcels", "addresses", "zones", "overlays"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        stats[table] = cur.fetchone()[0]
    
    cur.execute("SELECT * FROM sync_log ORDER BY completed_at DESC LIMIT 5")
    cols = [d[0] for d in cur.description]
    logs = [dict(zip(cols, row)) for row in cur.fetchall()]
    
    return {
        "database": "postgis",
        "counts": stats,
        "recent_syncs": logs,
    }
