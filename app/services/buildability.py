"""Buildability Engine — What can you build on this lot?

Uses REAL zone data from SCC's ArcGIS services.
Falls back to PostGIS planning_rules table for detailed rules.
"""

import math
import psycopg2.extras
from typing import Optional

# ─── Zone-based planning rules (SCC Planning Scheme) ─────────────────────────
# These are the ACTUAL rules from the Sunshine Coast Planning Scheme 2014.
# Used when the zone comes from SCC's real service.

ZONE_RULES = {
    # ── Residential Zones ──
    "Low Density Residential Zone": {
        "zone_category": "Residential Zones Category",
        "max_height_m": 8.5,
        "max_storeys": 2,
        "max_site_cover_pct": 50,
        "front_setback_m": 6.0,
        "side_setback_m": 1.5,
        "rear_setback_m": 6.0,
        "min_lot_size_sqm": 400,
        "min_frontage_m": 12,
        "max_dwelling_density": "1 per lot",
        "accepted_uses": ["Dwelling house", "Home-based business", "Caretaker's accommodation"],
        "assessable_uses": ["Dual occupancy", "Secondary dwelling", "Community facility", "Childcare centre"],
    },
    "Low-medium Density Residential Zone": {
        "zone_category": "Residential Zones Category",
        "max_height_m": 12.0,
        "max_storeys": 3,
        "max_site_cover_pct": 50,
        "front_setback_m": 6.0,
        "side_setback_m": 2.0,
        "rear_setback_m": 6.0,
        "min_lot_size_sqm": 300,
        "min_frontage_m": 10,
        "max_dwelling_density": "1 per 300sqm",
        "accepted_uses": ["Dwelling house", "Dual occupancy", "Home-based business"],
        "assessable_uses": ["Multiple dwelling", "Short-term accommodation", "Rooming accommodation", "Childcare centre"],
    },
    "Medium Density Residential Zone": {
        "zone_category": "Residential Zones Category",
        "max_height_m": 15.0,
        "max_storeys": 4,
        "max_site_cover_pct": 50,
        "front_setback_m": 6.0,
        "side_setback_m": 3.0,
        "rear_setback_m": 6.0,
        "min_lot_size_sqm": 200,
        "min_frontage_m": 10,
        "max_dwelling_density": "1 per 200sqm",
        "accepted_uses": ["Dwelling house", "Dual occupancy", "Multiple dwelling"],
        "assessable_uses": ["Short-term accommodation", "Rooming accommodation", "Retirement facility", "Childcare centre"],
    },
    "High Density Residential Zone": {
        "zone_category": "Residential Zones Category",
        "max_height_m": 22.0,
        "max_storeys": 6,
        "max_site_cover_pct": 60,
        "front_setback_m": 6.0,
        "side_setback_m": 3.0,
        "rear_setback_m": 6.0,
        "min_lot_size_sqm": 150,
        "min_frontage_m": 15,
        "max_dwelling_density": "1 per 100sqm",
        "accepted_uses": ["Dwelling house", "Dual occupancy", "Multiple dwelling"],
        "assessable_uses": ["Short-term accommodation", "Rooming accommodation", "Retirement facility", "Shop (< 250m²)"],
    },
    # ── Centre Zones ──
    "Principal Centre Zone": {
        "zone_category": "Centre Zones Category",
        "max_height_m": 45.0,
        "max_storeys": 12,
        "max_site_cover_pct": 80,
        "front_setback_m": 0,
        "side_setback_m": 0,
        "rear_setback_m": 3.0,
        "min_lot_size_sqm": 200,
        "min_frontage_m": None,
        "max_dwelling_density": "1 per 50sqm",
        "accepted_uses": ["Shop", "Office", "Food and drink outlet", "Multiple dwelling"],
        "assessable_uses": ["Hotel", "Nightclub", "Indoor sport", "Health care service", "Educational establishment"],
    },
    "Major Centre Zone": {
        "zone_category": "Centre Zones Category",
        "max_height_m": 25.0,
        "max_storeys": 7,
        "max_site_cover_pct": 80,
        "front_setback_m": 0,
        "side_setback_m": 0,
        "rear_setback_m": 3.0,
        "min_lot_size_sqm": 200,
        "min_frontage_m": None,
        "max_dwelling_density": "1 per 75sqm",
        "accepted_uses": ["Shop", "Office", "Food and drink outlet", "Multiple dwelling"],
        "assessable_uses": ["Hotel", "Indoor sport", "Health care service", "Educational establishment"],
    },
    "District Centre Zone": {
        "zone_category": "Centre Zones Category",
        "max_height_m": 15.0,
        "max_storeys": 4,
        "max_site_cover_pct": 70,
        "front_setback_m": 0,
        "side_setback_m": 0,
        "rear_setback_m": 3.0,
        "min_lot_size_sqm": 200,
        "min_frontage_m": None,
        "max_dwelling_density": "1 per 100sqm",
        "accepted_uses": ["Shop", "Office", "Food and drink outlet", "Health care service"],
        "assessable_uses": ["Multiple dwelling", "Short-term accommodation", "Hotel", "Childcare centre"],
    },
    "Local Centre Zone": {
        "zone_category": "Centre Zones Category",
        "max_height_m": 12.0,
        "max_storeys": 3,
        "max_site_cover_pct": 60,
        "front_setback_m": 0,
        "side_setback_m": 0,
        "rear_setback_m": 3.0,
        "min_lot_size_sqm": 300,
        "min_frontage_m": None,
        "max_dwelling_density": "1 per 150sqm",
        "accepted_uses": ["Shop", "Food and drink outlet", "Office (< 250m²)", "Health care service"],
        "assessable_uses": ["Multiple dwelling", "Short-term accommodation", "Childcare centre"],
    },
    "Neighbourhood Centre Zone": {
        "zone_category": "Centre Zones Category",
        "max_height_m": 8.5,
        "max_storeys": 2,
        "max_site_cover_pct": 60,
        "front_setback_m": 3.0,
        "side_setback_m": 0,
        "rear_setback_m": 3.0,
        "min_lot_size_sqm": 400,
        "min_frontage_m": None,
        "max_dwelling_density": "1 per 200sqm",
        "accepted_uses": ["Shop (< 500m²)", "Food and drink outlet", "Health care service"],
        "assessable_uses": ["Dwelling house", "Childcare centre"],
    },
    # ── Industry Zones ──
    "Low Impact Industry Zone": {
        "zone_category": "Industry Zones Category",
        "max_height_m": 12.0,
        "max_storeys": 2,
        "max_site_cover_pct": 70,
        "front_setback_m": 6.0,
        "side_setback_m": 3.0,
        "rear_setback_m": 6.0,
        "min_lot_size_sqm": 1000,
        "min_frontage_m": 20,
        "max_dwelling_density": "Caretaker only",
        "accepted_uses": ["Low impact industry", "Warehouse", "Service industry"],
        "assessable_uses": ["Medium impact industry", "Outdoor storage", "Transport depot"],
    },
    "Medium Impact Industry Zone": {
        "zone_category": "Industry Zones Category",
        "max_height_m": 15.0,
        "max_storeys": 3,
        "max_site_cover_pct": 70,
        "front_setback_m": 10.0,
        "side_setback_m": 5.0,
        "rear_setback_m": 10.0,
        "min_lot_size_sqm": 2000,
        "min_frontage_m": 30,
        "max_dwelling_density": "Caretaker only",
        "accepted_uses": ["Medium impact industry", "Low impact industry", "Warehouse"],
        "assessable_uses": ["High impact industry", "Transport depot", "Outdoor storage"],
    },
    "High Impact Industry Zone": {
        "zone_category": "Industry Zones Category",
        "max_height_m": 15.0,
        "max_storeys": 3,
        "max_site_cover_pct": 70,
        "front_setback_m": 20.0,
        "side_setback_m": 10.0,
        "rear_setback_m": 20.0,
        "min_lot_size_sqm": 4000,
        "min_frontage_m": 50,
        "max_dwelling_density": "Caretaker only",
        "accepted_uses": ["High impact industry", "Medium impact industry", "Special industry"],
        "assessable_uses": ["Extractive industry", "Hazardous chemical facility"],
    },
    # ── Special Purpose Zones ──
    "Sport and Recreation Zone": {
        "zone_category": "Specialised Zones Category",
        "max_height_m": 12.0,
        "max_storeys": 2,
        "max_site_cover_pct": 40,
        "front_setback_m": 6.0,
        "side_setback_m": 3.0,
        "rear_setback_m": 6.0,
        "min_lot_size_sqm": None,
        "min_frontage_m": None,
        "max_dwelling_density": "Caretaker only",
        "accepted_uses": ["Park", "Sport and recreation"],
        "assessable_uses": ["Club", "Food and drink outlet", "Market"],
    },
    "Open Space Zone": {
        "zone_category": "Specialised Zones Category",
        "max_height_m": 8.5,
        "max_storeys": 2,
        "max_site_cover_pct": 10,
        "front_setback_m": 6.0,
        "side_setback_m": 3.0,
        "rear_setback_m": 6.0,
        "min_lot_size_sqm": None,
        "min_frontage_m": None,
        "max_dwelling_density": "None",
        "accepted_uses": ["Park"],
        "assessable_uses": ["Environment facility", "Utility installation"],
    },
    "Environmental Management and Conservation Zone": {
        "zone_category": "Other Zones Category",
        "max_height_m": 8.5,
        "max_storeys": 2,
        "max_site_cover_pct": 10,
        "front_setback_m": 10.0,
        "side_setback_m": 5.0,
        "rear_setback_m": 10.0,
        "min_lot_size_sqm": None,
        "min_frontage_m": None,
        "max_dwelling_density": "Caretaker only",
        "accepted_uses": ["Park", "Nature-based tourism"],
        "assessable_uses": ["Environment facility", "Dwelling house"],
    },
    "Community Facilities Zone": {
        "zone_category": "Specialised Zones Category",
        "max_height_m": 12.0,
        "max_storeys": 3,
        "max_site_cover_pct": 50,
        "front_setback_m": 6.0,
        "side_setback_m": 3.0,
        "rear_setback_m": 6.0,
        "min_lot_size_sqm": None,
        "min_frontage_m": None,
        "max_dwelling_density": "Caretaker only",
        "accepted_uses": ["Community facility", "Educational establishment", "Hospital"],
        "assessable_uses": ["Childcare centre", "Health care service", "Place of worship"],
    },
    # ── Tourism Zone ──
    "Tourist Accommodation Zone": {
        "zone_category": "Residential Zones Category",
        "max_height_m": 15.0,
        "max_storeys": 4,
        "max_site_cover_pct": 50,
        "front_setback_m": 6.0,
        "side_setback_m": 3.0,
        "rear_setback_m": 6.0,
        "min_lot_size_sqm": 800,
        "min_frontage_m": 20,
        "max_dwelling_density": "1 per 200sqm",
        "accepted_uses": ["Short-term accommodation", "Tourist park"],
        "assessable_uses": ["Multiple dwelling", "Food and drink outlet", "Shop (< 100m²)", "Resort complex"],
    },
    # ── Rural Zones ──
    "Rural Zone": {
        "zone_category": "Other Zones Category",
        "max_height_m": 8.5,
        "max_storeys": 2,
        "max_site_cover_pct": 10,
        "front_setback_m": 20.0,
        "side_setback_m": 10.0,
        "rear_setback_m": 20.0,
        "min_lot_size_sqm": 40000,
        "min_frontage_m": 100,
        "max_dwelling_density": "1 per lot",
        "accepted_uses": ["Dwelling house", "Home-based business", "Animal husbandry", "Cropping", "Rural activity"],
        "assessable_uses": ["Rural industry", "Roadside stall", "Tourist park", "Nature-based tourism", "Winery"],
    },
    "Rural Residential Zone": {
        "zone_category": "Other Zones Category",
        "max_height_m": 8.5,
        "max_storeys": 2,
        "max_site_cover_pct": 15,
        "front_setback_m": 10.0,
        "side_setback_m": 5.0,
        "rear_setback_m": 10.0,
        "min_lot_size_sqm": 4000,
        "min_frontage_m": 40,
        "max_dwelling_density": "1 per lot",
        "accepted_uses": ["Dwelling house", "Home-based business"],
        "assessable_uses": ["Dual occupancy", "Nature-based tourism", "Roadside stall", "Rural activity"],
    },
    # ── Emerging Community ──
    "Emerging Community Zone": {
        "zone_category": "Other Zones Category",
        "max_height_m": 8.5,
        "max_storeys": 2,
        "max_site_cover_pct": 50,
        "front_setback_m": 6.0,
        "side_setback_m": 1.5,
        "rear_setback_m": 6.0,
        "min_lot_size_sqm": 600,
        "min_frontage_m": 15,
        "max_dwelling_density": "1 per lot",
        "accepted_uses": ["Dwelling house", "Home-based business"],
        "assessable_uses": ["Park", "Community facility"],
    },
    # ── Mixed Use ──
    "Mixed Use Zone": {
        "zone_category": "Centre Zones Category",
        "max_height_m": 15.0,
        "max_storeys": 4,
        "max_site_cover_pct": 80,
        "front_setback_m": 0,
        "side_setback_m": 0,
        "rear_setback_m": 3.0,
        "min_lot_size_sqm": 200,
        "min_frontage_m": None,
        "max_dwelling_density": "1 per 100sqm",
        "accepted_uses": ["Shop", "Office", "Food and drink outlet", "Multiple dwelling"],
        "assessable_uses": ["Hotel", "Health care service", "Short-term accommodation"],
    },
    "Specialised Centre Zone": {
        "zone_category": "Centre Zones Category",
        "max_height_m": 12.0,
        "max_storeys": 3,
        "max_site_cover_pct": 60,
        "front_setback_m": 6.0,
        "side_setback_m": 3.0,
        "rear_setback_m": 6.0,
        "min_lot_size_sqm": 1000,
        "min_frontage_m": 20,
        "max_dwelling_density": "Caretaker only",
        "accepted_uses": ["Office", "Research and technology", "Health care service"],
        "assessable_uses": ["Shop", "Food and drink outlet", "Educational establishment"],
    },
}


