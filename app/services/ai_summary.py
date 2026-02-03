"""
AI Site Analysis Service — Template-based intelligent site summary.

Compiles data from all services (zone, overlays, DAs, buildability, 
constraints, infrastructure, flood) into a structured, plain-English
site analysis with scoring, strengths, risks, and precedent analysis.
"""

from typing import Optional, List, Dict, Any


# ─── Zone category links to SCC Planning Scheme chapters ──────────────────────

SCC_SCHEME_BASE = "https://www.sunshinecoast.qld.gov.au/development/planning-documents/sunshine-coast-planning-scheme-2014"
SCC_ZONE_LINKS = {
    "Low Density Residential Zone": f"{SCC_SCHEME_BASE}/zones/low-density-residential-zone",
    "Low-medium Density Residential Zone": f"{SCC_SCHEME_BASE}/zones/low-medium-density-residential-zone",
    "Medium Density Residential Zone": f"{SCC_SCHEME_BASE}/zones/medium-density-residential-zone",
    "High Density Residential Zone": f"{SCC_SCHEME_BASE}/zones/high-density-residential-zone",
    "Rural Zone": f"{SCC_SCHEME_BASE}/zones/rural-zone",
    "Rural Residential Zone": f"{SCC_SCHEME_BASE}/zones/rural-residential-zone",
    "Principal Centre Zone": f"{SCC_SCHEME_BASE}/zones/principal-centre-zone",
    "Major Centre Zone": f"{SCC_SCHEME_BASE}/zones/major-centre-zone",
    "District Centre Zone": f"{SCC_SCHEME_BASE}/zones/district-centre-zone",
    "Local Centre Zone": f"{SCC_SCHEME_BASE}/zones/local-centre-zone",
    "Neighbourhood Centre Zone": f"{SCC_SCHEME_BASE}/zones/neighbourhood-centre-zone",
    "Low Impact Industry Zone": f"{SCC_SCHEME_BASE}/zones/low-impact-industry-zone",
    "Medium Impact Industry Zone": f"{SCC_SCHEME_BASE}/zones/medium-impact-industry-zone",
    "High Impact Industry Zone": f"{SCC_SCHEME_BASE}/zones/high-impact-industry-zone",
    "Sport and Recreation Zone": f"{SCC_SCHEME_BASE}/zones/sport-and-recreation-zone",
    "Open Space Zone": f"{SCC_SCHEME_BASE}/zones/open-space-zone",
    "Environmental Management and Conservation Zone": f"{SCC_SCHEME_BASE}/zones/environmental-management-and-conservation-zone",
    "Community Facilities Zone": f"{SCC_SCHEME_BASE}/zones/community-facilities-zone",
    "Tourist Accommodation Zone": f"{SCC_SCHEME_BASE}/zones/tourist-accommodation-zone",
    "Emerging Community Zone": f"{SCC_SCHEME_BASE}/zones/emerging-community-zone",
    "Mixed Use Zone": f"{SCC_SCHEME_BASE}/zones/mixed-use-zone",
    "Specialised Centre Zone": f"{SCC_SCHEME_BASE}/zones/specialised-centre-zone",
}

ZONE_COLORS = {
    "Low Density Residential Zone": "#ffdcdc",
    "Low-medium Density Residential Zone": "#ffb4b4",
    "Medium Density Residential Zone": "#ffa4a4",
    "High Density Residential Zone": "#aa0000",
    "Tourist Accommodation Zone": "#ff3232",
    "Principal Centre Zone": "#0032ff",
    "Major Centre Zone": "#426bff",
    "District Centre Zone": "#7082aa",
    "Local Centre Zone": "#86a6ff",
    "Neighbourhood Centre Zone": "#a0c0ff",
    "Sport and Recreation Zone": "#afe1c8",
    "Open Space Zone": "#6eaf4b",
    "Environmental Management and Conservation Zone": "#327d00",
    "Low Impact Industry Zone": "#e1c8e1",
    "Medium Impact Industry Zone": "#c88fc8",
    "High Impact Industry Zone": "#af56af",
    "Community Facilities Zone": "#ffff64",
    "Emerging Community Zone": "#e8beaf",
    "Rural Zone": "#f0fae6",
    "Rural Residential Zone": "#a07878",
    "Specialised Centre Zone": "#a9a9a9",
    "Mixed Use Zone": "#b3d234",
}


