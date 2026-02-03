"""
Flood Information Service — Query SCC and QLD for flood mapping and studies.

Checks flood levels, minimum floor levels, and identifies flood studies
in the area to inform building design requirements.
"""

import asyncio
import httpx
from typing import Optional, List, Dict


# ─── Service URLs ─────────────────────────────────────────────────────────────

SCC_FLOOD_URL = (
    "https://geopublic.scc.qld.gov.au/arcgis/rest/services/"
    "Emergency/FloodMapping_scrc/MapServer/0"
)

QLD_FLOOD_STUDIES_URL = (
    "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
    "FloodCheck/FloodStudies/MapServer"
)

# QLD Flood Studies layers
FLOOD_STUDY_LAYER_0 = 0  # Flood studies
FLOOD_STUDY_LAYER_1 = 1  # Flood extents
FLOOD_STUDY_LAYER_2 = 2  # Additional flood information


async def _query_scc_flood_by_lotplan(
    lotplan: str,
    timeout: float = 15.0,
) -> List[Dict]:
    """Query SCC flood mapping by lotplan attribute."""
    url = f"{SCC_FLOOD_URL}/query"
    
    params = {
        "where": f"lotplan='{lotplan}'",
        "outFields": "SCENARIO,MAX_FLOOD_FORMAT,MAX_FLOOR_FORMAT,FREEBOARD,MAX_VEL_FORMAT,SOURCE,NOTES,COMPLEX,address_format,lotplan",
        "returnGeometry": "false",
        "f": "json",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("features", [])
        except Exception as e:
            print(f"⚠️  SCC Flood query failed for lotplan {lotplan}: {e}")
            return []


async def _query_qld_flood_studies(
    lat: float,
    lng: float,
    distance_m: int = 500,
    timeout: float = 15.0,
) -> Dict[str, List[Dict]]:
    """Query QLD flood studies near the parcel."""
    results = {}
    
    # Query all three layers in parallel
    tasks = []
    for layer_id in [FLOOD_STUDY_LAYER_0, FLOOD_STUDY_LAYER_1, FLOOD_STUDY_LAYER_2]:
        url = f"{QLD_FLOOD_STUDIES_URL}/{layer_id}/query"
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
            "resultRecordCount": 50,
        }
        tasks.append((layer_id, url, params))
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        for layer_id, url, params in tasks:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                results[f"layer_{layer_id}"] = data.get("features", [])
            except Exception as e:
                print(f"⚠️  QLD Flood studies query failed (layer {layer_id}): {e}")
                results[f"layer_{layer_id}"] = []
    
    return results


def _process_scc_flood(features: List[Dict]) -> Optional[Dict]:
    """Process SCC flood mapping results."""
    if not features:
        return None
    
    # Take the first/best result (there should typically be only one per parcel)
    feat = features[0]
    attrs = feat.get("attributes", {})
    
    flood_data = {
        "scenario": attrs.get("SCENARIO", "").strip(),
        "max_flood_level": attrs.get("MAX_FLOOD_FORMAT", "").strip(),
        "min_floor_level": attrs.get("MAX_FLOOR_FORMAT", "").strip(),
        "freeboard": attrs.get("FREEBOARD", "").strip(),
        "velocity": attrs.get("MAX_VEL_FORMAT", "").strip(),
        "source": attrs.get("SOURCE", "").strip(),
        "notes": attrs.get("NOTES", "").strip(),
        "complex_note": attrs.get("COMPLEX", "").strip(),
        "address": attrs.get("address_format", "").strip(),
        "lotplan": attrs.get("lotplan", "").strip(),
    }
    
    # Clean empty values
    flood_data = {k: v for k, v in flood_data.items() if v}
    
    return flood_data if flood_data else None


def _process_qld_flood_studies(study_results: Dict[str, List[Dict]]) -> List[Dict]:
    """Process QLD flood studies results."""
    studies = []
    
    # Combine all layers
    all_features = []
    for layer_results in study_results.values():
        all_features.extend(layer_results)
    
    # Process unique studies
    seen_studies = set()
    
    for feat in all_features:
        attrs = feat.get("attributes", {})
        
        # Try different field names for study identification
        study_name = (
            attrs.get("STUDY_NAME") or 
            attrs.get("StudyName") or 
            attrs.get("NAME") or 
            attrs.get("name") or
            attrs.get("TITLE")
        )
        
        if not study_name:
            continue
        
        study_name = study_name.strip()
        if study_name in seen_studies:
            continue
        
        seen_studies.add(study_name)
        
        study = {
            "name": study_name,
            "authority": attrs.get("AUTHORITY") or attrs.get("Authority") or "",
            "date": attrs.get("DATE") or attrs.get("Date") or "",
            "status": attrs.get("STATUS") or attrs.get("Status") or "",
            "type": attrs.get("TYPE") or attrs.get("Type") or "",
        }
        
        # Clean empty values
        study = {k: v.strip() if isinstance(v, str) else v for k, v in study.items() if v}
        
        studies.append(study)
    
    return studies[:5]  # Limit to 5 most relevant studies


def _parse_lotplan_for_flood(lot_plan: str) -> Optional[str]:
    """Convert lot/plan format to lotplan format for flood query."""
    if not lot_plan or "/" not in lot_plan:
        return None
    
    try:
        lot, plan = lot_plan.split("/", 1)
        # Remove RP/SP prefix and combine without separator
        plan_num = plan.replace("RP", "").replace("SP", "")
        return f"{lot.strip()}{plan_num.strip()}"
    except:
        return None


async def get_flood_info(lat: float, lng: float, lot_plan: str = None) -> dict:
    """
    Query SCC and QLD for flood information.
    
    Returns flood levels, floor requirements, and nearby flood studies.
    """
    # Convert lot/plan to lotplan format for SCC query
    lotplan = _parse_lotplan_for_flood(lot_plan) if lot_plan else None
    
    # Run queries in parallel
    tasks = []
    
    # SCC flood mapping (if we have lotplan)
    if lotplan:
        tasks.append(_query_scc_flood_by_lotplan(lotplan))
    else:
        tasks.append(asyncio.create_task(asyncio.sleep(0, result=[])))  # Dummy task
    
    # QLD flood studies
    tasks.append(_query_qld_flood_studies(lat, lng))
    
    scc_flood_features, qld_studies = await asyncio.gather(*tasks)
    
    # Process results
    flood_data = _process_scc_flood(scc_flood_features)
    flood_studies = _process_qld_flood_studies(qld_studies)
    
    # Determine flood status
    has_flood_data = flood_data is not None
    has_flood_studies = len(flood_studies) > 0
    
    # Build summary
    if has_flood_data:
        if flood_data.get("max_flood_level") and flood_data.get("min_floor_level"):
            summary = f"⚠️ Flood affected — Floor level {flood_data['min_floor_level']}"
        else:
            summary = "⚠️ Flood mapping data available — check requirements"
    else:
        if has_flood_studies:
            summary = "✅ No direct flood mapping — studies available in area"
        else:
            summary = "✅ No flood mapping or studies identified"
    
    # Add studies info to summary
    if has_flood_studies:
        if len(flood_studies) == 1:
            summary += f" (1 flood study in area)"
        else:
            summary += f" ({len(flood_studies)} flood studies in area)"
    
    return {
        "has_flood_data": has_flood_data,
        "flood_data": flood_data,
        "flood_studies": flood_studies,
        "has_flood_studies": has_flood_studies,
        "summary": summary,
        "lotplan_searched": lotplan,
    }