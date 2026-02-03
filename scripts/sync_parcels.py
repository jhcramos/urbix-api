"""
Sync QLD DCDB parcels from ArcGIS REST to PostGIS.

Usage:
    python scripts/sync_parcels.py                    # Sync all QLD (big!)
    python scripts/sync_parcels.py --lga "Sunshine Coast Regional"  # One LGA
    python scripts/sync_parcels.py --lga "Brisbane City"

Data source: QLD PlanningCadastre LandParcelPropertyFramework MapServer/4
Updates nightly from QLD Government.
"""

import argparse
import json
import time
import sys
import urllib.request
import urllib.parse
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

PARCELS_URL = (
    "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
    "PlanningCadastre/LandParcelPropertyFramework/MapServer/4/query"
)
ADDRESSES_URL = (
    "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
    "PlanningCadastre/LandParcelPropertyFramework/MapServer/0/query"
)

DB_DSN = "dbname=urbix"
BATCH_SIZE = 2000  # ArcGIS max is typically 2000-5000


def fetch_features(url: str, where: str, offset: int = 0) -> dict:
    """Fetch a batch of features from ArcGIS REST."""
    params = urllib.parse.urlencode({
        "where": where,
        "outFields": "*",
        "outSR": 4326,
        "f": "geojson",
        "resultOffset": offset,
        "resultRecordCount": BATCH_SIZE,
        "returnGeometry": "true",
    })
    full_url = f"{url}?{params}"
    req = urllib.request.Request(full_url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def sync_parcels(conn, lga_filter: str = None):
    """Sync parcels from QLD ArcGIS to PostGIS."""
    where = "1=1"
    if lga_filter:
        where = f"shire_name='{lga_filter}'"

    print(f"🔄 Syncing parcels: {where}")
    start = datetime.now()
    
    cur = conn.cursor()
    total = 0
    offset = 0
    
    while True:
        print(f"  Fetching batch at offset {offset}...")
        data = fetch_features(PARCELS_URL, where, offset)
        features = data.get("features", [])
        
        if not features:
            break
        
        rows = []
        for f in features:
            props = f.get("properties", {})
            geom = f.get("geometry")
            geom_json = json.dumps(geom) if geom else None
            
            lotplan = props.get("lotplan", "")
            if not lotplan:
                lot = props.get("lot", "")
                plan = props.get("plan", "")
                lotplan = f"{lot}{plan}" if lot and plan else None
            
            if not lotplan:
                continue
            
            rows.append((
                props.get("lot"),
                props.get("plan"),
                lotplan,
                props.get("parcel_typ"),
                props.get("cover_typ"),
                props.get("tenure"),
                props.get("lot_area"),
                props.get("locality"),
                props.get("shire_name"),
                props.get("feat_name"),
                geom_json,
            ))
        
        if rows:
            for row in rows:
                try:
                    cur.execute("""
                        INSERT INTO parcels (lot, plan_number, lotplan, parcel_type, cover_type, 
                                             tenure, area_sqm, locality, shire_name, feature_name, geom)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromGeoJSON(%s))
                        ON CONFLICT (lotplan) DO UPDATE SET
                            parcel_type = EXCLUDED.parcel_type,
                            cover_type = EXCLUDED.cover_type,
                            tenure = EXCLUDED.tenure,
                            area_sqm = EXCLUDED.area_sqm,
                            locality = EXCLUDED.locality,
                            shire_name = EXCLUDED.shire_name,
                            feature_name = EXCLUDED.feature_name,
                            geom = EXCLUDED.geom,
                            synced_at = NOW()
                    """, row)
                except Exception as e:
                    conn.rollback()
                    # Skip invalid geometries
                    continue
            conn.commit()
        
        total += len(features)
        print(f"  ✅ {total} parcels synced so far")
        
        # Check if there are more
        if len(features) < BATCH_SIZE:
            break
        offset += BATCH_SIZE
        time.sleep(0.5)  # Be nice to the server
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n🎉 Done! {total} parcels synced in {elapsed:.1f}s")
    
    # Log the sync
    cur.execute("""
        INSERT INTO sync_log (sync_type, lga, records_synced, started_at, completed_at, status)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, ("parcels", lga_filter or "ALL", total, start, datetime.now(), "success"))
    conn.commit()
    
    return total


def sync_addresses(conn, lga_filter: str = None):
    """Sync addresses from QLD ArcGIS to PostGIS."""
    where = "1=1"
    if lga_filter:
        where = f"local_authority='{lga_filter}'"

    print(f"\n🔄 Syncing addresses: {where}")
    start = datetime.now()
    
    cur = conn.cursor()
    total = 0
    offset = 0
    
    while True:
        print(f"  Fetching batch at offset {offset}...")
        data = fetch_features(ADDRESSES_URL, where, offset)
        features = data.get("features", [])
        
        if not features:
            break
        
        rows = []
        for f in features:
            props = f.get("properties", {})
            geom = f.get("geometry")
            
            addr = props.get("address", "")
            if not addr:
                continue
            
            # GeoJSON point
            lat = lng = None
            if geom and "coordinates" in geom:
                lng, lat = geom["coordinates"]
            
            geom_wkt = f"POINT({lng} {lat})" if lat and lng else None
            
            rows.append((
                addr,
                props.get("street_number", props.get("street_no_1", "")),
                props.get("street_name"),
                props.get("street_type"),
                props.get("locality"),
                None,  # postcode not always available
                props.get("lot"),
                props.get("plan"),
                props.get("lotplan"),
                geom_wkt,
            ))
        
        if rows:
            cur.executemany("""
                INSERT INTO addresses (full_address, street_number, street_name, street_type, 
                                       locality, postcode, lot, plan_number, lotplan, geom)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, ST_GeomFromText(%s, 4326))
                ON CONFLICT DO NOTHING
            """, rows)
            conn.commit()
        
        total += len(features)
        print(f"  ✅ {total} addresses synced so far")
        
        if len(features) < BATCH_SIZE:
            break
        offset += BATCH_SIZE
        time.sleep(0.5)
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n🎉 Done! {total} addresses synced in {elapsed:.1f}s")
    
    cur.execute("""
        INSERT INTO sync_log (sync_type, lga, records_synced, started_at, completed_at, status)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, ("addresses", lga_filter or "ALL", total, start, datetime.now(), "success"))
    conn.commit()
    
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync QLD DCDB to PostGIS")
    parser.add_argument("--lga", help="Filter by LGA name (e.g. 'Sunshine Coast Regional')")
    parser.add_argument("--parcels-only", action="store_true", help="Only sync parcels")
    parser.add_argument("--addresses-only", action="store_true", help="Only sync addresses")
    args = parser.parse_args()
    
    conn = psycopg2.connect(DB_DSN)
    
    try:
        if not args.addresses_only:
            sync_parcels(conn, args.lga)
        if not args.parcels_only:
            sync_addresses(conn, args.lga)
    finally:
        conn.close()
    
    print("\n✅ All syncs complete!")
