"""
Constraints & Easements Service — Query SCC and QLD for site constraints.

Checks easements, covenants, koala habitat, and environmentally sensitive areas
that may constrain development on the parcel.
"""

import asyncio
import httpx
from typing import Optional, List, Dict


# ─── Service URLs ─────────────────────────────────────────────────────────────

SCC_PARCEL_INFO_URL = (
    "https://geopublic.scc.qld.gov.au/arcgis/rest/services/"
    "PlanningCadastre/ParcelInformation_SCRC/MapServer"
)

QLD_KOALA_URL = (
    "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
    "Environment/KoalaPlan/MapServer"
)

QLD_ESA_URL = (
    "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
    "Environment/EnvironmentallySensitiveAreas/MapServer"
)

# Layer IDs
EASEMENTS_LAYER = 1
COVENANTS_LAYER = 0
KOALA_PRIORITY_LAYER = 1
KOALA_HABITAT_LAYER = 2
KOALA_CORE_HABITAT_LAYER = 3
ESA_CATEGORY_A_LAYER = 0
ESA_CATEGORY_B_LAYER = 1


async def _query_parcel_constraints(
    lat: float,
    lng: float,
    geometry: dict = None,
    timeout: float = 15.0,
) -> Dict[str, List[Dict]]:
    """Query SCC for easements and covenants."""
    results = {}
    
    # Build envelope from geometry if available
    if geometry and geometry.get("type") == "Polygon":
        coords = geometry["coordinates"][0]
        min_lng = min(c[0] for c in coords)
        max_lng = max(c[0] for c in coords)
        min_lat = min(c[1] for c in coords)
        max_lat = max(c[1] for c in coords)
        
        # Small buffer for edge cases
        buffer = 0.0001  # ~10m
        envelope = f"{min_lng-buffer},{min_lat-buffer},{max_lng+buffer},{max_lat+buffer}"
        
        geom_params = {
            "geometry": envelope,
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
        }
    else:
        # Fallback to point with small buffer
        geom_params = {
            "geometry": f"{lng},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "distance": 50,
            "units": "esriSRUnit_Meter",
        }
    
    # Query easements and covenants
    tasks = []
    for layer_id, layer_name in [(EASEMENTS_LAYER, "easements"), (COVENANTS_LAYER, "covenants")]:
        url = f"{SCC_PARCEL_INFO_URL}/{layer_id}/query"
        params = {
            **geom_params,
            "inSR": 4326,
            "outSR": 4326,
            "outFields": "LOTPLAN,GAZETTEDAREA,NAME,PURPOSE1,INFAVOUR1,STATUS",
            "returnGeometry": "true",
            "f": "json",
            "resultRecordCount": 50,
        }
        tasks.append((layer_name, url, params))
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        for layer_name, url, params in tasks:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                results[layer_name] = data.get("features", [])
            except Exception as e:
                print(f"⚠️  SCC {layer_name} query failed: {e}")
                results[layer_name] = []
    
    return results


async def _query_koala_habitat(
    lat: float,
    lng: float,
    distance_m: int = 200,
    timeout: float = 15.0,
) -> Dict[str, List[Dict]]:
    """Query QLD koala habitat layers."""
    results = {}
    
    # Query all koala habitat layers
    tasks = []
    layer_names = {
        KOALA_PRIORITY_LAYER: "priority",
        KOALA_HABITAT_LAYER: "habitat", 
        KOALA_CORE_HABITAT_LAYER: "core_habitat"
    }
    
    for layer_id, layer_name in layer_names.items():
        url = f"{QLD_KOALA_URL}/{layer_id}/query"
        params = {
            "geometry": f"{lng},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "distance": distance_m,
            "units": "esriSRUnit_Meter",
            "inSR": 4326,
            "outSR": 4326,
            "outFields": "*",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 20,
        }
        tasks.append((layer_name, url, params))
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        for layer_name, url, params in tasks:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                results[layer_name] = data.get("features", [])
            except Exception as e:
                print(f"⚠️  Koala {layer_name} query failed: {e}")
                results[layer_name] = []
    
    return results


async def _query_esa_areas(
    lat: float,
    lng: float,
    distance_m: int = 200,
    timeout: float = 15.0,
) -> Dict[str, List[Dict]]:
    """Query QLD Environmentally Sensitive Areas."""
    results = {}
    
    # Query ESA Category A and B
    tasks = []
    layer_names = {
        ESA_CATEGORY_A_LAYER: "category_a",
        ESA_CATEGORY_B_LAYER: "category_b",
    }
    
    for layer_id, layer_name in layer_names.items():
        url = f"{QLD_ESA_URL}/{layer_id}/query"
        params = {
            "geometry": f"{lng},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "distance": distance_m,
            "units": "esriSRUnit_Meter",
            "inSR": 4326,
            "outSR": 4326,
            "outFields": "*",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 20,
        }
        tasks.append((layer_name, url, params))
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        for layer_name, url, params in tasks:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                results[layer_name] = data.get("features", [])
            except Exception as e:
                print(f"⚠️  ESA {layer_name} query failed: {e}")
                results[layer_name] = []
    
    return results