def _calculate_constraints_score(
    overlays: list,
    flood_info: dict,
    constraints: dict,
    infrastructure: dict,
    buildability: dict,
) -> int:
    """
    Calculate a Site Constraints Score (1-100).
    100 = easy to develop (no constraints), 1 = very constrained.
    """
    score = 100
    deductions = []

    # Overlay-based deductions
    if overlays:
        for group in overlays:
            cat = (group.get("category") or "").lower()
            layers = group.get("layers", [])
            count = len(layers)

            if "bushfire" in cat:
                score -= 12 * count
                deductions.append(f"Bushfire overlay (-{12 * count})")
            elif "flood" in cat:
                score -= 15 * count
                deductions.append(f"Flood overlay (-{15 * count})")
            elif "heritage" in cat or "character" in cat:
                score -= 8 * count
                deductions.append(f"Heritage/Character (-{8 * count})")
            elif "landslide" in cat:
                score -= 15
                deductions.append("Landslide hazard (-15)")
            elif "steep" in cat or "slope" in cat:
                score -= 10
                deductions.append("Steep land (-10)")
            elif "biodiversity" in cat or "waterway" in cat or "wetland" in cat:
                score -= 10 * count
                deductions.append(f"Biodiversity/Waterway (-{10 * count})")
            elif "coastal" in cat:
                score -= 10 * count
                deductions.append(f"Coastal protection (-{10 * count})")
            elif "acid" in cat:
                score -= 5
                deductions.append("Acid sulfate soils (-5)")
            elif "scenic" in cat:
                score -= 5
                deductions.append("Scenic amenity (-5)")

    # Flood deductions
    if flood_info and flood_info.get("has_flood_data"):
        score -= 15
        deductions.append("Direct flood mapping (-15)")

    # Constraint deductions (easements, covenants, environmental)
    if constraints:
        ease_count = constraints.get("easements_count", 0)
        cov_count = constraints.get("covenants_count", 0)
        if ease_count > 0:
            score -= 5 * ease_count
            deductions.append(f"Easements ({ease_count}) (-{5 * ease_count})")
        if cov_count > 0:
            score -= 5 * cov_count
            deductions.append(f"Covenants ({cov_count}) (-{5 * cov_count})")
        koala = constraints.get("koala", {})
        if koala.get("status"):
            score -= 10
            deductions.append("Koala habitat (-10)")
        esa = constraints.get("esa", {})
        if esa.get("status"):
            score -= 10
            deductions.append("ESA area (-10)")

    # Infrastructure deductions (missing = harder to develop)
    if infrastructure:
        if not infrastructure.get("water", {}).get("available"):
            score -= 8
            deductions.append("No reticulated water (-8)")
        if not infrastructure.get("sewer", {}).get("available"):
            score -= 8
            deductions.append("No reticulated sewer (-8)")

    # Lot compliance
    if buildability:
        lot_comp = buildability.get("lot_compliance", {})
        if not lot_comp.get("compliant", True):
            score -= 5
            deductions.append("Lot non-compliant (-5)")

    return max(1, min(100, score)), deductions


def _analyze_da_precedent(da_history: dict) -> dict:
    """Analyze DA history for precedent patterns."""
    on_parcel = da_history.get("on_parcel", [])
    nearby = da_history.get("nearby", [])

    all_das = on_parcel + nearby

    approved = 0
    refused = 0
    in_progress = 0
    lapsed = 0
    categories = {}

    for da in all_das:
        decision = (da.get("decision") or "").lower()
        category = da.get("category", "Other")

        if decision and "approved" in decision:
            approved += 1
        elif decision and "refused" in decision:
            refused += 1
        elif decision and "lapsed" in decision:
            lapsed += 1
        else:
            in_progress += 1

        categories[category] = categories.get(category, 0) + 1

    # Assess
    total = approved + refused + lapsed + in_progress
    if total == 0:
        assessment = "No precedent data available in area"
        outlook = "neutral"
    elif refused == 0 and approved > 0:
        assessment = "Strong approval trend — all applications in the area have been approved"
        outlook = "positive"
    elif approved > refused * 2:
        assessment = "Positive approval trend — majority of applications approved"
        outlook = "positive"
    elif refused > approved:
        assessment = "Challenging area — more refusals than approvals"
        outlook = "negative"
    else:
        assessment = "Mixed results — assess carefully against planning scheme"
        outlook = "neutral"

    return {
        "approved_count": approved,
        "refused_count": refused,
        "in_progress_count": in_progress,
        "lapsed_count": lapsed,
        "total_count": total,
        "on_parcel_count": len(on_parcel),
        "nearby_count": len(nearby),
        "top_categories": dict(sorted(categories.items(), key=lambda x: -x[1])[:5]),
        "assessment": assessment,
        "outlook": outlook,
    }


