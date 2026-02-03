"""
Infrastructure Service — Query Unitywater + SCC for public infrastructure.

Checks water mains, sewer mains, hydrants, and stormwater/waterways
near a parcel to determine service availability.
"""

import asyncio
import httpx
from typing import Optional

# ─── Service URLs ─────────────────────────────────────────────────────────────

UNITYWATER_WATER_URL = (
    "https://services2.arcgis.com/tQg86iShPXJPWQWw/ArcGIS/rest/services/"
    "UWPublicAccessWaterInfrastructureLayers/FeatureServer"
)
UNITYWATER_SEWER_URL = (
    "https://services2.arcgis.com/tQg86iShPXJPWQWw/ArcGIS/rest/services/"
    "UWPublicAccessSewerInfrastructureLayers/FeatureServer"
)
SCC_WATERWAYS_URL = (
    "https://geopublic.scc.qld.gov.au/arcgis/rest/services/"
    "InlandWaters/InlandWaters_SCRC/MapServer"
)
SCC_STORMWATER_URL = (
    "https://geopublic.scc.qld.gov.au/arcgis/rest/services/"
    "UtilitiesCommunication/Utilities_SCRC/MapServer"
)

# Layer IDs
WATER_MAIN_LAYER = 10
WATER_HYDRANT_LAYER = 7
SEWER_GRAVITY_LAYER = 11
SEWER_PRESSURE_LAYER = 12
WATERWAY_LAYER = 7
SW_PIPE_LAYER = 8       # Stormwater Pipe (Council)
SW_PIT_LAYER = 4         # Stormwater Pit (Council)
SW_CULVERT_LAYER = 9     # Stormwater Culvert (Council)
SW_OPEN_DRAIN_LAYER = 6  # Stormwater Open Drain (Council)


async def _query_infrastructure_layer(
    base_url: str,
    layer_id: int,
    lat: float,
    lng: float,
    distance_m: int = 100,
    return_geometry: bool = False,
    timeout: float = 15.0,
    is_feature_server: bool = True,
) -> list:
    """Query an ArcGIS layer with a buffer distance around a point."""
    url = f"{base_url}/{layer_id}/query"
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": distance_m,
        "units": "esriSRUnit_Meter",
        "inSR": 4326,
        "outSR": 4326,
        "outFields": "*",
        "returnGeometry": str(return_geometry).lower(),
        "f": "json",
        "resultRecordCount": 200,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("features", [])
        except Exception as e:
            print(f"⚠️  Infrastructure query failed (layer {layer_id}): {e}")
            return []


async def get_infrastructure(lat: float, lng: float) -> dict:
    """
    Query Unitywater + SCC for public infrastructure near the parcel.
    
    Returns water, sewer, and stormwater availability with details.
    """
    # Run all queries in parallel
    water_task = _query_infrastructure_layer(
        UNITYWATER_WATER_URL, WATER_MAIN_LAYER, lat, lng,
        distance_m=100, return_geometry=True
    )
    hydrant_task = _query_infrastructure_layer(
        UNITYWATER_WATER_URL, WATER_HYDRANT_LAYER, lat, lng,
        distance_m=200, return_geometry=True
    )
    sewer_gravity_task = _query_infrastructure_layer(
        UNITYWATER_SEWER_URL, SEWER_GRAVITY_LAYER, lat, lng,
        distance_m=100, return_geometry=True
    )
    sewer_pressure_task = _query_infrastructure_layer(
        UNITYWATER_SEWER_URL, SEWER_PRESSURE_LAYER, lat, lng,
        distance_m=100, return_geometry=True
    )
    waterway_task = _query_infrastructure_layer(
        SCC_WATERWAYS_URL, WATERWAY_LAYER, lat, lng,
        distance_m=200, return_geometry=False, is_feature_server=False
    )
    sw_pipe_task = _query_infrastructure_layer(
        SCC_STORMWATER_URL, SW_PIPE_LAYER, lat, lng,
        distance_m=200, return_geometry=True, is_feature_server=False
    )
    sw_pit_task = _query_infrastructure_layer(
        SCC_STORMWATER_URL, SW_PIT_LAYER, lat, lng,
        distance_m=200, return_geometry=True, is_feature_server=False
    )
    sw_culvert_task = _query_infrastructure_layer(
        SCC_STORMWATER_URL, SW_CULVERT_LAYER, lat, lng,
        distance_m=200, return_geometry=True, is_feature_server=False
    )

    (water_mains, hydrants, sewer_gravity, sewer_pressure,
     waterways, sw_pipes, sw_pits, sw_culverts) = await asyncio.gather(
        water_task, hydrant_task, sewer_gravity_task, sewer_pressure_task,
        waterway_task, sw_pipe_task, sw_pit_task, sw_culvert_task
    )

    # ── Process Water ──
    water_result = _process_water(water_mains, hydrants)

    # ── Process Sewer ──
    sewer_result = _process_sewer(sewer_gravity, sewer_pressure)

    # ── Process Stormwater ──
    stormwater_result = _process_stormwater(waterways, sw_pipes, sw_pits, sw_culverts)

    return {
        "water": water_result,
        "sewer": sewer_result,
        "stormwater": stormwater_result,
    }


