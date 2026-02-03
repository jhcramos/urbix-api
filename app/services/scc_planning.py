"""
SCC Planning Service — Query Sunshine Coast Council's REAL ArcGIS services.

No guessing. Actual zone + overlay data from the source.
"""

import asyncio
import httpx
from typing import Optional

# ─── SCC ArcGIS Service URLs ─────────────────────────────────────────────────

SCC_ZONING_URL = (
    "https://geoimage.scc.qld.gov.au/arcgis/rest/services/"
    "PlanningCadastre/PlanningScheme_SunshineCoast_Zoning_SCC/MapServer"
)
SCC_OVERLAYS_URL = (
    "https://geoimage.scc.qld.gov.au/arcgis/rest/services/"
    "PlanningCadastre/PlanningScheme_SunshineCoast_Overlays_SCC/MapServer"
)
SCC_TRANSPORT_URL = (
    "https://geoimage.scc.qld.gov.au/arcgis/rest/services/"
    "PlanningCadastre/PlanningScheme_SunshineCoast_Transport_SCC/MapServer"
)
SCC_PARCELS_URL = (
    "https://geopublic.scc.qld.gov.au/arcgis/rest/services/"
    "PlanningCadastre/ParcelInformation_SCRC/MapServer/3"
)

ZONING_LAYER = 5
HEIGHT_LAYER = 50

# ─── Overlay Layer Definitions ────────────────────────────────────────────────
# category → list of (layer_id, name)

OVERLAY_LAYERS = {
    "Acid Sulfate Soils": [
        (0, "Acid Sulfate Soils"),
    ],
    "Airport Environs": [
        (2, "Sunshine Coast Airport"),
        (3, "Public Safety Area"),
        (9, "Obstacle Limitation Surface (OLS)"),
        (12, "Australian Noise Exposure Forecast (ANEF) Level"),
        (13, "Caloundra Aerodrome"),
    ],
    "Biodiversity, Waterways and Wetlands": [
        (24, "Waterways"),
        (25, "Declared Fish Habitat Area"),
        (26, "Riparian Protection Area"),
        (27, "Ramsar Wetlands"),
        (28, "Wetlands"),
        (29, "Waterbodies"),
        (30, "Native Vegetation Area"),
    ],
    "Bushfire Hazard": [
        (32, "High Bushfire Hazard Area"),
        (33, "High Bushfire Hazard Area Buffer"),
        (34, "Medium Bushfire Hazard Area"),
        (35, "Medium Bushfire Hazard Area Buffer"),
    ],
    "Coastal Protection": [
        (37, "Coastal Protection Area"),
        (38, "Maritime Development Area"),
    ],
    "Extractive Resources": [
        (40, "Transport Route and Separation Area"),
        (41, "Local Resource / Processing Area"),
        (43, "State Key Resource Area"),
    ],
    "Flood Hazard": [
        (46, "Flooding and Inundation Area"),
        (47, "Drainage Deficient Areas"),
    ],
    "Height of Buildings and Structures": [
        (50, "Maximum Height of Buildings and Structures"),
    ],
    "Heritage and Character Areas": [
        (52, "Local Heritage Place (Shipwreck)"),
        (53, "State Heritage Place"),
        (54, "Local Heritage Place"),
        (55, "Land In Proximity to a Local Heritage Place"),
        (56, "Character Building"),
        (57, "Character Area"),
    ],
    "Landslide Hazard": [
        (58, "Landslide Hazard Area"),
    ],
    "Steep Land": [
        (59, "Steep Land (Slope)"),
    ],
    "Regional Infrastructure": [
        (61, "Gas Pipeline Corridor and Buffer"),
        (62, "High Voltage Electricity Line (Distribution)"),
        (63, "High Voltage Electricity Line (Transmission)"),
        (64, "Water Supply Pipeline and Buffer"),
        (65, "Wastewater Treatment Plant and Buffer"),
        (66, "Railway Corridor and Buffer"),
        (67, "Dedicated Transit Corridor and Buffer"),
        (68, "Major Road Corridor and Buffer"),
    ],
    "Scenic Amenity": [
        (69, "Scenic Amenity"),
        (70, "Scenic Route"),
        (71, "Regional Inter-Urban Break"),
    ],
    "Water Resource Catchments": [
        (73, "Water Resource Catchment Area"),
        (74, "Water Supply Storage"),
    ],
}

# Flat list of all queryable layer IDs
ALL_OVERLAY_LAYER_IDS = []
for layers in OVERLAY_LAYERS.values():
    for lid, _ in layers:
        ALL_OVERLAY_LAYER_IDS.append(lid)