def _process_easements(easement_features: List[Dict]) -> List[Dict]:
    """Process easement features."""
    easements = []
    
    for feat in easement_features:
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry", {})
        
        easement = {
            "lotplan": attrs.get("LOTPLAN", "").strip(),
            "area": attrs.get("GAZETTEDAREA", "").strip(),
            "name": attrs.get("NAME", "").strip(),
            "purpose": attrs.get("PURPOSE1", "").strip(),
            "in_favour": attrs.get("INFAVOUR1", "").strip(),
            "status": attrs.get("STATUS", "").strip(),
            "geometry": geom if geom else None,
        }
        
        # Skip if no meaningful data
        if not any([easement["name"], easement["purpose"]]):
            continue
        
        easements.append(easement)
    
    return easements


def _process_covenants(covenant_features: List[Dict]) -> List[Dict]:
    """Process covenant features."""
    covenants = []
    
    for feat in covenant_features:
        attrs = feat.get("attributes", {})
        
        covenant = {
            "lotplan": attrs.get("LOTPLAN", "").strip(),
            "name": attrs.get("NAME", "").strip(),
            "purpose": attrs.get("PURPOSE1", "").strip(),
            "in_favour": attrs.get("INFAVOUR1", "").strip(),
            "status": attrs.get("STATUS", "").strip(),
        }
        
        # Skip if no meaningful data
        if not covenant["name"] and not covenant["purpose"]:
            continue
        
        covenants.append(covenant)
    
    return covenants


def _process_koala_habitat(koala_results: Dict[str, List[Dict]]) -> Dict[str, any]:
    """Process koala habitat results."""
    priority_areas = koala_results.get("priority", [])
    habitat_areas = koala_results.get("habitat", [])
    core_habitat_areas = koala_results.get("core_habitat", [])
    
    koala_info = {
        "has_priority": len(priority_areas) > 0,
        "has_habitat": len(habitat_areas) > 0,
        "has_core_habitat": len(core_habitat_areas) > 0,
        "priority_count": len(priority_areas),
        "habitat_count": len(habitat_areas),
        "core_habitat_count": len(core_habitat_areas),
    }
    
    # Determine highest level of koala significance
    if koala_info["has_core_habitat"]:
        koala_info["status"] = "Core Koala Habitat"
        koala_info["significance"] = "high"
    elif koala_info["has_habitat"]:
        koala_info["status"] = "Koala Habitat Area"
        koala_info["significance"] = "medium"
    elif koala_info["has_priority"]:
        koala_info["status"] = "Koala Priority Area"
        koala_info["significance"] = "medium"
    else:
        koala_info["status"] = None
        koala_info["significance"] = "none"
    
    return koala_info


def _process_esa_areas(esa_results: Dict[str, List[Dict]]) -> Dict[str, any]:
    """Process Environmentally Sensitive Areas results."""
    category_a = esa_results.get("category_a", [])
    category_b = esa_results.get("category_b", [])
    
    esa_info = {
        "has_category_a": len(category_a) > 0,
        "has_category_b": len(category_b) > 0,
        "category_a_count": len(category_a),
        "category_b_count": len(category_b),
    }
    
    # Determine ESA category
    if esa_info["has_category_a"]:
        esa_info["category"] = "Category A"
        esa_info["significance"] = "high"
        esa_info["status"] = "Environmentally Sensitive Area (Category A)"
    elif esa_info["has_category_b"]:
        esa_info["category"] = "Category B"
        esa_info["significance"] = "medium"
        esa_info["status"] = "Environmentally Sensitive Area (Category B)"
    else:
        esa_info["category"] = None
        esa_info["significance"] = "none"
        esa_info["status"] = None
    
    return esa_info


async def get_constraints(lat: float, lng: float, geometry: dict = None) -> dict:
    """
    Query SCC and QLD for site constraints and easements.
    
    Returns easements, covenants, koala habitat, and ESA information.
    """
    # Run all constraint queries in parallel
    parcel_task = _query_parcel_constraints(lat, lng, geometry)
    koala_task = _query_koala_habitat(lat, lng)
    esa_task = _query_esa_areas(lat, lng)

    parcel_results, koala_results, esa_results = await asyncio.gather(
        parcel_task, koala_task, esa_task
    )

    # Process results
    easements = _process_easements(parcel_results.get("easements", []))
    covenants = _process_covenants(parcel_results.get("covenants", []))
    koala_info = _process_koala_habitat(koala_results)
    esa_info = _process_esa_areas(esa_results)

    # Build summary of constraints
    constraint_items = []
    
    if easements:
        constraint_items.append(f"{len(easements)} easement{'s' if len(easements) != 1 else ''}")
    
    if covenants:
        constraint_items.append(f"{len(covenants)} covenant{'s' if len(covenants) != 1 else ''}")
    
    if koala_info["status"]:
        constraint_items.append(koala_info["status"])
    
    if esa_info["status"]:
        constraint_items.append(esa_info["status"])
    
    if constraint_items:
        summary = "⚠️ " + ", ".join(constraint_items)
    else:
        summary = "✅ No major site constraints identified"

    return {
        "easements": easements,
        "covenants": covenants,
        "koala": koala_info,
        "esa": esa_info,
        "easements_count": len(easements),
        "covenants_count": len(covenants),
        "has_constraints": len(easements) > 0 or len(covenants) > 0 or koala_info["status"] or esa_info["status"],
        "summary": summary,
    }