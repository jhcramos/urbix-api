"""QLD Spatial Services — ArcGIS REST API Client"""

import httpx
from typing import Optional
from app.config import (
    PARCELS_URL, ADDRESSES_URL, TENURE_URL, DEFAULT_SR, MAX_RECORDS
)


async def query_arcgis(
    url: str,
    where: str = "1=1",
    geometry: Optional[str] = None,
    geometry_type: str = "esriGeometryPoint",
    spatial_rel: str = "esriSpatialRelIntersects",
    out_fields: str = "*",
    return_geometry: bool = True,
    out_sr: int = DEFAULT_SR,
    result_record_count: int = MAX_RECORDS,
    output_format: str = "geojson",
) -> dict:
    """Generic ArcGIS REST query."""
    params = {
        "where": where,
        "outFields": out_fields,
        "returnGeometry": str(return_geometry).lower(),
        "outSR": out_sr,
        "f": output_format,
        "resultRecordCount": result_record_count,
    }
    if geometry:
        params["geometry"] = geometry
        params["geometryType"] = geometry_type
        params["spatialRel"] = spatial_rel
        params["inSR"] = out_sr

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{url}/query", params=params)
        resp.raise_for_status()
        return resp.json()


STREET_ABBREVS = {
    " St ": " Street ", " St,": " Street,", " Rd ": " Road ", " Rd,": " Road,",
    " Ave ": " Avenue ", " Ave,": " Avenue,", " Dr ": " Drive ", " Dr,": " Drive,",
    " Ct ": " Court ", " Ct,": " Court,", " Pl ": " Place ", " Pl,": " Place,",
    " Cres ": " Crescent ", " Cres,": " Crescent,", " Tce ": " Terrace ",
    " Ln ": " Lane ", " Pde ": " Parade ", " Blvd ": " Boulevard ",
    " Hwy ": " Highway ", " Cct ": " Circuit ", " Esp ": " Esplanade ",
    " Cl ": " Close ", " Gr ": " Grove ", " Way ": " Way ",
}


def _expand_street_abbrevs(text: str) -> str:
    """Expand common street abbreviations to match QLD data format."""
    # Add trailing space for end-of-string matches
    t = text + " "
    for abbr, full in STREET_ABBREVS.items():
        t = t.replace(abbr, full)
    return t.strip()


async def search_addresses(query: str, limit: int = 10) -> list:
    """Search addresses by text (type-ahead)."""
    q = query.strip().replace("'", "''")
    q_expanded = _expand_street_abbrevs(q)
    where = f"address LIKE '%{q_expanded}%'"

    data = await query_arcgis(
        ADDRESSES_URL,
        where=where,
        return_geometry=True,
        result_record_count=limit,
        out_sr=DEFAULT_SR,
    )

    features = data.get("features", [])
    results = []
    for f in features:
        props = f.get("properties", {}) if "properties" in f else f.get("attributes", {})
        geom = f.get("geometry")
        
        # Handle both GeoJSON and esri geometry formats
        lat, lng = None, None
        if geom:
            if "coordinates" in geom:
                lng, lat = geom["coordinates"][0], geom["coordinates"][1]
            elif "y" in geom and "x" in geom:
                # Need to convert from web mercator if needed
                lat = props.get("latitude")
                lng = props.get("longitude")

        results.append({
            "address": props.get("address", ""),
            "locality": props.get("locality", ""),
            "lot": props.get("lot", ""),
            "plan": props.get("plan", ""),
            "lotplan": props.get("lotplan", ""),
            "street_name": props.get("street_name", ""),
            "street_number": props.get("street_number", ""),
            "lat": lat,
            "lng": lng,
        })
    return results


async def get_parcel_by_lotplan(lot: str, plan: str) -> Optional[dict]:
    """Get a parcel by Lot/Plan reference."""
    where = f"lot='{lot}' AND plan='{plan}'"

    data = await query_arcgis(
        PARCELS_URL,
        where=where,
        return_geometry=True,
        result_record_count=5,
    )

    features = data.get("features", [])
    if not features:
        return None

    # Prefer Base parcel over Easement
    base = [f for f in features if f.get("properties", {}).get("cover_typ", "") == "Base"]
    feature = base[0] if base else features[0]

    return _format_parcel(feature)


async def get_parcel_by_point(lat: float, lng: float) -> Optional[dict]:
    """Get parcel at a lat/lng point."""
    geometry = f"{lng},{lat}"

    data = await query_arcgis(
        PARCELS_URL,
        geometry=geometry,
        geometry_type="esriGeometryPoint",
        spatial_rel="esriSpatialRelIntersects",
        return_geometry=True,
        result_record_count=5,
    )

    features = data.get("features", [])
    if not features:
        return None

    # Prefer Base parcel
    base = [f for f in features if f.get("properties", {}).get("cover_typ", "") == "Base"]
    feature = base[0] if base else features[0]

    return _format_parcel(feature)


async def get_tenure_for_parcel(lot: str, plan: str) -> Optional[str]:
    """Get tenure type for a parcel."""
    where = f"lot='{lot}' AND plan='{plan}'"

    data = await query_arcgis(
        TENURE_URL,
        where=where,
        return_geometry=False,
        result_record_count=1,
    )

    features = data.get("features", [])
    if features:
        props = features[0].get("properties", {}) if "properties" in features[0] else features[0].get("attributes", {})
        return props.get("tenure", None)
    return None


def _format_parcel(feature: dict) -> dict:
    """Format a raw ArcGIS parcel feature into our API response."""
    props = feature.get("properties", {})
    geom = feature.get("geometry")

    return {
        "parcel": {
            "lot": props.get("lot", ""),
            "plan": props.get("plan", ""),
            "lot_plan": f"{props.get('lot', '')}/{props.get('plan', '')}",
            "lotplan": props.get("lotplan", ""),
            "parcel_type": props.get("parcel_typ", ""),
            "cover_type": props.get("cover_typ", ""),
            "tenure": props.get("tenure", ""),
            "area_sqm": props.get("lot_area", None),
            "locality": props.get("locality", ""),
            "shire_name": props.get("shire_name", ""),
            "feature_name": props.get("feat_name", ""),
        },
        "geometry": geom,
    }