# Reverse map: layer_id → (category, name)
LAYER_INFO = {}
for cat, layers in OVERLAY_LAYERS.items():
    for lid, name in layers:
        LAYER_INFO[lid] = (cat, name)


# ─── Low-level query helpers ─────────────────────────────────────────────────

async def _query_layer(
    base_url: str,
    layer_id: int,
    lat: float,
    lng: float,
    return_geometry: bool = False,
    timeout: float = 12.0,
    bbox: list = None,
) -> list:
    """Query a single ArcGIS layer with a point or bounding box envelope."""
    url = f"{base_url}/{layer_id}/query"
    if bbox:
        params = {
            "geometry": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": 4326,
            "outFields": "*",
            "returnGeometry": str(return_geometry).lower(),
            "f": "json",
            "resultRecordCount": 50,
        }
    else:
        params = {
            "geometry": f"{lng},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": 4326,
            "outFields": "*",
            "returnGeometry": str(return_geometry).lower(),
            "f": "json",
            "resultRecordCount": 10,
        }
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("features", [])
        except Exception as e:
            print(f"⚠️  SCC query failed layer {layer_id}: {e}")
            return []


async def _identify_service(
    base_url: str,
    lat: float,
    lng: float,
    timeout: float = 15.0,
    tolerance: int = 10,
) -> list:
    """Identify all layers at a point on a MapServer."""
    url = f"{base_url}/identify"
    params = {
        "geometry": f'{{"x":{lng},"y":{lat},"spatialReference":{{"wkid":4326}}}}',
        "geometryType": "esriGeometryPoint",
        "tolerance": tolerance,
        "mapExtent": f"{lng-0.01},{lat-0.01},{lng+0.01},{lat+0.01}",
        "imageDisplay": "400,400,96",
        "layers": "all",
        "returnGeometry": "false",
        "f": "json",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except Exception as e:
            print(f"⚠️  SCC identify failed: {e}")
            return []


def _compute_parcel_bbox(geometry: dict) -> list:
    """Compute tight bounding box from a GeoJSON geometry for overlay queries."""
    coords = []
    geom_type = geometry.get("type", "")

    if geom_type == "Polygon":
        for ring in geometry.get("coordinates", []):
            coords.extend(ring)
    elif geom_type == "MultiPolygon":
        for polygon in geometry.get("coordinates", []):
            for ring in polygon:
                coords.extend(ring)
    elif geom_type == "Point":
        coords = [geometry["coordinates"]]

    if not coords:
        return None

    lngs = [c[0] for c in coords]
    lats = [c[1] for c in coords]

    return [min(lngs), min(lats), max(lngs), max(lats)]


# ─── Public API ───────────────────────────────────────────────────────────────

async def get_zone(lat: float, lng: float) -> Optional[dict]:
    """
    Get the planning zone from SCC's actual zoning service.
    Returns: {code, category, label, description} or None.
    """
    features = await _query_layer(SCC_ZONING_URL, ZONING_LAYER, lat, lng)
    if not features:
        return None

    attrs = features[0].get("attributes", {})
    label = attrs.get("LABEL", "")
    heading = attrs.get("HEADING", "").strip()
    descript = attrs.get("DESCRIPT", "")

    return {
        "code": label,
        "category": heading if heading else "Unknown Category",
        "label": label,
        "description": descript,
    }


async def get_height_restriction(lat: float, lng: float) -> Optional[dict]:
    """
    Get the max building height from SCC's Height overlay (Layer 50).
    Returns: {height_m, label, comment} or None.
    """
    features = await _query_layer(SCC_OVERLAYS_URL, HEIGHT_LAYER, lat, lng)
    if not features:
        return None

    attrs = features[0].get("attributes", {})
    height = attrs.get("HeightRestrictionMetres")
    label = attrs.get("LABEL", "")
    comment = attrs.get("ComplexComment") or ""

    return {
        "height_m": float(height) if height is not None else None,
        "label": label,
        "comment": comment,
    }


async def get_overlays(lat: float, lng: float, geometry: dict = None) -> list:
    """
    Query ALL SCC overlay layers and return those that intersect.
    
    If geometry is provided, uses parcel bounding box (envelope) to catch
    overlays on edges of the parcel, not just the centroid.
    
    Returns list of {layer_id, name, category, label, attributes}.
    Uses parallel queries batched to avoid overwhelming the server.
    """
    # Compute bbox from parcel geometry if available
    parcel_bbox = None
    if geometry:
        parcel_bbox = _compute_parcel_bbox(geometry)
        if parcel_bbox:
            print(f"📦 Using parcel bbox for overlays: {parcel_bbox}")

    results = []

    # Query layers in batches of 8 for parallelism
    batch_size = 8
    for i in range(0, len(ALL_OVERLAY_LAYER_IDS), batch_size):
        batch = ALL_OVERLAY_LAYER_IDS[i : i + batch_size]
        tasks = [
            _query_layer(SCC_OVERLAYS_URL, lid, lat, lng, bbox=parcel_bbox)
            for lid in batch
        ]
        batch_results = await asyncio.gather(*tasks)

        for lid, features in zip(batch, batch_results):
            if features:
                cat, name = LAYER_INFO.get(lid, ("Unknown", "Unknown"))
                for feat in features:
                    attrs = feat.get("attributes", {})
                    label = attrs.get("LABEL", name)
                    entry = {
                        "layer_id": lid,
                        "name": name,
                        "category": cat,
                        "label": label,
                        "attributes": {
                            k: v for k, v in attrs.items()
                            if k not in ("OBJECTID", "Shape", "Shape.STArea()", "Shape.STLength()")
                            and v is not None
                        },
                    }
                    # Special handling for height layer
                    if lid == HEIGHT_LAYER:
                        height_val = attrs.get("HeightRestrictionMetres")
                        if height_val is not None:
                            entry["height_m"] = float(height_val)
                    results.append(entry)

    return results


async def get_overlays_grouped(lat: float, lng: float, geometry: dict = None) -> list:
    """
    Get overlays grouped by category.
    Returns: [{category, layers: [{layer_id, name, label, ...}]}]
    """
    raw = await get_overlays(lat, lng, geometry=geometry)

    groups = {}
    seen_keys = set()
    for item in raw:
        # Deduplicate: same layer_id + label = same overlay feature
        dedup_key = f"{item['layer_id']}|{item['label']}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        cat = item["category"]
        if cat not in groups:
            groups[cat] = {
                "category": cat,
                "layers": [],
            }
        layer_entry = {
            "layer_id": item["layer_id"],
            "name": item["name"],
            "label": item["label"],
        }
        if "height_m" in item:
            layer_entry["height_m"] = item["height_m"]
        # Include extra attributes
        extra = {k: v for k, v in item.get("attributes", {}).items()
                 if k not in ("DESCRIPT", "HEADING", "LABEL")}
        if extra:
            layer_entry["attributes"] = extra
        groups[cat]["layers"].append(layer_entry)

    return list(groups.values())


async def get_transport(lat: float, lng: float) -> list:
    """
    Get transport/road hierarchy from SCC's Transport service.
    Returns list of {heading, label, description}.
    """
    results = await _identify_service(SCC_TRANSPORT_URL, lat, lng, tolerance=100)
    transport = []
    seen = set()
    for r in results:
        attrs = r.get("attributes", {})
        heading = attrs.get("HEADING", "")
        label = attrs.get("LABEL", "")
        key = f"{heading}|{label}"
        if key in seen:
            continue
        seen.add(key)
        transport.append({
            "heading": heading,
            "label": label,
            "description": attrs.get("DESCRIPT", ""),
        })
    return transport


async def get_scc_parcel_info(lat: float, lng: float) -> Optional[dict]:
    """
    Get parcel info from SCC's own ParcelInformation service.
    Returns address, lot/plan, area, locality etc.
    """
    # SCC_PARCELS_URL already includes /3, query it directly
    url = f"{SCC_PARCELS_URL}/query"
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": 4326,
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json",
        "resultRecordCount": 5,
    }
    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
        except Exception:
            return None

    if not features:
        return None

    attrs = features[0].get("attributes", {})
    return {
        "address": attrs.get("address_format", ""),
        "address_short": attrs.get("address_short", ""),
        "lot": attrs.get("lot", ""),
        "plan": attrs.get("plannum", ""),
        "lotplan": attrs.get("lotplan", ""),
        "area_sqm": float(attrs.get("land_area", 0)) if attrs.get("land_area") else None,
        "area_units": attrs.get("area_units_desc", ""),
        "street_name": attrs.get("street_name", ""),
        "street_number": str(attrs.get("Street_Number", attrs.get("house_no", ""))),
        "locality": attrs.get("locality_name", ""),
        "postcode": attrs.get("postcode", ""),
        "land_type": attrs.get("LANDTYPE", ""),
        "status": attrs.get("STATUS", ""),
        "property_no": attrs.get("property_no"),
    }


