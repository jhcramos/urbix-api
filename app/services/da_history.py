"""
Development Applications Service — Query SCC for DA history and building applications.

Checks development applications both on the parcel and nearby within 500m
to provide context on development activity in the area.
"""

import asyncio
import httpx
from typing import Optional, List, Dict


# ─── Service URLs ─────────────────────────────────────────────────────────────

SCC_DA_URL = (
    "https://geopublic.scc.qld.gov.au/arcgis/rest/services/"
    "PlanningCadastre/Applications_SCRC/MapServer"
)

# Layer IDs
DA_IN_PROGRESS = 0
DA_DECIDED_PAST = 1
BUILDING_IN_PROGRESS = 2
BUILDING_DECIDED_PAST = 3


async def _query_da_layer(
    layer_id: int,
    lat: float,
    lng: float,
    geometry: dict = None,
    distance_m: int = 100,
    timeout: float = 15.0,
) -> list:
    """Query a DA layer with either tight bbox or distance buffer."""
    url = f"{SCC_DA_URL}/{layer_id}/query"
    
    if distance_m > 200:
        # For nearby queries (500m), use point + distance
        params = {
            "geometry": f"{lng},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "distance": distance_m,
            "units": "esriSRUnit_Meter",
            "inSR": 4326,
            "outSR": 4326,
            "outFields": "ram_id,description,category_desc,decision,progress,assessment_level,d_date_rec,d_decision_made,land_parcel_relationship",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 100,
        }
    else:
        # For on-parcel queries, use envelope geometry if available
        if geometry and geometry.get("type") == "Polygon":
            coords = geometry["coordinates"][0]
            min_lng = min(c[0] for c in coords)
            max_lng = max(c[0] for c in coords)
            min_lat = min(c[1] for c in coords)
            max_lat = max(c[1] for c in coords)
            
            # Expand bbox slightly for edge cases
            buffer = 0.0005  # ~50m
            envelope = f"{min_lng-buffer},{min_lat-buffer},{max_lng+buffer},{max_lat+buffer}"
        else:
            # Fallback to small buffer around point
            buffer = 0.0005  # ~50m
            envelope = f"{lng-buffer},{lat-buffer},{lng+buffer},{lat+buffer}"
        
        params = {
            "geometry": envelope,
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": 4326,
            "outSR": 4326,
            "outFields": "ram_id,description,category_desc,decision,progress,assessment_level,d_date_rec,d_decision_made,land_parcel_relationship",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 50,
        }

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("features", [])
        except Exception as e:
            print(f"⚠️  DA query failed (layer {layer_id}): {e}")
            return []


def _process_da_features(features: List[Dict]) -> List[Dict]:
    """Process DA features and clean up the data."""
    processed = []
    
    for feat in features:
        attrs = feat.get("attributes", {})
        
        # Clean and structure the data
        da = {
            "ram_id": attrs.get("ram_id"),
            "description": attrs.get("description", "").strip(),
            "category": attrs.get("category_desc", "").strip(),
            "decision": attrs.get("decision", "").strip(),
            "progress": attrs.get("progress", "").strip(),
            "assessment_level": attrs.get("assessment_level", "").strip(),
            "date_received": _format_date(attrs.get("d_date_rec")),
            "date_decided": _format_date(attrs.get("d_decision_made")),
            "land_parcel_relationship": attrs.get("land_parcel_relationship", "").strip(),
        }
        
        # Skip if no meaningful data
        if not da["ram_id"] and not da["description"]:
            continue
            
        processed.append(da)
    
    return processed


def _format_date(timestamp) -> Optional[str]:
    """Convert ArcGIS timestamp to readable date."""
    if not timestamp:
        return None
    
    try:
        # ArcGIS timestamps are in milliseconds
        from datetime import datetime
        dt = datetime.fromtimestamp(timestamp / 1000)
        return dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError, OSError):
        return None