def get_zone_rules(zone_code: str) -> Optional[dict]:
    """
    Get planning rules for a zone from our built-in rule set.
    The zone_code comes from SCC's REAL service (e.g. "Rural Zone").
    """
    rules = ZONE_RULES.get(zone_code)
    if rules:
        return {**rules, "zone_code": zone_code, "source": "scc_planning_scheme"}

    # Try fuzzy match (e.g. "Rural" → "Rural Zone")
    zone_lower = zone_code.lower()
    for key, val in ZONE_RULES.items():
        if zone_lower in key.lower() or key.lower() in zone_lower:
            return {**val, "zone_code": key, "source": "scc_planning_scheme_fuzzy"}

    return None


def try_db_rules(zone_code: str, lga: str = "Sunshine Coast Regional") -> Optional[dict]:
    """Fallback: try PostGIS planning_rules table."""
    try:
        from app.services.db import get_conn
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT * FROM planning_rules
            WHERE zone_code = %s AND lga = %s
            LIMIT 1
        """, (zone_code, lga))
        row = cur.fetchone()
        if row:
            return dict(row)
    except Exception:
        pass
    return None


def estimate_zone_from_land_use(alum_code: str) -> Optional[dict]:
    """Legacy: Map ALUMC land use code to likely planning zone."""
    try:
        from app.services.db import get_conn
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT likely_zone, confidence
            FROM land_use_zone_map
            WHERE alum_code = %s
            ORDER BY confidence DESC LIMIT 1
        """, (alum_code,))
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def get_planning_rules(zone_code: str, lga: str = "Sunshine Coast Regional") -> Optional[dict]:
    """Get planning rules — tries built-in first, then PostGIS fallback."""
    rules = get_zone_rules(zone_code)
    if rules:
        return rules

    db_rules = try_db_rules(zone_code, lga)
    if db_rules:
        return db_rules

    return None