async def get_full_site_data(lat: float, lng: float, geometry: dict = None) -> dict:
    """
    Get ALL planning data for a point in one call.
    Runs zone, overlays, height, transport, and parcel queries in parallel.
    """
    zone_task = get_zone(lat, lng)
    overlays_task = get_overlays_grouped(lat, lng, geometry=geometry)
    height_task = get_height_restriction(lat, lng)
    transport_task = get_transport(lat, lng)
    parcel_task = get_scc_parcel_info(lat, lng)

    zone, overlays, height, transport, scc_parcel = await asyncio.gather(
        zone_task, overlays_task, height_task, transport_task, parcel_task
    )

    return {
        "zone": zone,
        "overlays": overlays,
        "height": height,
        "transport": transport,
        "scc_parcel": scc_parcel,
    }


# ─── WMS/Export URL builders ─────────────────────────────────────────────────

def get_zone_map_url(bbox: list, size: tuple = (500, 400)) -> str:
    """Build ArcGIS export URL for zone map image."""
    return (
        f"{SCC_ZONING_URL}/export?"
        f"bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
        f"&bboxSR=4326&imageSR=4326"
        f"&size={size[0]},{size[1]}"
        f"&format=png&transparent=true&f=image"
    )


def get_overlay_map_url(layer_ids: list, bbox: list, size: tuple = (500, 400)) -> str:
    """Build ArcGIS export URL for overlay map image."""
    layers_str = ",".join(str(lid) for lid in layer_ids)
    return (
        f"{SCC_OVERLAYS_URL}/export?"
        f"bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
        f"&bboxSR=4326&imageSR=4326"
        f"&size={size[0]},{size[1]}"
        f"&layers=show:{layers_str}"
        f"&format=png&transparent=true&f=image"
    )