async def get_da_history(lat: float, lng: float, geometry: dict = None, lot_plan: str = None) -> dict:
    """
    Query SCC for development applications on and near the parcel.
    
    Returns both on-parcel and nearby applications with decision status.
    """
    # Run all DA/Building queries in parallel
    # On parcel: tight bbox (~50m around parcel)
    da_progress_on_task = _query_da_layer(DA_IN_PROGRESS, lat, lng, geometry, distance_m=50)
    da_past_on_task = _query_da_layer(DA_DECIDED_PAST, lat, lng, geometry, distance_m=50)
    building_progress_on_task = _query_da_layer(BUILDING_IN_PROGRESS, lat, lng, geometry, distance_m=50)
    building_past_on_task = _query_da_layer(BUILDING_DECIDED_PAST, lat, lng, geometry, distance_m=50)
    
    # Nearby: 500m radius
    da_progress_nearby_task = _query_da_layer(DA_IN_PROGRESS, lat, lng, distance_m=500)
    da_past_nearby_task = _query_da_layer(DA_DECIDED_PAST, lat, lng, distance_m=500)
    building_progress_nearby_task = _query_da_layer(BUILDING_IN_PROGRESS, lat, lng, distance_m=500)
    building_past_nearby_task = _query_da_layer(BUILDING_DECIDED_PAST, lat, lng, distance_m=500)

    (da_progress_on, da_past_on, building_progress_on, building_past_on,
     da_progress_nearby, da_past_nearby, building_progress_nearby, building_past_nearby) = await asyncio.gather(
        da_progress_on_task, da_past_on_task, building_progress_on_task, building_past_on_task,
        da_progress_nearby_task, da_past_nearby_task, building_progress_nearby_task, building_past_nearby_task
    )

    # Process on-parcel applications
    on_parcel_das = _process_da_features(da_progress_on + da_past_on)
    on_parcel_building = _process_da_features(building_progress_on + building_past_on)
    on_parcel = on_parcel_das + on_parcel_building

    # Process nearby applications (excluding duplicates from on-parcel)
    nearby_das = _process_da_features(da_progress_nearby + da_past_nearby)
    nearby_building = _process_da_features(building_progress_nearby + building_past_nearby)
    
    # Remove duplicates that are already in on_parcel
    on_parcel_ids = set(da.get("ram_id") for da in on_parcel if da.get("ram_id"))
    nearby = [da for da in (nearby_das + nearby_building) if da.get("ram_id") not in on_parcel_ids]

    # Count progress/decided
    on_parcel_in_progress = len([da for da in on_parcel if _is_in_progress(da)])
    nearby_in_progress = len([da for da in nearby if _is_in_progress(da)])
    total_in_progress = on_parcel_in_progress + nearby_in_progress

    # Generate Development-i portal link if lot/plan available
    portal_link = None
    if lot_plan and "/" in lot_plan:
        try:
            lot, plan = lot_plan.split("/", 1)
            # Remove 'RP' or 'SP' prefix from plan if present
            clean_plan = plan.replace("RP", "").replace("SP", "")
            portal_link = f"https://developmenti.sunshinecoast.qld.gov.au/Home/FilterDirect?LotPlan={lot}/{clean_plan}"
        except:
            pass

    return {
        "on_parcel": on_parcel,
        "nearby": nearby,
        "on_parcel_count": len(on_parcel),
        "nearby_count": len(nearby),
        "total_count": len(on_parcel) + len(nearby),
        "on_parcel_in_progress": on_parcel_in_progress,
        "nearby_in_progress": nearby_in_progress,
        "total_in_progress": total_in_progress,
        "portal_link": portal_link,
        "summary": _build_summary(len(on_parcel), len(nearby), total_in_progress),
    }


def _is_in_progress(da: Dict) -> bool:
    """Check if a DA is still in progress."""
    progress = (da.get("progress") or "").lower()
    decision = (da.get("decision") or "").lower()
    
    # No decision date usually means in progress
    if not da.get("date_decided") and da.get("date_received"):
        return True
    
    # Check progress status
    if "progress" in progress or "current" in progress or "pending" in progress:
        return True
    
    # Check decision status
    if not decision or "pending" in decision or "current" in decision:
        return True
    
    return False


def _build_summary(on_parcel_count: int, nearby_count: int, in_progress_count: int) -> str:
    """Build a summary string for DA history."""
    if on_parcel_count == 0 and nearby_count == 0:
        return "No development applications found in area"
    
    parts = []
    if on_parcel_count > 0:
        parts.append(f"{on_parcel_count} on parcel")
    if nearby_count > 0:
        parts.append(f"{nearby_count} nearby")
    
    summary = ", ".join(parts)
    
    if in_progress_count > 0:
        summary += f" ({in_progress_count} in progress)"
    
    return summary