def _identify_strengths(
    zone: dict,
    overlays: list,
    flood_info: dict,
    constraints: dict,
    infrastructure: dict,
    buildability: dict,
    precedent: dict,
) -> list:
    """Identify development strengths."""
    strengths = []

    # Infrastructure
    water_ok = infrastructure.get("water", {}).get("available", False) if infrastructure else False
    sewer_ok = infrastructure.get("sewer", {}).get("available", False) if infrastructure else False
    sw_ok = infrastructure.get("stormwater", {}).get("available", False) if infrastructure else False

    if water_ok and sewer_ok:
        strengths.append("Full reticulated water and sewer services available")
    elif water_ok:
        strengths.append("Reticulated water supply available")
    elif sewer_ok:
        strengths.append("Reticulated sewer available")

    if sw_ok:
        strengths.append("Council stormwater network available nearby")

    # No flood
    if flood_info and not flood_info.get("has_flood_data"):
        strengths.append("No direct flood mapping on parcel")

    # No major overlays
    overlay_count = sum(len(g.get("layers", [])) for g in (overlays or [])
                       if g.get("category", "").lower() not in ("height of buildings and structures",))
    if overlay_count == 0:
        strengths.append("No significant planning overlays")

    # No constraints
    if constraints and not constraints.get("has_constraints"):
        strengths.append("No easements, covenants, or environmental constraints")

    # Subdivision potential
    if buildability and buildability.get("subdivision", {}).get("can_subdivide"):
        max_lots = buildability["subdivision"].get("max_new_lots", 0)
        if max_lots > 1:
            strengths.append(f"Subdivision potential — up to {max_lots} lots")

    # Multi-dwelling
    if buildability:
        max_dw = buildability.get("buildable_envelope", {}).get("max_dwellings", 0)
        if max_dw and max_dw > 1:
            strengths.append(f"Multi-dwelling potential — up to {max_dw} units")

    # Approval precedent
    if precedent.get("outlook") == "positive":
        strengths.append(f"Strong approval precedent — {precedent['approved_count']} approvals in area")

    # Lot compliance
    if buildability and buildability.get("lot_compliance", {}).get("compliant", True):
        strengths.append("Lot size compliant with zone requirements")

    return strengths