def get_transport_map_url(bbox: list, size: tuple = (500, 400)) -> str:
    """Build ArcGIS export URL for transport map image."""
    return (
        f"{SCC_TRANSPORT_URL}/export?"
        f"bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
        f"&bboxSR=4326&imageSR=4326"
        f"&size={size[0]},{size[1]}"
        f"&format=png&transparent=true&f=image"
    )


def compute_bbox(lat: float, lng: float, buffer_deg: float = 0.005) -> list:
    """Compute bounding box around a point."""
    return [
        round(lng - buffer_deg, 6),
        round(lat - buffer_deg, 6),
        round(lng + buffer_deg, 6),
        round(lat + buffer_deg, 6),
    ]


def compute_bbox_from_geometry(geometry: dict, buffer_deg: float = 0.001) -> list:
    """Compute bounding box from a GeoJSON geometry."""
    coords = []
    geom_type = geometry.get("type", "")

    if geom_type == "Polygon":
        for ring in geometry.get("coordinates", []):
            coords.extend(ring)
    elif geom_type == "MultiPolygon":
        for polygon in geometry.get("coordinates", []):
            for ring in polygon:
                coords.extend(ring)
    elif geom_type == "Point":
        coords = [geometry["coordinates"]]

    if not coords:
        return None

    lngs = [c[0] for c in coords]
    lats = [c[1] for c in coords]

    return [
        round(min(lngs) - buffer_deg, 6),
        round(min(lats) - buffer_deg, 6),
        round(max(lngs) + buffer_deg, 6),
        round(max(lats) + buffer_deg, 6),
    ]


def build_map_urls(lat: float, lng: float, overlays: list, geometry: dict = None) -> dict:
    """
    Build all WMS/export map URLs for a site report.
    """
    if geometry:
        bbox = compute_bbox_from_geometry(geometry, buffer_deg=0.002)
    else:
        bbox = compute_bbox(lat, lng, buffer_deg=0.005)

    if not bbox:
        bbox = compute_bbox(lat, lng)

    maps = {
        "zone_wms": get_zone_map_url(bbox),
        "bbox": bbox,
        "overlay_wms_urls": {},
    }

    # Group overlay layer IDs by category for map URLs
    CATEGORY_LAYERS = {
        "bushfire": [31, 32, 33, 34, 35],
        "biodiversity": [22, 24, 26, 28, 30],
        "flood": [45, 46, 47],
        "height": [48, 50],
        "heritage": [51, 54, 55, 56, 57],
        "landslide": [58],
        "steep_land": [59],
        "coastal": [36, 37, 38],
        "infrastructure": [60, 61, 62, 63, 64, 65, 66, 67, 68],
        "scenic": [69, 70, 71],
        "water": [72, 73, 74],
        "acid_sulfate": [0],
    }

    # Only include map URLs for categories that have overlays
    overlay_categories = set()
    for group in overlays:
        cat = group.get("category", "")
        cat_lower = cat.lower().replace(" ", "_").replace(",", "")
        overlay_categories.add(cat_lower)

    for key, layer_ids in CATEGORY_LAYERS.items():
        # Always include the URL if there's a matching overlay
        for oc in overlay_categories:
            if key in oc or oc in key:
                maps["overlay_wms_urls"][key] = get_overlay_map_url(layer_ids, bbox)
                break

    # Transport
    maps["transport_wms"] = get_transport_map_url(bbox)

    return maps