def _process_water(water_mains: list, hydrants: list) -> dict:
    """Process water main and hydrant query results."""
    mains_count = len(water_mains)
    hydrants_count = len(hydrants)

    # Find nearest/largest diameter
    nearest_diameter = None
    nearest_material = None
    for feat in water_mains:
        attrs = feat.get("attributes", {})
        diam = attrs.get("NominalDiameter") or attrs.get("Diameter")
        mat = attrs.get("Material")
        if diam is not None:
            try:
                diam_val = float(diam)
                if nearest_diameter is None or diam_val > 0:
                    # Take the first valid one (they're sorted by proximity)
                    if nearest_diameter is None:
                        nearest_diameter = diam_val
                        nearest_material = mat
            except (ValueError, TypeError):
                pass

    available = mains_count > 0

    if available:
        summary = f"✅ Reticulated water available — {int(nearest_diameter) if nearest_diameter else '?'}mm {nearest_material or ''} main within 100m"
        summary = summary.strip()
    else:
        summary = "❌ No reticulated water — tank/bore required"

    # Extract geometries for mapping
    water_geometries = []
    for feat in water_mains:
        geom = feat.get("geometry")
        if geom:
            water_geometries.append({
                "type": "water_main",
                "geometry": geom,
                "diameter": feat.get("attributes", {}).get("NominalDiameter"),
                "material": feat.get("attributes", {}).get("Material"),
            })

    hydrant_geometries = []
    for feat in hydrants:
        geom = feat.get("geometry")
        if geom:
            hydrant_geometries.append({
                "type": "hydrant",
                "geometry": geom,
            })

    return {
        "available": available,
        "mains_count": mains_count,
        "nearest_diameter_mm": int(nearest_diameter) if nearest_diameter else None,
        "nearest_material": nearest_material,
        "hydrants_nearby": hydrants_count,
        "summary": summary,
        "geometries": water_geometries,
        "hydrant_geometries": hydrant_geometries,
    }


def _process_sewer(sewer_gravity: list, sewer_pressure: list) -> dict:
    """Process sewer main query results."""
    gravity_count = len(sewer_gravity)
    pressure_count = len(sewer_pressure)
    total_count = gravity_count + pressure_count

    nearest_diameter = None
    nearest_type = None

    # Check gravity mains first (more common)
    for feat in sewer_gravity:
        attrs = feat.get("attributes", {})
        diam = attrs.get("NominalDiameter") or attrs.get("Diameter")
        if diam is not None:
            try:
                diam_val = float(diam)
                if nearest_diameter is None:
                    nearest_diameter = diam_val
                    nearest_type = "gravity"
            except (ValueError, TypeError):
                pass

    # Then pressure mains
    for feat in sewer_pressure:
        attrs = feat.get("attributes", {})
        diam = attrs.get("NominalDiameter") or attrs.get("Diameter")
        if diam is not None:
            try:
                diam_val = float(diam)
                if nearest_diameter is None:
                    nearest_diameter = diam_val
                    nearest_type = "pressure"
            except (ValueError, TypeError):
                pass

    available = total_count > 0

    if available:
        summary = f"✅ Reticulated sewer available — {int(nearest_diameter) if nearest_diameter else '?'}mm {nearest_type or ''} main within 100m"
    else:
        summary = "❌ No reticulated sewer — on-site system required"

    # Extract geometries for mapping
    sewer_geometries = []
    for feat in sewer_gravity:
        geom = feat.get("geometry")
        if geom:
            sewer_geometries.append({
                "type": "sewer_gravity",
                "geometry": geom,
                "diameter": feat.get("attributes", {}).get("NominalDiameter"),
            })
    for feat in sewer_pressure:
        geom = feat.get("geometry")
        if geom:
            sewer_geometries.append({
                "type": "sewer_pressure",
                "geometry": geom,
                "diameter": feat.get("attributes", {}).get("NominalDiameter"),
            })

    return {
        "available": available,
        "mains_count": total_count,
        "gravity_count": gravity_count,
        "pressure_count": pressure_count,
        "nearest_diameter_mm": int(nearest_diameter) if nearest_diameter else None,
        "nearest_type": nearest_type,
        "summary": summary,
        "geometries": sewer_geometries,
    }