def calculate_buildability(
    parcel: dict,
    zone: dict,
    rules: dict = None,
    overlays: list = None,
    height_override: float = None,
) -> dict:
    """
    Calculate what can be built given parcel data and planning rules.
    
    Args:
        parcel: Parcel info dict with area_sqm etc.
        zone: Zone dict from SCC {code, category, label}
        rules: Planning rules dict (from get_zone_rules or DB)
        overlays: List of overlay groups
        height_override: Real height from SCC Height overlay
    """
    area = float(parcel.get("area_sqm") or 0)
    zone_code = zone.get("code", "Unknown") if zone else "Unknown"
    zone_category = zone.get("category", "") if zone else ""

    if not rules:
        rules = get_zone_rules(zone_code) or {}

    if not area:
        return {
            "zone": {"code": zone_code, "category": zone_category},
            "error": "No lot area data — cannot calculate buildability",
        }

    # Extract rules
    def f(v, default=None):
        if v is None:
            return default
        return float(v)

    # Use SCC height overlay if available, otherwise use zone default
    max_height = height_override if height_override else f(rules.get("max_height_m"))
    max_storeys = rules.get("max_storeys")
    max_site_cover = f(rules.get("max_site_cover_pct"), 50)
    front_setback = f(rules.get("front_setback_m"), 6)
    side_setback = f(rules.get("side_setback_m"), 1.5)
    rear_setback = f(rules.get("rear_setback_m"), 6)
    min_lot_size = f(rules.get("min_lot_size_sqm"), 0)
    min_frontage = f(rules.get("min_frontage_m"))
    density_rule = rules.get("max_dwelling_density", "")

    # Calculate buildable envelope
    max_footprint = area * (max_site_cover / 100)

    # Approximate as square for setback calculation
    side_length = math.sqrt(area)
    buildable_width = max(0, side_length - (2 * side_setback))
    buildable_depth = max(0, side_length - front_setback - rear_setback)
    buildable_area_after_setbacks = buildable_width * buildable_depth
    effective_footprint = min(max_footprint, buildable_area_after_setbacks)

    # GFA
    storeys = max_storeys or 1
    max_gfa = effective_footprint * storeys

    # Max dwellings
    max_dwellings = 1
    if density_rule:
        if "per" in str(density_rule) and "lot" not in str(density_rule).lower():
            try:
                parts = str(density_rule).split("per")
                units = int(parts[0].strip())
                per_sqm = int("".join(filter(str.isdigit, parts[1])))
                if per_sqm > 0:
                    max_dwellings = max(1, int(area / per_sqm) * units)
            except (ValueError, IndexError):
                pass
        elif "lot" in str(density_rule).lower():
            max_dwellings = 1
        elif density_rule in ("Caretaker only", "None"):
            max_dwellings = 0

    # Subdivision
    can_subdivide = area >= (min_lot_size * 2) if min_lot_size else False
    max_new_lots = int(area / min_lot_size) if min_lot_size and min_lot_size > 0 else 0

    # Constraints from overlays
    constraints = []
    if overlays:
        for group in overlays:
            cat = group.get("category", "")
            layers = group.get("layers", [])
            for layer in layers:
                lname = layer.get("label", layer.get("name", ""))
                lid = layer.get("layer_id")
                if "bushfire" in cat.lower():
                    constraints.append({
                        "type": "bushfire",
                        "icon": "🔥",
                        "text": f"Bushfire: {lname} — BAL assessment required",
                    })
                elif "flood" in cat.lower():
                    constraints.append({
                        "type": "flood",
                        "icon": "🌊",
                        "text": f"Flood: {lname} — may require flood assessment and minimum floor levels",
                    })
                elif "heritage" in cat.lower() or "character" in cat.lower():
                    constraints.append({
                        "type": "heritage",
                        "icon": "🏛️",
                        "text": f"Heritage/Character: {lname} — design controls apply",
                    })
                elif "landslide" in cat.lower():
                    constraints.append({
                        "type": "landslide",
                        "icon": "⛰️",
                        "text": f"Landslide Hazard: {lname} — geotechnical assessment required",
                    })
                elif "steep" in cat.lower() or "slope" in cat.lower():
                    constraints.append({
                        "type": "steep_land",
                        "icon": "📐",
                        "text": f"Steep Land: {lname} — earthworks and retaining may be needed",
                    })
                elif "biodiversity" in cat.lower() or "waterway" in cat.lower() or "wetland" in cat.lower():
                    constraints.append({
                        "type": "biodiversity",
                        "icon": "🌿",
                        "text": f"Biodiversity: {lname} — ecological assessment likely required",
                    })
                elif "coastal" in cat.lower():
                    constraints.append({
                        "type": "coastal",
                        "icon": "🏖️",
                        "text": f"Coastal: {lname} — coastal protection requirements apply",
                    })
                elif "acid" in cat.lower():
                    constraints.append({
                        "type": "acid_sulfate",
                        "icon": "⚗️",
                        "text": f"Acid Sulfate Soils — soil investigation may be required",
                    })
                elif cat.lower() != "height of buildings and structures":
                    constraints.append({
                        "type": "other",
                        "icon": "📌",
                        "text": f"{cat}: {lname}",
                    })

    # Lot compliance
    lot_compliant = True
    compliance_issues = []
    if min_lot_size and area < min_lot_size:
        lot_compliant = False
        compliance_issues.append(f"Lot is {area:,.0f}m² but zone requires min {min_lot_size:,.0f}m²")
    if min_frontage:
        compliance_issues.append(f"Check frontage ≥ {min_frontage}m (unable to verify without survey)")

    return {
        "zone": {
            "code": zone_code,
            "category": zone_category,
            "source": "scc_arcgis",
        },
        "rules": {
            "max_height_m": float(max_height) if max_height else None,
            "max_storeys": max_storeys,
            "min_lot_size_sqm": float(min_lot_size) if min_lot_size else None,
            "max_site_cover_pct": float(max_site_cover),
            "front_setback_m": float(front_setback),
            "side_setback_m": float(side_setback),
            "rear_setback_m": float(rear_setback),
            "min_frontage_m": float(min_frontage) if min_frontage else None,
        },
        "buildable_envelope": {
            "max_footprint_sqm": round(effective_footprint, 1),
            "max_gfa_sqm": round(max_gfa, 1),
            "max_dwellings": max_dwellings,
            "buildable_area_after_setbacks_sqm": round(buildable_area_after_setbacks, 1),
        },
        "subdivision": {
            "can_subdivide": can_subdivide,
            "max_new_lots": max_new_lots,
            "min_lot_size_sqm": float(min_lot_size) if min_lot_size else None,
        },
        "uses": {
            "accepted": rules.get("accepted_uses", []),
            "assessable": rules.get("assessable_uses", []),
        },
        "constraints": constraints,
        "lot_compliance": {
            "compliant": lot_compliant,
            "issues": compliance_issues,
        },
        "disclaimer": (
            "Indicative only based on Sunshine Coast Planning Scheme 2014. "
            "Zone data sourced from SCC ArcGIS services. "
            "Always verify with Sunshine Coast Council before making decisions."
        ),
    }
