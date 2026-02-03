"""QLD Overlay Services — Zoning, Flood, Development Areas."""

import httpx
from typing import Optional

BASE = "https://spatial-gis.information.qld.gov.au/arcgis/rest/services"

# Service URLs
LAND_USE_URL = f"{BASE}/PlanningCadastre/LandUse/FeatureServer/0"
FLOOD_COMPREHENSIVE_URL = f"{BASE}/FloodCheck/ComprehensiveStudies/MapServer"
FLOOD_BASIC_URL = f"{BASE}/FloodCheck/BasicStudies/MapServer"
PDA_URL = f"{BASE}/PlanningCadastre/PriorityDevelopmentAreas/MapServer/10"
SDA_URL = f"{BASE}/PlanningCadastre/StateDevelopmentAreas/MapServer"
COASTAL_URL = f"{BASE}/PlanningCadastre/CoastalManagement/MapServer"


async def _query_point(url: str, lat: float, lng: float, out_fields: str = "*") -> list:
    """Query a layer with a point geometry."""
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": 4326,
        "outFields": out_fields,
        "returnGeometry": "false",
        "f": "json",
        "resultRecordCount": 10,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{url}/query", params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("features", [])
        except Exception:
            return []


async def _identify_point(url: str, lat: float, lng: float) -> list:
    """Identify all layers at a point (for MapServers without query)."""
    params = {
        "geometry": f'{{"x":{lng},"y":{lat},"spatialReference":{{"wkid":4326}}}}',
        "geometryType": "esriGeometryPoint",
        "tolerance": 0,
        "mapExtent": f"{lng-0.01},{lat-0.01},{lng+0.01},{lat+0.01}",
        "imageDisplay": "400,400,96",
        "layers": "all",
        "returnGeometry": "false",
        "f": "json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{url}/identify", params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except Exception:
            return []


async def get_land_use(lat: float, lng: float) -> Optional[dict]:
    """Get ALUMC land use classification at a point."""
    features = await _query_point(LAND_USE_URL, lat, lng, 
        "primary_,secondary,tertiary,alum_code,qlump_code,year")
    
    if not features:
        return None
    
    attrs = features[0].get("attributes", {})
    return {
        "primary": attrs.get("primary_", ""),
        "secondary": attrs.get("secondary", ""),
        "tertiary": attrs.get("tertiary", ""),
        "alum_code": attrs.get("alum_code", ""),
        "qlump_code": attrs.get("qlump_code"),
        "year": attrs.get("year"),
    }


async def get_flood_info(lat: float, lng: float) -> list:
    """Get flood study information at a point."""
    results = []
    
    # Comprehensive studies
    items = await _identify_point(FLOOD_COMPREHENSIVE_URL, lat, lng)
    for item in items:
        attrs = item.get("attributes", {})
        if attrs.get("StudyName"):
            results.append({
                "type": "Flood - Comprehensive Study",
                "name": attrs.get("StudyName", ""),
                "area": attrs.get("studyArea", ""),
                "lga": attrs.get("LGA", ""),
                "purpose": attrs.get("purpose", "")[:200],
            })
    
    # Basic studies
    items = await _identify_point(FLOOD_BASIC_URL, lat, lng)
    for item in items:
        attrs = item.get("attributes", {})
        if attrs.get("StudyName"):
            results.append({
                "type": "Flood - Basic Study",
                "name": attrs.get("StudyName", ""),
                "area": attrs.get("studyArea", ""),
                "lga": attrs.get("LGA", ""),
            })
    
    return results


async def get_priority_development_area(lat: float, lng: float) -> Optional[dict]:
    """Check if point is in a Priority Development Area."""
    features = await _query_point(PDA_URL, lat, lng)
    if not features:
        return None
    
    attrs = features[0].get("attributes", {})
    return {
        "type": "Priority Development Area",
        "name": attrs.get("PDA_NAME", attrs.get("Name", "")),
    }


async def get_all_overlays(lat: float, lng: float) -> dict:
    """Get ALL overlay information for a point — the full picture."""
    import asyncio
    
    # Run all queries in parallel
    land_use_task = get_land_use(lat, lng)
    flood_task = get_flood_info(lat, lng)
    pda_task = get_priority_development_area(lat, lng)
    
    land_use, floods, pda = await asyncio.gather(
        land_use_task, flood_task, pda_task
    )
    
    result = {}
    
    if land_use:
        result["land_use"] = land_use
    
    overlays = []
    if floods:
        overlays.extend(floods)
    if pda:
        overlays.append(pda)
    
    if overlays:
        result["overlays"] = overlays
    
    return result