def _process_stormwater(
    waterways: list,
    sw_pipes: list = None,
    sw_pits: list = None,
    sw_culverts: list = None,
) -> dict:
    """Process stormwater/waterway + SCC stormwater network results."""
    sw_pipes = sw_pipes or []
    sw_pits = sw_pits or []
    sw_culverts = sw_culverts or []

    waterway_count = len(waterways)
    pipe_count = len(sw_pipes)
    pit_count = len(sw_pits)
    culvert_count = len(sw_culverts)

    # Get stream info from waterways
    drainage_info = None
    for feat in waterways:
        attrs = feat.get("attributes", {})
        name = attrs.get("Name") or attrs.get("GNAME") or attrs.get("name")
        if name:
            drainage_info = name
            break

    # Stormwater network availability
    has_network = (pipe_count + culvert_count) > 0

    # Find largest pipe diameter
    largest_diameter = None
    for feat in sw_pipes + sw_culverts:
        attrs = feat.get("attributes", {})
        diam = attrs.get("PipeDiameter_mm")
        if diam is not None:
            try:
                diam_val = int(diam)
                if diam_val > 0 and (largest_diameter is None or diam_val > largest_diameter):
                    largest_diameter = diam_val
            except (ValueError, TypeError):
                pass

    # Build summary
    parts = []
    if has_network:
        parts.append(f"✅ Council stormwater network — {pipe_count} pipe{'s' if pipe_count != 1 else ''}")
        if culvert_count:
            parts.append(f"{culvert_count} culvert{'s' if culvert_count != 1 else ''}")
        parts_str = ", ".join(parts) + " within 200m"
    else:
        parts_str = "No council stormwater pipes within 200m"

    if waterway_count > 0:
        ww = f"{waterway_count} waterway{'s' if waterway_count != 1 else ''} within 200m"
        if drainage_info:
            ww = f"Natural drainage via {drainage_info} — {ww}"
        parts_str += f" | {ww}"

    # Extract pipe geometries for mapping
    pipe_geometries = []
    for feat in sw_pipes:
        geom = feat.get("geometry")
        if geom:
            attrs = feat.get("attributes", {})
            pipe_geometries.append({
                "type": "stormwater_pipe",
                "geometry": geom,
                "diameter": attrs.get("PipeDiameter_mm"),
                "material": attrs.get("Material"),
            })
    for feat in sw_culverts:
        geom = feat.get("geometry")
        if geom:
            attrs = feat.get("attributes", {})
            pipe_geometries.append({
                "type": "stormwater_culvert",
                "geometry": geom,
                "diameter": attrs.get("PipeDiameter_mm"),
                "material": attrs.get("Material"),
            })

    # Extract pit geometries for mapping
    pit_geometries = []
    for feat in sw_pits:
        geom = feat.get("geometry")
        if geom:
            attrs = feat.get("attributes", {})
            pit_geometries.append({
                "type": "stormwater_pit",
                "geometry": geom,
                "inlet_type": attrs.get("InletType"),
            })

    return {
        "available": has_network,
        "nearby_waterways": waterway_count,
        "drainage_info": drainage_info,
        "pipe_count": pipe_count,
        "pit_count": pit_count,
        "culvert_count": culvert_count,
        "largest_diameter_mm": largest_diameter,
        "summary": parts_str,
        "geometries": pipe_geometries,
        "pit_geometries": pit_geometries,
    }
