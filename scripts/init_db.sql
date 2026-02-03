-- Urbix Database Init
-- Run: psql urbix < scripts/init_db.sql

CREATE EXTENSION IF NOT EXISTS postgis;

-- Cadastral Parcels (from QLD DCDB)
CREATE TABLE IF NOT EXISTS parcels (
    id SERIAL PRIMARY KEY,
    lot VARCHAR(20),
    plan_number VARCHAR(20),
    lotplan VARCHAR(40) UNIQUE,
    parcel_type VARCHAR(50),
    cover_type VARCHAR(30),
    tenure VARCHAR(50),
    area_sqm NUMERIC,
    locality VARCHAR(100),
    shire_name VARCHAR(100),
    feature_name VARCHAR(200),
    geom GEOMETRY(Geometry, 4326),
    synced_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_parcels_geom ON parcels USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_parcels_lotplan ON parcels (lotplan);
CREATE INDEX IF NOT EXISTS idx_parcels_lot_plan ON parcels (lot, plan_number);
CREATE INDEX IF NOT EXISTS idx_parcels_locality ON parcels (locality);

-- Addresses
CREATE TABLE IF NOT EXISTS addresses (
    id SERIAL PRIMARY KEY,
    full_address TEXT,
    street_number VARCHAR(20),
    street_name VARCHAR(100),
    street_type VARCHAR(20),
    locality VARCHAR(100),
    postcode VARCHAR(10),
    lot VARCHAR(20),
    plan_number VARCHAR(20),
    lotplan VARCHAR(40),
    geom GEOMETRY(Point, 4326),
    synced_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_addresses_geom ON addresses USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_addresses_fulltext ON addresses USING GIN (to_tsvector('english', full_address));
CREATE INDEX IF NOT EXISTS idx_addresses_lotplan ON addresses (lotplan);

-- Zones (Phase 2 — QPlan data)
CREATE TABLE IF NOT EXISTS zones (
    id SERIAL PRIMARY KEY,
    zone_code VARCHAR(100),
    zone_short VARCHAR(30),
    planning_scheme VARCHAR(200),
    lga VARCHAR(100),
    geom GEOMETRY(MultiPolygon, 4326),
    synced_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_zones_geom ON zones USING GIST (geom);

-- Overlays (Phase 2 — flood, bushfire, heritage, character)
CREATE TABLE IF NOT EXISTS overlays (
    id SERIAL PRIMARY KEY,
    overlay_type VARCHAR(100),
    overlay_name VARCHAR(200),
    overlay_code VARCHAR(50),
    planning_scheme VARCHAR(200),
    lga VARCHAR(100),
    geom GEOMETRY(Geometry, 4326),
    synced_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_overlays_geom ON overlays USING GIST (geom);

-- Sync log
CREATE TABLE IF NOT EXISTS sync_log (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(50),
    lga VARCHAR(100),
    records_synced INTEGER,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(20),
    error_message TEXT
);