def _identify_risks(
    zone: dict,
    overlays: list,
    flood_info: dict,
    constraints: dict,
    infrastructure: dict,
    buildability: dict,
    precedent: dict,
) -> list:
    """Identify development risks."""
    risks = []

    # Overlays
    if overlays:
        for group in overlays:
            cat = (group.get("category") or "").lower()
            layers = group.get("layers", [])
            if "bushfire" in cat:
                risks.append("Bushfire hazard area — BAL assessment required")
            elif "flood" in cat:
                risks.append("Flood overlay present — flood assessment may be required")
            elif "heritage" in cat or "character" in cat:
                risks.append("Heritage/character area — design controls apply")
            elif "landslide" in cat:
                risks.append("Landslide hazard — geotechnical assessment required")
            elif "steep" in cat or "slope" in cat:
                risks.append("Steep land — additional earthworks and retaining likely")
            elif "biodiversity" in cat or "waterway" in cat or "wetland" in cat:
                risks.append("Biodiversity/waterway overlay — ecological assessment likely required")
            elif "coastal" in cat:
                risks.append("Coastal protection area — additional requirements apply")
            elif "acid" in cat:
                risks.append("Acid sulfate soils — soil investigation may be required")

    # Flood
    if flood_info and flood_info.get("has_flood_data"):
        fd = flood_info.get("flood_data", {})
        if fd.get("min_floor_level"):
            risks.append(f"Flood affected — minimum floor level {fd['min_floor_level']}")
        else:
            risks.append("Flood mapping data on parcel — check requirements")

    # Constraints
    if constraints:
        if constraints.get("easements_count", 0) > 0:
            risks.append(f"{constraints['easements_count']} easement(s) on parcel — may restrict building location")
        if constraints.get("covenants_count", 0) > 0:
            risks.append(f"{constraints['covenants_count']} covenant(s) on parcel — may restrict development")
        koala = constraints.get("koala", {})
        if koala.get("status"):
            risks.append(f"Koala habitat: {koala['status']}")
        esa = constraints.get("esa", {})
        if esa.get("status"):
            risks.append(f"Environmental: {esa['status']}")

    # Infrastructure
    if infrastructure:
        if not infrastructure.get("water", {}).get("available"):
            risks.append("No reticulated water — tank/bore required")
        if not infrastructure.get("sewer", {}).get("available"):
            risks.append("No reticulated sewer — on-site system required")

    # Lot compliance
    if buildability:
        issues = buildability.get("lot_compliance", {}).get("issues", [])
        for issue in issues:
            if "lot is" in issue.lower():
                risks.append(issue)

    # Negative precedent
    if precedent.get("outlook") == "negative":
        risks.append(f"Challenging approval area — {precedent['refused_count']} refusals vs {precedent['approved_count']} approvals")

    return risks


