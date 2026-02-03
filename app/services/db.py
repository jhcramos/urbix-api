"""PostGIS database service — local parcel/address lookups."""

import json
from typing import Optional
import psycopg2
import psycopg2.extras

DB_DSN = "dbname=urbix"

_conn = None


def get_conn():
    """Get or create database connection."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(DB_DSN)
    return _conn


def db_available() -> bool:
    """Check if PostGIS database is available and has data."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM parcels")
        count = cur.fetchone()[0]
        return count > 0
    except Exception:
        return False


STREET_ABBREVS_DB = {
    " St ": " Street ", " Rd ": " Road ", " Ave ": " Avenue ",
    " Dr ": " Drive ", " Ct ": " Court ", " Pl ": " Place ",
    " Cres ": " Crescent ", " Tce ": " Terrace ", " Ln ": " Lane ",
    " Pde ": " Parade ", " Blvd ": " Boulevard ", " Hwy ": " Highway ",
    " Cct ": " Circuit ", " Esp ": " Esplanade ", " Cl ": " Close ",
}


def _expand_abbrevs(text: str) -> str:
    t = text + " "
    for abbr, full in STREET_ABBREVS_DB.items():
        t = t.replace(abbr, full)
    return t.strip()


def search_addresses_db(query: str, limit: int = 10) -> list:
    """Full-text address search from PostGIS."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    expanded = _expand_abbrevs(query)
    
    cur.execute("""
        SELECT full_address as address, locality, lot, plan_number as plan, lotplan,
               street_name, street_number,
               ST_Y(geom) as lat, ST_X(geom) as lng
        FROM addresses
        WHERE full_address ILIKE %s
        ORDER BY full_address
        LIMIT %s
    """, (f"%{expanded}%", limit))
    
    return [dict(r) for r in cur.fetchall()]


def get_parcel_by_lotplan_db(lot: str, plan: str) -> Optional[dict]:
    """Get parcel by lot/plan from PostGIS."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute("""
        SELECT lot, plan_number as plan, lotplan, parcel_type, cover_type,
               tenure, area_sqm, locality, shire_name, feature_name,
               ST_AsGeoJSON(geom)::json as geometry
        FROM parcels
        WHERE lot = %s AND plan_number = %s
        AND (cover_type = 'Base' OR cover_type IS NULL)
        ORDER BY CASE WHEN cover_type = 'Base' THEN 0 ELSE 1 END
        LIMIT 1
    """, (lot, plan))
    
    row = cur.fetchone()
    if not row:
        return None
    
    return {
        "parcel": {
            "lot": row["lot"],
            "plan": row["plan"],
            "lot_plan": f"{row['lot']}/{row['plan']}",
            "lotplan": row["lotplan"],
            "parcel_type": row["parcel_type"],
            "cover_type": row["cover_type"],
            "tenure": row["tenure"],
            "area_sqm": float(row["area_sqm"]) if row["area_sqm"] else None,
            "locality": row["locality"],
            "shire_name": row["shire_name"],
            "feature_name": row["feature_name"],
        },
        "geometry": row["geometry"],
    }


def get_parcel_by_point_db(lat: float, lng: float) -> Optional[dict]:
    """Get parcel at a point from PostGIS — fast spatial query."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute("""
        SELECT lot, plan_number as plan, lotplan, parcel_type, cover_type,
               tenure, area_sqm, locality, shire_name, feature_name,
               ST_AsGeoJSON(geom)::json as geometry
        FROM parcels
        WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        ORDER BY CASE WHEN cover_type = 'Base' THEN 0 ELSE 1 END
        LIMIT 1
    """, (lng, lat))
    
    row = cur.fetchone()
    if not row:
        return None
    
    return {
        "parcel": {
            "lot": row["lot"],
            "plan": row["plan"],
            "lot_plan": f"{row['lot']}/{row['plan']}",
            "lotplan": row["lotplan"],
            "parcel_type": row["parcel_type"],
            "cover_type": row["cover_type"],
            "tenure": row["tenure"],
            "area_sqm": float(row["area_sqm"]) if row["area_sqm"] else None,
            "locality": row["locality"],
            "shire_name": row["shire_name"],
            "feature_name": row["feature_name"],
        },
        "geometry": row["geometry"],
    }


def get_overlays_at_point_db(lat: float, lng: float) -> list:
    """Get overlays that intersect a point."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute("""
        SELECT overlay_type, overlay_name, overlay_code, planning_scheme, lga
        FROM overlays
        WHERE ST_Intersects(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
    """, (lng, lat))
    
    return [dict(r) for r in cur.fetchall()]


def get_zone_at_point_db(lat: float, lng: float) -> Optional[dict]:
    """Get the planning zone at a point."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute("""
        SELECT zone_code, zone_short, planning_scheme, lga
        FROM zones
        WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        LIMIT 1
    """, (lng, lat))
    
    row = cur.fetchone()
    return dict(row) if row else None