def generate_ai_summary(
    site_info: dict,
    zone: dict,
    overlays: list,
    buildability: dict,
    infrastructure: dict,
    da_history: dict,
    flood_info: dict,
    constraints: dict,
    height: dict = None,
) -> dict:
    """
    Generate a comprehensive AI site analysis summary.
    
    Template-based approach — no LLM API needed.
    Returns structured JSON with score, summary, strengths, risks,
    development potential, and precedent analysis.
    """
    # Extract key values
    area = site_info.get("area_sqm")
    address = site_info.get("address", "")
    lot_plan = site_info.get("lot_plan", "")
    zone_code = (zone or {}).get("code", "Unknown Zone")
    zone_category = (zone or {}).get("category", "")

    # Precedent analysis
    precedent = _analyze_da_precedent(da_history or {})

    # Constraints score
    score, score_deductions = _calculate_constraints_score(
        overlays or [], flood_info or {}, constraints or {},
        infrastructure or {}, buildability or {}
    )

    # Strengths and risks
    strengths = _identify_strengths(
        zone, overlays, flood_info, constraints, infrastructure, buildability, precedent
    )
    risks = _identify_risks(
        zone, overlays, flood_info, constraints, infrastructure, buildability, precedent
    )

    # Build summary text
    area_str = f"{int(area):,}" if area else "unknown-size"
    da_count = (da_history or {}).get("on_parcel_count", 0)
    nearby_count = (da_history or {}).get("nearby_count", 0)

    summary_parts = []

    # Opening sentence
    if address:
        summary_parts.append(
            f"This {area_str}m² {zone_code} lot at {address} "
            f"has {da_count} development application{'s' if da_count != 1 else ''} on record."
        )
    else:
        summary_parts.append(
            f"This {area_str}m² {zone_code} lot ({lot_plan}) "
            f"has {da_count} development application{'s' if da_count != 1 else ''} on record."
        )

    # Strengths summary
    if strengths:
        top_strengths = strengths[:3]
        summary_parts.append(f"Key strengths: {'; '.join(top_strengths)}.")

    # Risks summary
    if risks:
        top_risks = risks[:3]
        summary_parts.append(f"Key risks: {'; '.join(top_risks)}.")

    # Development potential
    rules = (buildability or {}).get("rules", {})
    max_height = rules.get("max_height_m")
    site_cover = rules.get("max_site_cover_pct")
    max_storeys = rules.get("max_storeys")
    max_gfa = (buildability or {}).get("buildable_envelope", {}).get("max_gfa_sqm")
    max_dwellings = (buildability or {}).get("buildable_envelope", {}).get("max_dwellings")

    dev_pot_parts = []
    if max_height:
        dev_pot_parts.append(f"maximum building height is {max_height}m")
    if site_cover:
        dev_pot_parts.append(f"{site_cover}% site cover")
    if max_storeys:
        dev_pot_parts.append(f"up to {max_storeys} storeys")

    if dev_pot_parts:
        summary_parts.append(
            f"Development potential: Based on {zone_code} zoning, "
            f"{', '.join(dev_pot_parts)}."
        )

    # Precedent
    if precedent["total_count"] > 0:
        summary_parts.append(
            f"Precedent: {precedent['approved_count']} approval{'s' if precedent['approved_count'] != 1 else ''} "
            f"and {precedent['refused_count']} refusal{'s' if precedent['refused_count'] != 1 else ''} "
            f"in the surrounding area — {precedent['assessment'].lower()}."
        )

    # Development potential structure
    dev_potential = {
        "zone_code": zone_code,
        "zone_category": zone_category,
        "zone_link": SCC_ZONE_LINKS.get(zone_code),
        "zone_color": ZONE_COLORS.get(zone_code, "#999"),
        "max_height_m": max_height,
        "max_storeys": max_storeys,
        "max_site_cover_pct": site_cover,
        "max_gfa_sqm": round(max_gfa, 1) if max_gfa else None,
        "max_dwellings": max_dwellings,
        "can_subdivide": (buildability or {}).get("subdivision", {}).get("can_subdivide", False),
        "max_new_lots": (buildability or {}).get("subdivision", {}).get("max_new_lots", 0),
        "accepted_uses": (buildability or {}).get("uses", {}).get("accepted", []),
        "assessable_uses": (buildability or {}).get("uses", {}).get("assessable", []),
    }

    # Infrastructure summary
    infra_summary = {}
    if infrastructure:
        infra_summary = {
            "water": {
                "available": infrastructure.get("water", {}).get("available", False),
                "detail": infrastructure.get("water", {}).get("summary", ""),
            },
            "sewer": {
                "available": infrastructure.get("sewer", {}).get("available", False),
                "detail": infrastructure.get("sewer", {}).get("summary", ""),
            },
            "stormwater": {
                "available": infrastructure.get("stormwater", {}).get("available", False),
                "detail": infrastructure.get("stormwater", {}).get("summary", ""),
            },
        }

    # External links
    external_links = {
        "scc_planning_scheme": SCC_ZONE_LINKS.get(zone_code),
        "scc_pd_online": "https://pdonline.sunshinecoast.qld.gov.au/",
        "qld_globe": f"https://qldglobe.information.qld.gov.au/?ll={site_info.get('centroid', {}).get('lat', '')},{site_info.get('centroid', {}).get('lng', '')}",
        "da_portal": (da_history or {}).get("portal_link"),
    }

    # Score label
    if score >= 80:
        score_label = "Low Constraints"
        score_color = "#27AE60"
    elif score >= 60:
        score_label = "Moderate Constraints"
        score_color = "#F39C12"
    elif score >= 40:
        score_label = "Significant Constraints"
        score_color = "#E67E22"
    else:
        score_label = "Highly Constrained"
        score_color = "#E74C3C"

    return {
        "score": score,
        "score_label": score_label,
        "score_color": score_color,
        "score_deductions": score_deductions,
        "summary": " ".join(summary_parts),
        "strengths": strengths,
        "risks": risks,
        "development_potential": dev_potential,
        "precedent_analysis": precedent,
        "infrastructure_summary": infra_summary,
        "external_links": external_links,
        "quick_facts": {
            "area_sqm": area,
            "zone": zone_code,
            "zone_color": ZONE_COLORS.get(zone_code, "#999"),
            "flood_risk": "Yes" if (flood_info or {}).get("has_flood_data") else "No",
            "da_count": da_count,
            "nearby_da_count": nearby_count,
            "constraints_score": score,
            "easements": (constraints or {}).get("easements_count", 0),
            "overlay_count": sum(len(g.get("layers", [])) for g in (overlays or [])),
        },
    }
